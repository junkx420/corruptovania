"""Search for the 1024-byte flag block of each world in the heap (SPEC E8, docs/AP_LIVE_TESTS.md test D,
docs/AP_SAVW_FORMAT.md 4).

Layout from ``W`` (address of the MLVL ID):

| Offset      | Content                                                                        | checked |
|-------------|--------------------------------------------------------------------------------|---------|
| ``W - 4``   | ``0xEAEAEAEA`` (allocator guard)                                               | yes     |
| ``W + 0x00``| MLVL ID of the world (``u64``)                                                 | yes     |
| ``W + 0x08``| pointer to the resource descriptor: ``"SAVW"`` at +8, SAVW ID (``u64``) at +16 | yes     |
| ``W + 0x10``| pointer to the parsed SAVW object: length of list 1 (``u32``) at +0x10         | yes     |
| ``W + 0x18``| ``0x400`` (number of flags)                                                    | yes     |
| ``W + 0x1C``| 1024 flag bytes, byte ``i`` = memory relay ``i`` of SAVW list 1                |         |

In addition the content must be plausible: bytes from the length of SAVW list 1 onwards must be 0 (there is no memory
relay there). All checks were reproduced on the 22 T10 snapshots (MEM1).

**Findings T10 snapshots (re-evaluated in T06):**
- Every snapshot holds blocks of **all 14 worlds** with locations at the same time, even of worlds never visited
  (content 0). They are told apart by the MLVL ID.
- "Pirate Homeworld - Command" has two blocks with a full header signature from the reload (A4) on: ``0x80A22E20``
  (empty) and ``0x80A11900``, whose bytes 670-1019 are set (the world has only 209 relays) - garbage. The plausibility
  check rejects it.
- Snapshot C1 had a second, fully valid copy per world (``0x811E....``) whose set bytes were a **subset** of the main
  block (Norion: empty). In C2 it was gone.

**Assumption for several valid blocks of a world (checked live in T14):**
The client reads **all** valid, plausible blocks of the current world and merges them with **OR**: a byte counts as set
if it is set in any of them. Reason: within a save, flags are only set, never cleared, and the copies seen were subsets.
Risk: a left-over, still valid block of **another** save could contribute foreign flags. Differences between the blocks
are reported (``FlagRead.disagree``) and logged by the learning mode; ``CheckDetector`` also debounces (2 polls).
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import Callable

from ..location_flags import FLAG_BLOCK_SIZE, WORLD_NAMES
from .memory import MEM1_SIZE, MEM1_START, MemoryAccess, in_ram

GUARD = b"\xEA\xEA\xEA\xEA"
OFF_DESCRIPTOR = 0x08
OFF_SAVW_OBJECT = 0x10
OFF_FLAG_COUNT = 0x18
OFF_FLAGS = 0x1C
HEADER_SIZE = OFF_FLAGS + 4  # read from W - 4: guard + 0x1C header bytes

DESC_FOURCC_OFFSET = 8
DESC_ID_OFFSET = 16
SAVW_OBJECT_LIST1_COUNT = 0x10

# MLVL ID -> (SAVW ID, length of SAVW list 1). From PAL RM3P01: SAVW ID from MLVL + 0x14, list 1 from the SAVW
# (apworld/tools/savw_parser.py, T12). Original ISO and patched ISO are identical.
SAVW_INFO: dict[int, tuple[int, int]] = {
    0x37A9E86F0A0CAF6F: (0x64021D5C7A946BD2, 77),  # G.F.S. Olympus
    0x6FB8EF2A9523C343: (0x732E1A63A1122AD3, 149),  # Norion
    0xC133F919C108BDF9: (0x05630E8EB047656B, 212),  # G.F.S. Valhalla
    0x9BA9292D588D6EB8: (0x0A5262459412C4CF, 155),  # Bryyo - Fire
    0x9F059B53561A9695: (0xBC611ADD6B0E178E, 262),  # Bryyo - Reptilicus
    0xB0D67636D61F3868: (0x6A5A8884EE60529B, 51),  # Bryyo - Ice
    0xC37F4AD853284C78: (0xE504A7A03347426B, 238),  # SkyTown, Elysia - Main
    0xE0F0622642E42CAB: (0x28148FE42065E4EA, 153),  # SkyTown, Elysia - Pod
    0x106F7F4FEFB651D9: (0x44030E5DF215E3F8, 256),  # Pirate Homeworld - Research
    0x38098524EF78B6D2: (0x5821A13F1AE1AB31, 209),  # Pirate Homeworld - Command
    0xDD1C4E18E7291BEF: (0x1ADC831BF2A0B419, 113),  # Pirate Homeworld - Mines
    0x94BCA72AB1CFEC05: (0x3C88ACB252016000, 4),  # SkyTown, Elysia - Seed
    0xCD79C43EB6C801FD: (0xAC4E9456EF4E5822, 6),  # Bryyo - Seed
    0xDE97D48188CA8C99: (0x850046A2CF5AA17D, 6),  # Pirate Homeworld - Seed
}
assert set(SAVW_INFO) == set(WORLD_NAMES)

DEFAULT_SCAN_RANGES: tuple[tuple[int, int], ...] = ((MEM1_START, MEM1_SIZE),)


@dataclass
class FlagRead:
    world_id: int
    flags: bytes  # OR of all valid blocks
    blocks: tuple[int, ...]  # addresses W of the blocks read
    disagree: tuple[int, ...] = ()  # byte indices that differ between the blocks


@dataclass
class _ScanResult:
    time: float
    blocks: dict[int, list[int]] = field(default_factory=dict)


class FlagBlockFinder:
    """Finds and remembers the flag blocks; checks the signature on every poll, rescans on a mismatch."""

    def __init__(self, memory: MemoryAccess, scan_ranges=DEFAULT_SCAN_RANGES, rescan_interval: float = 2.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.memory = memory
        self.scan_ranges = scan_ranges
        self.rescan_interval = rescan_interval
        self.clock = clock
        self.blocks: dict[int, list[int]] = {}
        self.rejected: dict[int, list[int]] = {}  # header signature ok, content implausible (last scan)
        self.last_scan: float | None = None
        self.scan_count = 0
        self.last_scan_seconds = 0.0

    def reset(self) -> None:
        """After menu/loading: forget the addresses (blocks move when loading)."""
        self.blocks = {}
        self.rejected = {}
        self.last_scan = None

    # ---- signature --------------------------------------------------------------------------------------------- #

    def validate(self, address: int, world_id: int) -> bool:
        """Full signature check of the block ``W = address`` for ``world_id``."""
        if address % 4 or not in_ram(address - 4, HEADER_SIZE + FLAG_BLOCK_SIZE):
            return False
        head = self.memory.read(address - 4, HEADER_SIZE)
        if head[0:4] != GUARD:
            return False
        world, descriptor, _, savw_object, _, count = struct.unpack(">QIIIII", head[4:HEADER_SIZE])
        if world != world_id or count != FLAG_BLOCK_SIZE:
            return False
        info = SAVW_INFO.get(world_id)
        if not in_ram(descriptor, DESC_ID_OFFSET + 8) or not in_ram(savw_object, SAVW_OBJECT_LIST1_COUNT + 4):
            return False
        desc = self.memory.read(descriptor, DESC_ID_OFFSET + 8)
        if desc[DESC_FOURCC_OFFSET:DESC_FOURCC_OFFSET + 4] != b"SAVW":
            return False
        if info is not None:
            savw_id, list1_len = info
            if struct.unpack(">Q", desc[DESC_ID_OFFSET:DESC_ID_OFFSET + 8])[0] != savw_id:
                return False
            if self.memory.read_u32(savw_object + SAVW_OBJECT_LIST1_COUNT) != list1_len:
                return False
        return True

    @staticmethod
    def plausible(flags: bytes, world_id: int) -> bool:
        """Nothing may be set behind the last memory relay number of the world."""
        info = SAVW_INFO.get(world_id)
        return info is None or not any(flags[info[1]:])

    # ---- search ------------------------------------------------------------------------------------------------ #

    def scan(self) -> dict[int, list[int]]:
        """Scans MEM1 for the blocks of **all** known worlds (one pass, reads about 24 MiB)."""
        started = time.perf_counter()
        patterns = {world: GUARD + struct.pack(">Q", world) for world in SAVW_INFO}
        candidates: dict[int, set[int]] = {}
        for start, size in self.scan_ranges:
            for base, data in self.memory.iter_chunks(start, size, overlap=len(GUARD) + 8):
                for world, pattern in patterns.items():
                    pos = data.find(pattern)
                    while pos != -1:
                        address = base + pos + len(GUARD)
                        if address % 4 == 0:
                            candidates.setdefault(world, set()).add(address)
                        pos = data.find(pattern, pos + 1)
        self.blocks = {}
        self.rejected = {}
        for world, addrs in candidates.items():
            for address in sorted(addrs):
                if not self.validate(address, world):
                    continue
                if self.plausible(self.memory.read(address + OFF_FLAGS, FLAG_BLOCK_SIZE), world):
                    self.blocks.setdefault(world, []).append(address)
                else:
                    self.rejected.setdefault(world, []).append(address)
        self.last_scan = self.clock()
        self.scan_count += 1
        self.last_scan_seconds = time.perf_counter() - started
        return self.blocks

    def get(self, world_id: int) -> list[int]:
        """Valid blocks of the world. Remembered addresses are checked; if one is missing or invalid: rescan.
        If nothing is found, rescan at most every ``rescan_interval`` seconds."""
        cached = self.blocks.get(world_id)
        if cached:
            if all(self.validate(a, world_id) for a in cached):
                return list(cached)
            self.scan()  # block moved or freed: rescan at once
            return list(self.blocks.get(world_id, []))
        if self.last_scan is None or self.clock() - self.last_scan >= self.rescan_interval:
            self.scan()
        return list(self.blocks.get(world_id, []))

    def read_flags(self, world_id: int) -> FlagRead | None:
        """Reads all valid blocks of the world (merged with OR). The signature is checked again after reading so that
        no block is read that was freed in between."""
        for _attempt in range(2):
            addresses = self.get(world_id)
            if not addresses:
                return None
            datas = [self.memory.read(a + OFF_FLAGS, FLAG_BLOCK_SIZE) for a in addresses]
            if all(self.validate(a, world_id) for a in addresses) and all(
                    self.plausible(d, world_id) for d in datas):
                return _merge(world_id, addresses, datas)
            self.scan()  # block moved, freed or became implausible
        return None


def _merge(world_id: int, addresses: list[int], datas: list[bytes]) -> FlagRead:
    if len(datas) == 1:
        return FlagRead(world_id, datas[0], tuple(addresses))
    merged = bytearray(FLAG_BLOCK_SIZE)
    disagree = []
    for i in range(FLAG_BLOCK_SIZE):
        values = [d[i] for d in datas]
        merged[i] = next((v for v in values if v), 0)
        if any(v != values[0] for v in values):
            disagree.append(i)
    return FlagRead(world_id, bytes(merged), tuple(addresses), tuple(disagree))
