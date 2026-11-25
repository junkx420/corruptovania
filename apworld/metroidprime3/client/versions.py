"""Runtime addresses for the supported Wii releases (docs/AP_MEMORY_MAP.md and docs/AP_NTSC.md)."""

from dataclasses import dataclass

from ..patcher.seed_id import DolVersion, version_for_game_id


@dataclass(frozen=True)
class GameVersion:
    dol: DolVersion
    game_state_pointer: int
    cplayer_vtable: int
    cstate_manager_global: int


VERSIONS = {
    b"RM3P01": GameVersion(version_for_game_id("RM3P01"), 0x80680234, 0x80595238, 0x805C7570),
    b"RM3E01": GameVersion(version_for_game_id("RM3E01"), 0x8067DC0C, 0x80592C78, 0x805C4F70),
}
