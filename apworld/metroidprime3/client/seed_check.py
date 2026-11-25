"""Seed check (T18 part 2): does the running ISO belong to the connected slot?

The patch tool writes ``patcher.seed_id.make_seed_id(seed_name, slot)`` into bytes 6-22 of the build string of
``main.dol`` (docs/AP_PATCH_TOOL.md 2.2, PAL RAM ``0x805843AE``). The client reads the build string from RAM
(``seed_id_from_build_string``, the same function the patch tool uses) and compares it with the ID it computes itself
from the server's seed name (``RoomInfo.seed_name``) and its slot. Only with ``OK`` does the client send location checks
and give items. Unpatched ISO (original text in the build string) = ``VANILLA``.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from ..patcher import seed_id as seed_id_module
from .memory import EXPECTED_GAME_ID, MemoryAccess


class SeedStatus(enum.Enum):
    WAITING = "waiting"  # seed/slot not known yet (no server connection)
    OK = "ok"
    MISMATCH = "mismatch"  # ISO of another seed or slot
    VANILLA = "vanilla"  # no seed ID: unpatched ISO or not built with the AP patch tool
    UNREADABLE = "unreadable"  # build string missing/unexpected (game not loaded yet, other DOL)


@dataclass(frozen=True)
class SeedCheckResult:
    status: SeedStatus
    found: bytes | None = None
    expected: bytes | None = None
    seed_name: str | None = None
    slot: int | None = None

    @property
    def ok(self) -> bool:
        return self.status is SeedStatus.OK

    def message(self) -> str:
        found = self.found.hex() if self.found else "-"
        if self.status is SeedStatus.OK:
            return (f"Seed check OK: the ISO belongs to seed {self.seed_name}, slot {self.slot} (ID {found}). "
                    f"Location checks and item giving are active.")
        if self.status is SeedStatus.WAITING:
            return (f"Seed check is waiting for the server connection (ID in the ISO {found}). Until then the client "
                    f"sends no location checks and gives no items.")
        if self.status is SeedStatus.MISMATCH:
            return (f"WRONG ISO: the seed ID in the game ({found}) does not belong to seed {self.seed_name}, "
                    f"slot {self.slot} (expected {self.expected.hex() if self.expected else '-'}). The client sends "
                    f"no location checks and gives no items. Please start the ISO built from this slot's .apmp3.")
        if self.status is SeedStatus.VANILLA:
            return ("NOT AN AP ISO: the game has no seed ID (unpatched ISO or not built with the AP patch tool). The "
                    "client sends no location checks and gives no items. Please start the ISO built from this slot's "
                    ".apmp3.")
        return ("Seed ID not readable (unexpected build info in main.dol). The client sends no location checks and "
                "gives no items.")


class SeedCheck:
    def __init__(self, game_id: bytes = EXPECTED_GAME_ID) -> None:
        self.version = seed_id_module.version_for_game_id(game_id.decode())
        self.result = SeedCheckResult(SeedStatus.WAITING)

    def read_found(self, memory: MemoryAccess) -> tuple[SeedStatus | None, bytes | None]:
        """Seed ID from RAM. ``(None, id)`` = read, otherwise ``(VANILLA|UNREADABLE, None)``."""
        raw = memory.read(self.version.build_string_address, len(self.version.build_string))
        try:
            found = seed_id_module.seed_id_from_build_string(raw, self.version)
        except ValueError:
            return SeedStatus.UNREADABLE, None
        if found is None:
            return SeedStatus.VANILLA, None
        return None, found

    def update(self, memory: MemoryAccess, identity: tuple[str, int] | None) -> SeedCheckResult:
        """``identity`` = ``(seed_name, slot)`` of the server or the last connection, ``None`` = unknown."""
        status, found = self.read_found(memory)
        seed_name, slot = identity if identity else (None, None)
        if status is not None:
            self.result = SeedCheckResult(status, None, None, seed_name, slot)
        elif identity is None:
            self.result = SeedCheckResult(SeedStatus.WAITING, found)
        else:
            expected = seed_id_module.make_seed_id(seed_name, slot)
            status = SeedStatus.OK if found == expected else SeedStatus.MISMATCH
            self.result = SeedCheckResult(status, found, expected, seed_name, slot)
        return self.result

    def reset(self) -> None:
        self.result = SeedCheckResult(SeedStatus.WAITING)
