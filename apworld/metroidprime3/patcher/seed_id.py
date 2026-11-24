"""Seed ID in the build info of ``main.dol`` (T18 part 1, write; the client reads it in T18 part 2).

The DOL contains the build string ``!#$MetroidBuildInfo!#$<date> Build <version>``. Bytes 6-22 of it
(``roidBuildInfo!#$`` in the original) are replaced by a 16-byte seed ID. This is pure data: nothing in the game reads
the string (docs/AP_PATCHER_NOTES.md, docs/AP_MEMORY_MAP.md "Layout-UUID"); Randovania's Dolphin connector uses the
same 16 bytes as layout UUID for the other Prime games (``prime_remote_connector.check_for_world_uid``).

Client side (T18 part 2): read ``len(version.build_string)`` bytes at ``version.build_string_address`` from Dolphin
memory and pass them to :func:`seed_id_from_build_string`; compare the result with :func:`make_seed_id` for the
connected room's ``seed_name`` and slot.

Build string addresses: own copy of ``open_prime_rando.dol_patching.corruption.dol_versions.ALL_VERSIONS``
(open-prime-rando 0.15.1, fields ``description``, ``build_string_address``, ``build_string``). PAL checked against the
DOL of RM3P01 (file offset 0x580488 in data section 11) and live in T02.
"""

from __future__ import annotations

import dataclasses
import hashlib
import struct
from pathlib import Path

SEED_ID_OFFSET = 6
SEED_ID_LENGTH = 16


@dataclasses.dataclass(frozen=True)
class DolVersion:
    description: str
    game_id: str
    build_string_address: int
    build_string: bytes

    @property
    def seed_id_address(self) -> int:
        return self.build_string_address + SEED_ID_OFFSET


DOL_VERSIONS = (
    DolVersion("Wii NTSC", "RM3E01", 0x805822B0, b"!#$MetroidBuildInfo!#$2007/07/27 13:13 Build v3.436 (MP3)"),
    DolVersion("Wii PAL", "RM3P01", 0x805843A8, b"!#$MetroidBuildInfo!#$2007/08/24 16:52 Build v3.453 (mp3)"),
    DolVersion("Wii NTSC-J", "RM3J01", 0x80587C2C, b"!#$MetroidBuildInfo!#$2007/11/12 14:15 Build v3.495 (jpn)"),
)

# What bytes 6-22 hold in an unpatched DOL (all versions).
ORIGINAL_SEED_ID_BYTES = b"roidBuildInfo!#$"


def version_for_game_id(game_id: str) -> DolVersion:
    for version in DOL_VERSIONS:
        if version.game_id == game_id:
            return version
    raise ValueError(f"unknown game ID {game_id!r}")


def make_seed_id(seed_name: str, slot: int) -> bytes:
    """Seed ID for an Archipelago slot. Deterministic, so the client can recompute it from the room's seed name."""
    data = f"metroidprime3-ap\0{seed_name}\0{slot}".encode()
    return hashlib.sha256(data).digest()[:SEED_ID_LENGTH]


def _matches_except_seed_id(raw: bytes, version: DolVersion) -> bool:
    expected = version.build_string
    return (
        len(raw) == len(expected)
        and raw[:SEED_ID_OFFSET] == expected[:SEED_ID_OFFSET]
        and raw[SEED_ID_OFFSET + SEED_ID_LENGTH :] == expected[SEED_ID_OFFSET + SEED_ID_LENGTH :]
    )


def seed_id_from_build_string(raw: bytes, version: DolVersion) -> bytes | None:
    """Seed ID from the raw build string (DOL or memory). ``None`` = unpatched (original text).

    Raises ``ValueError`` if ``raw`` is not this version's build string at all (wrong game/version or not loaded).
    """
    raw = bytes(raw)
    if not _matches_except_seed_id(raw, version):
        raise ValueError(f"not the build string of {version.description}: {raw!r}")
    seed_id = raw[SEED_ID_OFFSET : SEED_ID_OFFSET + SEED_ID_LENGTH]
    if seed_id == ORIGINAL_SEED_ID_BYTES:
        return None
    return seed_id


# --- DOL file access ---------------------------------------------------------------------------------------------

_DOL_SECTIONS = 18  # 7 text + 11 data


def dol_offset_for_address(dol: bytes, address: int, length: int = 1) -> int:
    """File offset of a virtual address in a DOL (header: offsets 0x00, addresses 0x48, sizes 0x90)."""
    offsets = struct.unpack_from(f">{_DOL_SECTIONS}I", dol, 0x00)
    addresses = struct.unpack_from(f">{_DOL_SECTIONS}I", dol, 0x48)
    sizes = struct.unpack_from(f">{_DOL_SECTIONS}I", dol, 0x90)
    for offset, start, size in zip(offsets, addresses, sizes):
        if size and start <= address and address + length <= start + size:
            return offset + address - start
    raise ValueError(f"address {address:#x} is not in any DOL section")


def find_version(dol: bytes) -> DolVersion:
    """The DOL version whose build string (bytes 6-22 ignored) sits at its known address."""
    for version in DOL_VERSIONS:
        try:
            offset = dol_offset_for_address(dol, version.build_string_address, len(version.build_string))
        except ValueError:
            continue
        if _matches_except_seed_id(dol[offset : offset + len(version.build_string)], version):
            return version
    raise ValueError("main.dol is none of the known Metroid Prime 3 versions (NTSC-U, PAL, NTSC-J)")


def read_seed_id(dol: bytes) -> tuple[DolVersion, bytes | None]:
    """``(version, seed ID)`` of a DOL; seed ID ``None`` if the DOL is unpatched."""
    version = find_version(dol)
    offset = dol_offset_for_address(dol, version.build_string_address, len(version.build_string))
    return version, seed_id_from_build_string(dol[offset : offset + len(version.build_string)], version)


def write_seed_id(dol: bytearray, seed_id: bytes) -> DolVersion:
    """Write ``seed_id`` into bytes 6-22 of the build string (in place). Overwrites an older seed ID."""
    seed_id = bytes(seed_id)
    if len(seed_id) != SEED_ID_LENGTH:
        raise ValueError(f"seed ID must be {SEED_ID_LENGTH} bytes, got {len(seed_id)}")
    if seed_id == ORIGINAL_SEED_ID_BYTES:
        raise ValueError("seed ID must differ from the original build string bytes")
    version = find_version(dol)
    offset = dol_offset_for_address(dol, version.seed_id_address, SEED_ID_LENGTH)
    dol[offset : offset + SEED_ID_LENGTH] = seed_id
    return version


def read_seed_id_from_dol_file(path: Path) -> tuple[DolVersion, bytes | None]:
    return read_seed_id(Path(path).read_bytes())


def write_seed_id_to_dol_file(path: Path, seed_id: bytes) -> DolVersion:
    path = Path(path)
    dol = bytearray(path.read_bytes())
    version = write_seed_id(dol, seed_id)
    path.write_bytes(dol)
    return version
