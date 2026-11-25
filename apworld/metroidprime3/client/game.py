"""Game state MP3 PAL (RM3P01): ingame vs. menu/loading, current world, inventory key values.

Addresses and pointer chains: docs/AP_MEMORY_MAP.md (sections 1, 2, 6, 7), PAL confirmed live in T02.
"""

from __future__ import annotations

from dataclasses import dataclass

from .memory import MemoryAccess

# PAL version table (AP_MEMORY_MAP.md, table 1)
GAME_STATE_POINTER = 0x80680234
CPLAYER_VTABLE = 0x80595238
CSTATE_MANAGER_GLOBAL = 0x805C7570

# Offsets (AP_MEMORY_MAP.md, table 2)
OFF_STATE_MANAGER_PLAYER_HOLDER = 0x28  # [CSM + 0x28] + 0x2184 = CPlayer*
OFF_CPLAYER = 0x2184
OFF_WORLD_ID = 0x08  # [GSP] + 0x8 = MLVL ID (u64)
OFF_PLAYER_STATE = 0x24  # PS = [[GSP] + 0x24]
OFF_INVENTORY = 0x54
SLOT_SIZE = 0xC

SLOT_POWER_BEAM = 0
SLOT_ITEM_PERCENTAGE = 21

FRONTEND_WORLD_ID = 0xF4A9F72C65FBAE26


def slot_address(player_state: int, slot: int) -> int:
    return player_state + OFF_INVENTORY + slot * SLOT_SIZE


@dataclass(frozen=True)
class GameState:
    ingame: bool
    reason: str = ""  # why not ingame (for status/log)
    world_id: int | None = None
    player_state: int | None = None
    item_percentage: int | None = None  # amount of slot 21
    power_beam_capacity: int = 0
    game_state_pointer: int | None = None  # [0x80680234]; changes on loading, PS stays (T10)

    @property
    def inventory_valid(self) -> bool:
        """Inventory filled (after intro/loading). Before that everything is 0/0 (AP_MEMORY_MAP.md, section 6)."""
        return self.power_beam_capacity > 0


NOT_INGAME_NO_PLAYER = "no CPlayer (menu or loading)"
NOT_INGAME_VTABLE = "CPlayer vtable does not match"
NOT_INGAME_NO_STATE = "no GameState pointer"


def read_game_state(memory: MemoryAccess) -> GameState:
    """Reads only the state pointers. Nothing else is read in the menu or while loading."""
    holder = memory.read_pointer(CSTATE_MANAGER_GLOBAL + OFF_STATE_MANAGER_PLAYER_HOLDER)
    if holder is None:
        return GameState(False, NOT_INGAME_NO_PLAYER)
    cplayer = memory.read_pointer(holder + OFF_CPLAYER)
    if cplayer is None:
        return GameState(False, NOT_INGAME_NO_PLAYER)
    if memory.read_u32(cplayer) != CPLAYER_VTABLE:
        return GameState(False, NOT_INGAME_VTABLE)
    game_state = memory.read_pointer(GAME_STATE_POINTER)
    if game_state is None:
        return GameState(False, NOT_INGAME_NO_STATE)
    world_id = memory.read_u64(game_state + OFF_WORLD_ID)
    if world_id == FRONTEND_WORLD_ID:
        return GameState(False, "FrontEnd (menu)", world_id, game_state_pointer=game_state)
    player_state = memory.read_pointer(game_state + OFF_PLAYER_STATE)
    item_percentage = None
    power_capacity = 0
    if player_state is not None:
        # amount/capacity per slot; ItemPercentage counts every collected pickup (+1)
        item_percentage = memory.read_u32(slot_address(player_state, SLOT_ITEM_PERCENTAGE))
        power_capacity = memory.read_u32(slot_address(player_state, SLOT_POWER_BEAM) + 4)
    return GameState(True, "", world_id, player_state, item_percentage, power_capacity, game_state)
