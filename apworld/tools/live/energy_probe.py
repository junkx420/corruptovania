"""Read PAL RM3P01 Rev 0 energy in PrimeHack. Refill once only on an explicit test command."""

from __future__ import annotations

import argparse
import struct
import time
from dataclasses import dataclass

GAME_STATE_POINTER = 0x80680234
PLAYER_HOLDER_POINTER = 0x805C7570 + 0x28
PLAYER_VTABLE = 0x80595238
BUILD_ADDRESS = 0x805843A8
BUILD = b"!#$MetroidBuildInfo!#$2007/08/24 16:52 Build v3.453 (mp3)"
ENERGY_OFFSET = 0x0C
TANK_OFFSET = 0x144
TANK_LIMIT = 14


@dataclass(frozen=True)
class Sample:
    seed_id: bytes | None
    holder: int
    player: int
    game_state: int
    world: int
    player_state: int
    nearby_energy: float
    energy: float
    energy_bytes: bytes
    slot18: tuple[int, int]
    tanks: tuple[int, int]

    @property
    def maximum(self) -> int:
        return 99 + 100 * self.tanks[0]

    @property
    def identity(self) -> tuple:
        return self.seed_id, self.holder, self.player, self.game_state, self.world, self.player_state

    def describe(self) -> str:
        seed = self.seed_id.hex() if self.seed_id is not None else "vanilla"
        return (f"seed={seed} holder={self.holder:#010x} player={self.player:#010x} "
                f"GS={self.game_state:#010x} world={self.world:#018x} PS={self.player_state:#010x} "
                f"PS+0x08={self.nearby_energy} PS+0x0C={self.energy} ({self.energy_bytes.hex()}) "
                f"slot18={self.slot18[0]}/{self.slot18[1]} slot20={self.tanks[0]}/{self.tanks[1]} "
                f"max_from_tank_amount={self.maximum}")


def read_sample(memory) -> Sample:
    def pointer(address: int, size: int) -> int:
        value, = struct.unpack(">I", memory.read_bytes(address, 4))
        if value % 4 or not 0x80000000 <= value <= 0x81800000 - size:
            raise ValueError(f"No valid MEM1 pointer at {address:#010x}")
        return value

    if memory.read_bytes(0x80000000, 6) != b"RM3P01" or memory.read_bytes(0x80000007, 1) != b"\0":
        raise ValueError("Expected game ID RM3P01, revision 0")
    build = memory.read_bytes(BUILD_ADDRESS, len(BUILD))
    if build[:6] != BUILD[:6] or build[22:] != BUILD[22:]:
        raise ValueError("Unexpected PAL DOL build string")
    seed = None if build == BUILD else build[6:22]
    holder = pointer(PLAYER_HOLDER_POINTER, 0x2188)
    player = pointer(holder + 0x2184, 4)
    if memory.read_bytes(player, 4) != struct.pack(">I", PLAYER_VTABLE):
        raise ValueError("No active CPlayer")
    game_state = pointer(GAME_STATE_POINTER, 0x28)
    world, = struct.unpack(">Q", memory.read_bytes(game_state + 8, 8))
    if world in (0, 0xF4A9F72C65FBAE26):
        raise ValueError("No active world")
    ps = pointer(game_state + 0x24, TANK_OFFSET + 8)
    raw = memory.read_bytes(ps, TANK_OFFSET + 8)
    if struct.unpack_from(">I", raw, 0x58)[0] == 0:
        raise ValueError("Player inventory is still empty")
    nearby, energy = struct.unpack_from(">ff", raw, 8)
    return Sample(seed, holder, player, game_state, world, ps, nearby, energy, raw[ENERGY_OFFSET:ENERGY_OFFSET + 4],
                  struct.unpack_from(">II", raw, 0x12C), struct.unpack_from(">II", raw, TANK_OFFSET))


def refill_once(memory, sample: Sample, args: argparse.Namespace) -> None:
    before_amount, before_capacity = args.before
    amount, capacity = args.after
    if not (0 <= before_amount <= before_capacity < capacity <= TANK_LIMIT and before_amount < amount <= capacity):
        raise ValueError("Expected a valid increase in both Energy Tank amount and capacity")
    if sample.seed_id != args.seed_id or sample.tanks != tuple(args.after):
        raise ValueError("The live AP seed ID or tank read-back differs from the expected value")
    if sample.energy != args.energy or not 0 < sample.energy <= 99 + 100 * before_amount:
        raise ValueError("Live energy must match the expected positive pre-refill value")
    current = read_sample(memory)
    if (current.identity, current.tanks, current.energy_bytes) != (sample.identity, sample.tanks, sample.energy_bytes):
        raise ValueError("Game state changed before the write")

    memory.write_bytes(sample.player_state + ENERGY_OFFSET, struct.pack(">f", sample.maximum))
    result = read_sample(memory)
    print(f"After write: {result.describe()}")
    if (result.identity, result.tanks, result.energy) != (sample.identity, sample.tanks, sample.maximum):
        raise ValueError("The one write could not be confirmed on read-back")


def parse_seed_id(value: str) -> bytes:
    try:
        seed = bytes.fromhex(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected a 32-digit hexadecimal seed ID") from error
    if len(seed) != 16:
        raise argparse.ArgumentTypeError("expected a 32-digit hexadecimal seed ID")
    return seed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("read", help="read the current sample")
    sub.add_parser("watch", help="print changed samples at 0.2 s intervals")
    refill = sub.add_parser("refill", help="write once after a separately observed AP tank delivery in a test save")
    refill.add_argument("--seed-id", type=parse_seed_id, required=True)
    refill.add_argument("--before", type=int, nargs=2, metavar=("AMOUNT", "CAPACITY"), required=True)
    refill.add_argument("--after", type=int, nargs=2, metavar=("AMOUNT", "CAPACITY"), required=True)
    refill.add_argument("--energy", type=float, required=True, help="exact current float from a preceding read")
    args = parser.parse_args()

    import dolphin_memory_engine as memory

    previous = None
    while True:
        try:
            if not memory.is_hooked():
                memory.hook()
            if not memory.is_hooked():
                raise ValueError("PrimeHack/Dolphin is unavailable")
            sample = read_sample(memory)
            message = sample.describe()
            if args.command == "refill":
                print(f"Before write: {message}")
                refill_once(memory, sample, args)
                return
        except (RuntimeError, ValueError) as error:
            if args.command != "watch":
                parser.exit(1, f"{error}\n")
            if isinstance(error, RuntimeError):
                memory.un_hook()
            message = str(error)
        if message != previous:
            print(time.strftime("%H:%M:%S"), message, flush=True)
        if args.command == "read":
            return
        previous = message
        time.sleep(0.2)


if __name__ == "__main__":
    main()
