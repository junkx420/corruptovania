"""Record read-only T14 comparisons using the MP3 client's memory reader and flag finder."""

from __future__ import annotations

import argparse
import json
import struct
import time
from datetime import UTC, datetime

from worlds.metroidprime3.client.checks import CheckDetector, LocationTable
from worlds.metroidprime3.client.flag_block import DEFAULT_SCAN_RANGES, OFF_FLAGS, FlagBlockFinder
from worlds.metroidprime3.client.game import GameState, read_game_state
from worlds.metroidprime3.client.memory import MEM2_SIZE, MEM2_START, DolphinMemory, MemoryAccessError, in_ram
from worlds.metroidprime3.location_flags import FLAG_BLOCK_SIZE, WORLD_NAMES
from worlds.metroidprime3.patcher.seed_id import SEED_ID_LENGTH, seed_id_from_build_string


class ReadOnlyMemory(DolphinMemory):
    def __init__(self) -> None:
        super().__init__()
        self.block_reads: dict[int, bytes] = {}

    def _write(self, address: int, data: bytes) -> None:
        raise RuntimeError("T14 probe only supports reads")

    def read(self, address: int, size: int) -> bytes:
        data = super().read(address, size)
        if size == FLAG_BLOCK_SIZE:
            self.block_reads[address - OFF_FLAGS] = data
        return data

    def verified_seed(self, expected: bytes) -> bool:
        if not self.check_game_id():
            return False
        dol = self.version.dol
        build = self.read(dol.build_string_address, len(dol.build_string))
        return seed_id_from_build_string(build, dol) == expected


def emit(kind: str, **fields) -> None:
    print(json.dumps({"kind": kind, "time": datetime.now(UTC).isoformat(timespec="milliseconds"), **fields}),
          flush=True)


def address(value: int | None) -> str | None:
    return f"0x{value:08X}" if value is not None else None


def candidates(finder: FlagBlockFinder) -> dict:
    return {
        name: {"valid": [address(w) for w in finder.blocks.get(world, ())],
               "rejected": [address(w) for w in finder.rejected.get(world, ())]}
        for world, name in WORLD_NAMES.items()
    }


def state_fields(state: GameState) -> dict:
    return {"world": LocationTable.world_name(state.world_id), "game_state": address(state.game_state_pointer),
            "player_state": address(state.player_state), "item_percentage": state.item_percentage,
            "inventory_valid": state.inventory_valid, "state": "ingame" if state.ingame else state.reason}


def pointer_hits(memory: ReadOnlyMemory, targets: list[int], state: GameState) -> dict:
    """Find aligned big-endian words equal to W or nearby boundaries. Hits alone imply no ownership."""
    hits: dict[str, dict[str, list]] = {
        address(block): {"W-4": [], "W": [], "flags": []} for block in targets
    }
    anchors = {"GameState": state.game_state_pointer, "PlayerState": state.player_state,
               "CStateManager": memory.version.cstate_manager_global}
    for start, size in (*DEFAULT_SCAN_RANGES, (MEM2_START, MEM2_SIZE)):
        for base, chunk in memory.iter_chunks(start, size):
            for block in targets:
                for key, offset in (("W-4", -4), ("W", 0), ("flags", OFF_FLAGS)):
                    word = struct.pack(">I", block + offset)
                    pos = chunk.find(word)
                    while pos >= 0:
                        source = base + pos
                        if source % 4 == 0:
                            near = {name: f"+0x{source - anchor:X}" for name, anchor in anchors.items()
                                    if anchor is not None and 0 <= source - anchor < 0x200}
                            hits[address(block)][key].append({"source": address(source), "near": near})
                        pos = chunk.find(word, pos + 1)
    return hits


def game_state_refs(memory: ReadOnlyMemory, finder: FlagBlockFinder, state: GameState) -> dict | None:
    """Compare the PAL GameState world table against the scanner's candidate addresses."""
    if state.game_state_pointer is None or memory.version.dol.game_id != "RM3P01":
        return None
    count, capacity, base = struct.unpack(">III", memory.read(state.game_state_pointer + 0x18, 12))
    entry_size = 0x38
    ref_offset = 0x14
    entries = []
    if 0 < count <= capacity <= 64 and in_ram(base, count * entry_size):
        data = memory.read(base, count * entry_size)
        for offset in range(0, len(data), entry_size):
            world = struct.unpack_from(">Q", data, offset)[0]
            value = struct.unpack_from(">I", data, offset + ref_offset)[0]
            match = value in finder.blocks.get(world, ())
            entries.append({"offset": f"0x{offset + ref_offset:X}", "block": address(value),
                            "world": LocationTable.world_name(world), "valid_candidate": match})
    return {"base": address(base), "count": count, "capacity": capacity, "entries": entries}


def snapshot(memory: ReadOnlyMemory, finder: FlagBlockFinder, expected: bytes, args: argparse.Namespace) -> bool:
    state = read_game_state(memory)
    if not state.ingame:
        emit("unavailable", **state_fields(state))
        return False
    finder.scan()
    data: dict[int, dict[int, bytes]] = {}
    for world in WORLD_NAMES:
        blocks = sorted(finder.blocks.get(world, []) + finder.rejected.get(world, []))
        data[world] = {w: memory.block_reads[w] for w in blocks}
    targets = finder.blocks.get(state.world_id, []) + finder.rejected.get(state.world_id, [])
    refs = pointer_hits(memory, sorted(targets), state) if args.references else None
    rooted_refs = game_state_refs(memory, finder, state) if args.references else None
    if not memory.verified_seed(expected) or read_game_state(memory) != state:
        emit("unstable_snapshot", event=args.event)
        return False
    for world, blocks in data.items():
        for block, flags in blocks.items():
            if (not finder.validate(block, world) or memory.read(block + OFF_FLAGS, FLAG_BLOCK_SIZE) != flags
                    or finder.plausible(flags, world) != (block in finder.blocks.get(world, ()))):
                emit("unstable_snapshot", event=args.event, world=WORLD_NAMES[world], block=address(block))
                return False
    encoded = {WORLD_NAMES[world]: {address(w): flags.hex() for w, flags in blocks.items()}
               for world, blocks in data.items()}
    emit("snapshot", event=args.event, **state_fields(state), candidates=candidates(finder), bytes=encoded,
         scan_seconds=round(finder.last_scan_seconds, 4), references=refs, game_state_refs=rooted_refs)
    return True


def watch(memory: ReadOnlyMemory, finder: FlagBlockFinder, expected: bytes, args: argparse.Namespace) -> bool:
    table = LocationTable()
    detector = CheckDetector()
    start = time.monotonic()
    next_report = 60.0
    total = ingame = missing = 0
    last_world = None
    previous = None
    scan_count = finder.scan_count

    def summary() -> dict:
        return {"seconds": round(time.monotonic() - start, 3), "polls": total, "ingame": ingame,
                "missing": missing, "scans": finder.scan_count}

    try:
        while time.monotonic() - start < args.seconds:
            if not memory.verified_seed(expected):
                emit("aborted", reason="Game or seed changed", **summary())
                return False
            total += 1
            state = read_game_state(memory)
            if not state.ingame:
                finder.reset()
                detector.reset_pending()
            if state.world_id != last_world:
                detector.reset_pending()
                last_world = state.world_id
            flag_read = None
            if state.ingame and table.has_world(state.world_id):
                ingame += 1
                memory.block_reads.clear()
                flag_read = finder.read_flags(state.world_id)
                missing += flag_read is None
            if finder.scan_count != scan_count:
                scan_count = finder.scan_count
                emit("scan", **summary(), duration=round(finder.last_scan_seconds, 4), candidates=candidates(finder))
            sample = {**state_fields(state), "blocks": {}, "disagree": [], "or_locations": []}
            if flag_read:
                sample["blocks"] = {address(w): memory.block_reads[w].hex() for w in flag_read.blocks}
                sample["disagree"] = list(flag_read.disagree)
                collected = table.collected(state.world_id, flag_read.flags)
                sample["or_locations"] = sorted(collected)
                new = detector.update(collected)
                if new:
                    emit("debounced", **summary(), locations=sorted(new), **state_fields(state))
            if sample != previous:
                emit("sample", **summary(), **sample)
                previous = sample
            elapsed = time.monotonic() - start
            if elapsed >= next_report:
                emit("heartbeat", **summary())
                next_report += 60.0
            time.sleep(max(0.0, min(args.interval, args.seconds - elapsed)))
    except (MemoryAccessError, KeyboardInterrupt) as exc:
        emit("aborted", reason=str(exc) or "interrupted", **summary())
        return False
    emit("finished", **summary())
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-id", required=True, type=bytes.fromhex)
    parser.add_argument("--emulator", required=True, choices=("Dolphin", "PrimeHack"))
    subparsers = parser.add_subparsers(dest="mode", required=True)
    shot = subparsers.add_parser("snapshot")
    shot.add_argument("event")
    shot.add_argument("--references", action="store_true", help="Scan MEM1 and MEM2 for references to current blocks")
    shot.add_argument("--mem2", action="store_true", help="Extend discovery beyond the client's MEM1 search")
    survey = subparsers.add_parser("watch")
    survey.add_argument("--interval", type=float, default=0.5)
    survey.add_argument("--seconds", type=float, default=3600)
    args = parser.parse_args()
    if len(args.seed_id) != SEED_ID_LENGTH:
        parser.error("--seed-id requires 16 bytes in hexadecimal")
    if args.mode == "watch" and (not 0 < args.interval <= args.seconds < float("inf")):
        parser.error("require 0 < interval <= seconds < infinity")
    memory = ReadOnlyMemory()
    emit("start", emulator=args.emulator, mode=args.mode)
    try:
        connected = memory.connect()
        if not memory.connected or not memory.verified_seed(args.seed_id):
            emit("aborted", reason=f"Expected seed unavailable ({connected.status.value})")
            return 1
        ranges = DEFAULT_SCAN_RANGES
        if args.mode == "snapshot" and args.mem2:
            ranges += ((MEM2_START, MEM2_SIZE),)
        finder = FlagBlockFinder(memory, scan_ranges=ranges)
        run = snapshot if args.mode == "snapshot" else watch
        return 0 if run(memory, finder, args.seed_id, args) else 1
    except MemoryAccessError as exc:
        emit("aborted", reason=str(exc))
        return 1
    finally:
        memory.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
