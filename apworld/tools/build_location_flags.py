"""Generates ``apworld/metroidprime3/location_flags.py``: pickup index 1-99 →
(MLVL ID, byte index in the world flag block, full object ID).

Read-only. Inputs:
- an extracted PAL ISO (folder with ``DATA/files`` or with the ``*.pak``),
- ``tools/prime3_patcher/MP3Randomizer/MP3Randomizer/PickupLocations.cs``
  (MREA ID, layer, lower 16 bits of the instance ID per location).

Finding (details ``docs/AP_SAVW_FORMAT.md``): the 1024-byte flag block of the world
is the state of the **Memory Relays** (MRLY) from list 1 of the SAVW. Byte ``i``
belongs to entry ``i`` of this list (empty slots count too). A pickup does not set
a byte of its own; when collected, it activates its Memory Relay via a relay, and
that Memory Relay switches the pickup off again on load.

Usage (from the repo root directory):

    venv/Scripts/python.exe -I apworld/tools/build_location_flags.py <extracted-ISO>

Options: ``--locations`` (path to PickupLocations.cs), ``--output`` (target file),
``--check`` (compare only, write nothing; exit 1 on difference).
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import savw_parser as sp  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DEFAULT_LOCATIONS = os.path.join(
    REPO, "tools", "prime3_patcher", "MP3Randomizer", "MP3Randomizer", "PickupLocations.cs"
)
DEFAULT_OUTPUT = os.path.join(REPO, "apworld", "metroidprime3", "location_flags.py")

MAX_DEPTH = 3  # connections from the pickup to the Memory Relay (measured: always 2)

# World names for the generated file: region names of the logic database
# (randovania/games/prime3/logic_database/*.json, field extra.asset_id = MLVL ID).
WORLD_LABELS = {
    0x9BA9292D588D6EB8: "Bryyo - Fire",
    0xB0D67636D61F3868: "Bryyo - Ice",
    0x9F059B53561A9695: "Bryyo - Reptilicus",
    0xCD79C43EB6C801FD: "Bryyo - Seed",
    0x37A9E86F0A0CAF6F: "G.F.S. Olympus",
    0xC133F919C108BDF9: "G.F.S. Valhalla",
    0x6FB8EF2A9523C343: "Norion",
    0x4B07619AB6125B33: "Phaaze",
    0x38098524EF78B6D2: "Pirate Homeworld - Command",
    0xDD1C4E18E7291BEF: "Pirate Homeworld - Mines",
    0x106F7F4FEFB651D9: "Pirate Homeworld - Research",
    0xDE97D48188CA8C99: "Pirate Homeworld - Seed",
    0xC37F4AD853284C78: "SkyTown, Elysia - Main",
    0xE0F0622642E42CAB: "SkyTown, Elysia - Pod",
    0x94BCA72AB1CFEC05: "SkyTown, Elysia - Seed",
}


@dataclasses.dataclass(frozen=True)
class PickupLocation:
    index: int
    mrea_id: int
    layer: int
    type: str  # "Pickup" or "SpecialFunction"
    local_id: int
    percentage_local_id: int | None


_LOC_RE = re.compile(
    r"create_pickup_location\((\d+)uL, (\d+)u, \"(\w+)\", "
    r"new byte\[2\] \{ (\d+), (\d+) \}, "  # instance_id
    r"new byte\[2\] \{ \d+, \d+ \}, new byte\[2\] \{ \d+, \d+ \}, "  # memo, streamed audio
    r"new byte\[(\d)\](?: \{ (\d+), (\d+) \})?, "  # percentage_pickup_id
    r"new byte\[\d\](?: \{ \d+, \d+ \})?, "  # end_relay_id
    r"should_modify_hud_type: \w+, (\d+)u\)"
)


def read_pickup_locations(path: str) -> list[PickupLocation]:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    out = []
    for m in _LOC_RE.finditer(text):
        mrea, layer, typ, hi, lo, n_pct, pct_hi, pct_lo, idx = m.groups()
        pct = int(pct_hi) * 256 + int(pct_lo) if n_pct == "2" else None
        out.append(PickupLocation(int(idx), int(mrea), int(layer), typ, int(hi) * 256 + int(lo), pct))
    if sorted(p.index for p in out) != list(range(100)):
        raise ValueError(f"{path}: expected locations 0-99, found {len(out)}")
    return sorted(out, key=lambda p: p.index)


# --------------------------------------------------------------------------- #
# Graph analysis of a room
# --------------------------------------------------------------------------- #


ID_MASK = 0x03FFFFFF  # area (10 bits) + local ID (16 bits), without layer (6 bits)


class Room:
    """Objects and connections of a room.

    Connection targets are resolved via area + local ID (lower 26 bits):
    the patcher writes targets back without layer bits (``Connection.export``),
    the game finds them anyway (location 4 on layer 16 measured live)."""

    def __init__(self, mrea: sp.Mrea):
        self.objects: dict[int, sp.ScriptObject] = {}
        self.layer_of: dict[int, int] = {}
        by_key: dict[int, int] = {}
        # Area + ID more than once (only in the patched game: new patcher objects in
        # several layers). Such targets are only resolved by exact full ID.
        self.ambiguous: set[int] = set()
        for layer, o in mrea.objects():
            key = o.instance_id & ID_MASK
            if key in by_key:
                self.ambiguous.add(key)
            by_key.setdefault(key, o.instance_id)
            self.objects[o.instance_id] = o
            self.layer_of[o.instance_id] = layer
        for key in self.ambiguous:
            del by_key[key]
        self.targets: dict[int, list[tuple[str, str, int]]] = {}
        self.incoming: dict[int, list[tuple[int, str, str]]] = collections.defaultdict(list)
        for iid, o in self.objects.items():
            conns = [
                (st, msg, t if t in self.objects else by_key.get(t & ID_MASK, t)) for st, msg, t in o.connections
            ]
            self.targets[iid] = conns
            for state, msg, target in conns:
                self.incoming[target].append((iid, state, msg))

    def connections(self, iid: int) -> list[tuple[str, str, int]]:
        return self.targets.get(iid, [])

    def type(self, iid: int) -> str:
        o = self.objects.get(iid)
        return o.type if o else "?"

    def find(self, layer: int, local_id: int, type_: str) -> sp.ScriptObject | None:
        hits = [
            o for iid, o in self.objects.items()
            if self.layer_of[iid] == layer and o.local_id == local_id and o.type == type_
        ]
        if len(hits) > 1:
            raise ValueError(f"{type_} {local_id:#x} more than once in layer {layer}")
        return hits[0] if hits else None

    def activated_relays(self, start: int, relays: dict[int, int], max_depth: int) -> dict[int, int]:
        """Memory Relays reached from ``start`` via connections with message
        ``ACTV`` → smallest depth. Memory Relays are not traversed."""
        found: dict[int, int] = {}
        queue = collections.deque([(start, 0)])
        seen = {start}
        while queue:
            cur, depth = queue.popleft()
            obj = self.objects.get(cur)
            if obj is None:
                continue
            for _state, msg, target in self.connections(cur):
                if target in relays and msg == "ACTV":
                    found.setdefault(target, depth + 1)
                if target not in seen and depth + 1 < max_depth and self.type(target) != "MRLY":
                    seen.add(target)
                    queue.append((target, depth + 1))
        return found

    def activators(self, relay: int) -> set[int]:
        return {src for src, _state, msg in self.incoming[relay] if msg == "ACTV"}

    def closure(self, start: int, max_depth: int) -> set[int]:
        seen = {start}
        queue = collections.deque([(start, 0)])
        while queue:
            cur, depth = queue.popleft()
            obj = self.objects.get(cur)
            if obj is None or depth >= max_depth:
                continue
            for _state, _msg, target in self.connections(cur):
                if target not in seen and self.type(target) != "MRLY":
                    seen.add(target)
                    queue.append((target, depth + 1))
        return seen


@dataclasses.dataclass
class Result:
    index: int
    mlvl_id: int
    area_index: int
    mrea_id: int
    layer: int
    type: str
    object_id: int  # full ID of the object from PickupLocations.cs (PCKP or SPFN)
    savw_object_id: int  # object listed in SAVW list 3
    savw_object_type: str
    savw_object_index: int
    relay_id: int | None  # Memory Relay whose byte is set
    byte_index: int | None
    status: str  # certain | probable | uncertain
    reason: str
    other_bytes: tuple[int, ...]  # further bytes set by the same event


def analyse(game: sp.GameFiles, locations: list[PickupLocation]) -> list[Result]:
    mrea_to_world: dict[int, tuple[sp.Mlvl, int]] = {}
    for pak, res in game.iter_type("MLVL"):
        mlvl = sp.parse_mlvl(pak.read(res.asset_id), res.asset_id)
        for area in mlvl.areas:
            mrea_to_world.setdefault(area.mrea_id, (mlvl, area.index))
    savw_cache: dict[int, sp.Savw] = {}
    results = []
    for loc in locations:
        if loc.index == 0:
            continue  # location 0 is never patched (E13)
        mlvl, area_index = mrea_to_world[loc.mrea_id]
        savw = savw_cache.get(mlvl.savw_id)
        if savw is None:
            savw = savw_cache[mlvl.savw_id] = sp.parse_savw(game.read(mlvl.savw_id, "SAVW"), mlvl.savw_id)
        relays = {e.instance_id: i for i, e in enumerate(savw.lists[1]) if not e.empty}
        saved = {e.instance_id: i for i, e in enumerate(savw.objects) if not e.empty}
        room = Room(sp.parse_mrea(game.read(loc.mrea_id, "MREA"), loc.mrea_id))

        main_type = "PCKP" if loc.type == "Pickup" else "SPFN"
        main = room.find(loc.layer, loc.local_id, main_type)
        if main is None:
            raise ValueError(f"Location {loc.index}: {main_type} {loc.local_id:#06x} missing in MREA {loc.mrea_id:#x}")
        if main.area != area_index or main.layer != loc.layer:
            raise ValueError(f"Location {loc.index}: instance ID {main.instance_id:#x} does not match area/layer")
        second = None
        if loc.percentage_local_id is not None:
            second = room.find(loc.layer, loc.percentage_local_id, "PCKP")
            if second is None:
                raise ValueError(f"Location {loc.index}: second PCKP {loc.percentage_local_id:#06x} missing")

        in_savw = [o for o in (main, second) if o is not None and o.instance_id in saved]
        if len(in_savw) != 1:
            raise ValueError(f"Location {loc.index}: {len(in_savw)} objects in SAVW list 3")
        savw_obj = in_savw[0]

        if loc.type == "Pickup":
            relay, status, reason, others = _pickup_relay(room, relays, main.instance_id)
        else:
            relay, status, reason, others = _special_relay(room, relays, main.instance_id)

        results.append(Result(
            index=loc.index,
            mlvl_id=mlvl.asset_id,
            area_index=area_index,
            mrea_id=loc.mrea_id,
            layer=loc.layer,
            type=loc.type,
            object_id=main.instance_id,
            savw_object_id=savw_obj.instance_id,
            savw_object_type=savw_obj.type,
            savw_object_index=saved[savw_obj.instance_id],
            relay_id=relay,
            byte_index=relays[relay] if relay is not None else None,
            status=status,
            reason=reason,
            other_bytes=tuple(sorted(relays[r] for r in others)),
        ))
    _check_collisions(results)
    return results


def _pickup_relay(room: Room, relays: dict[int, int], pickup: int):
    cands = room.activated_relays(pickup, relays, MAX_DEPTH)
    # Proof of persistence: the Memory Relay switches the pickup off on load
    own = [
        r for r in cands
        if any(t == pickup and msg == "DCTV" for _s, msg, t in room.connections(r))
    ]
    others = [r for r in cands if r not in own]
    if len(own) == 1:
        r = own[0]
        reason = (f"PCKP activates MRLY {r:#x} (depth {cands[r]}), MRLY switches the PCKP off on load (DCTV)")
        exclusive = room.activators(r) <= room.closure(pickup, MAX_DEPTH)
        if not exclusive:
            return r, "uncertain", reason + "; MRLY is also activated by other objects", others
        return r, "certain", reason, others
    if not cands:
        return None, "uncertain", "no Memory Relay reachable from the PCKP", []
    best = min(cands, key=lambda r: (cands[r], relays[r]))
    return best, "uncertain", f"{len(own)} MRLY with back connection, {len(cands)} candidates", [
        r for r in cands if r != best
    ]


def _special_relay(room: Room, relays: dict[int, int], spfn: int):
    triggers = [src for src, _st, msg in room.incoming[spfn] if msg == "ACTN"]
    if not triggers:
        return None, "uncertain", "SPFN has no trigger (ACTN)", []
    # Level 1: Memory Relays at the trigger itself; levels 2 and 3: at its predecessors
    levels = [triggers]
    for _ in range(2):
        levels.append(sorted({a for t in levels[-1] for a, _s, _m in room.incoming[t]} - set().union(*levels)))
    chain: set[int] = set()
    for level, starts in enumerate(levels, start=1):
        chain |= set(starts)
        cands: dict[int, int] = {}
        for t in starts:
            for _st, msg, target in room.connections(t):
                if msg == "ACTV" and target in relays:
                    cands.setdefault(target, level)
        if not cands:
            continue
        exclusive = [r for r in cands if room.activators(r) <= chain]
        where = "Trigger" if level == 1 else f"Predecessor of the trigger (level {level})"
        sources = lambda r: ", ".join(f"{t:#x}" for t in starts if r in [c[2] for c in room.connections(t)])  # noqa: E731
        base = ("No back connection to SPFN/PCKP (pattern of the SpecialFunction locations: the MRLY starts a setup "
                "relay on load), not verified live")
        if len(exclusive) == 1:
            r = exclusive[0]
            reason = (f"{where} {sources(r)} activates MRLY {r:#x} together with SPFN/PCKP, activated only from there. "
                      f"{base}")
            return r, "probable", reason, [c for c in cands if c != r]
        # Several exclusive candidates: all are set at the same moment. Preferred is
        # the MRLY with the load pattern ACTV -> ACTN to a relay (SRLY).
        setup = [r for r in exclusive if any(st == "ACTV" and msg == "ACTN" and room.type(t) == "SRLY"
                                             for st, msg, t in room.connections(r))]
        if len(setup) == 1:
            r = setup[0]
            rest = sorted((c for c in cands if c != r), key=relays.get)
            reason = (f"{where} {sources(r)} activates {len(cands)} MRLY only from there, together with SPFN/PCKP; "
                      f"chosen MRLY {r:#x} (load pattern ACTV->ACTN to SRLY); the others (byte "
                      f"{', '.join(str(relays[c]) for c in rest)}) are set at the same moment. {base}")
            return r, "probable", reason, rest
        best = min(cands, key=lambda r: relays[r])
        return best, "uncertain", (
            f"{where} activates {len(cands)} MRLY ({', '.join(str(relays[c]) for c in sorted(cands, key=relays.get))}), "
            f"{len(exclusive)} of them only from there; chosen: smallest index"
        ), [c for c in cands if c != best]
    return None, "uncertain", "no Memory Relay at the trigger or its predecessors", []


def _check_collisions(results: list[Result]) -> None:
    by_byte: dict[tuple[int, int], list[Result]] = collections.defaultdict(list)
    for r in results:
        if r.byte_index is not None:
            by_byte[(r.mlvl_id, r.byte_index)].append(r)
    for (_mlvl, byte), rs in by_byte.items():
        if len(rs) > 1:
            names = ", ".join(str(r.index) for r in rs)
            for r in rs:
                r.status = "uncertain"
                r.reason += f"; byte {byte} is shared by locations {names}"


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


def render(results: list[Result]) -> str:
    lines = [
        '"""Location check table for Metroid Prime 3 PAL (RM3P01). GENERATED, do not edit by hand.',
        "",
        "Generated with ``apworld/tools/build_location_flags.py`` from the game data (SAVW, MLVL, MREA) and",
        "``PickupLocations.cs``. Format and derivation: ``docs/AP_SAVW_FORMAT.md``.",
        "",
        "Flag block per world (``docs/AP_LIVE_TESTS.md``, test D): 1024 bytes from ``W + 0x1C``, ``W`` = address of",
        "the MLVL ID in the heap. Byte ``i`` = state of Memory Relay ``i`` from SAVW list 1 (0 = off, 1 = on).",
        "A location counts as collected when ``LOCATION_FLAGS[location][1]`` is non-zero in the block of its world.",
        '"""',
        "",
        "FLAG_BLOCK_SIZE = 1024",
        "",
        "# Pickup index -> (world MLVL ID, byte index in the flag block, full instance ID of the location object).",
        "# The location object is the PCKP, or for SpecialFunction locations the SPFN from PickupLocations.cs.",
        "LOCATION_FLAGS: dict[int, tuple[int, int, int]] = {",
    ]
    for r in results:
        byte = r.byte_index if r.byte_index is not None else -1
        lines.append(f"    {r.index}: (0x{r.mlvl_id:016X}, {byte}, 0x{r.object_id:08X}),"
                     f"  # {WORLD_LABELS.get(r.mlvl_id, '?')}, {r.status}")
    lines += [
        "}",
        "",
        "# Pickup index -> details:",
        "#   relay_id        Memory Relay (full instance ID) whose byte is set",
        "#   savw_object     object in SAVW list 3 (PCKP; for SpecialFunction the second PCKP)",
        "#   status          certain | probable | uncertain",
        "#   other_bytes     further bytes of the same world that are set by the same event",
        "LOCATION_DETAILS: dict[int, dict[str, object]] = {",
    ]
    for r in results:
        lines.append(f"    {r.index}: {{")
        lines.append(f"        \"type\": {r.type!r},")
        lines.append(f"        \"mrea_id\": 0x{r.mrea_id:016X},")
        lines.append(f"        \"area_index\": {r.area_index},")
        lines.append(f"        \"layer\": {r.layer},")
        lines.append(f"        \"relay_id\": {('0x%08X' % r.relay_id) if r.relay_id is not None else None},")
        lines.append(f"        \"savw_object\": ({r.savw_object_type!r}, 0x{r.savw_object_id:08X}, {r.savw_object_index}),")
        lines.append(f"        \"status\": {r.status!r},")
        lines.append(f"        \"reason\": {r.reason!r},")
        lines.append(f"        \"other_bytes\": {r.other_bytes!r},")
        lines.append("    },")
    lines += [
        "}",
        "",
        "WORLD_NAMES: dict[int, str] = {",
    ]
    for mlvl_id in sorted({r.mlvl_id for r in results}):
        lines.append(f"    0x{mlvl_id:016X}: {WORLD_LABELS.get(mlvl_id, '?')!r},")
    lines += ["}", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("game_dir", help="extracted PAL ISO (folder with DATA/files)")
    ap.add_argument("--locations", default=DEFAULT_LOCATIONS)
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    ap.add_argument("--check", action="store_true", help="compare only, exit 1 on difference")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    results = analyse(sp.GameFiles(args.game_dir), read_pickup_locations(args.locations))
    text = render(results)
    counts = collections.Counter(r.status for r in results)
    print(f"{len(results)} locations: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    for r in results:
        if r.status != "certain":
            print(f"  location {r.index}: {r.status}, byte {r.byte_index}: {r.reason}")
    if args.check:
        with open(args.output, encoding="utf-8") as f:  # CRLF after a Windows checkout does not count as a difference
            same = f.read() == text
        print("unchanged" if same else f"DIFFERENCE from {args.output}")
        return 0 if same else 1
    with open(args.output, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"written: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
