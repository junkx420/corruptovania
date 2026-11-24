"""Spielzustand MP3 PAL (RM3P01): ingame vs. Menü/Laden, aktuelle Welt, Inventar-Kennwerte.

Adressen und Pointer-Ketten: docs/AP_MEMORY_MAP.md (Abschnitte 1, 2, 6, 7), PAL live bestätigt in T02.
"""

from __future__ import annotations

from dataclasses import dataclass

from .memory import MemoryAccess

# Versionstabelle PAL (AP_MEMORY_MAP.md, Tabelle 1)
GAME_STATE_POINTER = 0x80680234
CPLAYER_VTABLE = 0x80595238
CSTATE_MANAGER_GLOBAL = 0x805C7570

# Offsets (AP_MEMORY_MAP.md, Tabelle 2)
OFF_STATE_MANAGER_PLAYER_HOLDER = 0x28  # [CSM + 0x28] + 0x2184 = CPlayer*
OFF_CPLAYER = 0x2184
OFF_WORLD_ID = 0x08  # [GSP] + 0x8 = MLVL-ID (u64)
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
    reason: str = ""  # warum nicht ingame (für Status/Log)
    world_id: int | None = None
    player_state: int | None = None
    item_percentage: int | None = None  # Anzahl (amount) von Slot 21
    power_beam_capacity: int = 0

    @property
    def inventory_valid(self) -> bool:
        """Inventar befüllt (nach Intro/Laden). Vorher ist alles 0/0 (AP_MEMORY_MAP.md, Abschnitt 6)."""
        return self.power_beam_capacity > 0


NOT_INGAME_NO_PLAYER = "kein CPlayer (Menü oder Laden)"
NOT_INGAME_VTABLE = "CPlayer-vtable passt nicht"
NOT_INGAME_NO_STATE = "kein GameState-Zeiger"


def read_game_state(memory: MemoryAccess) -> GameState:
    """Liest nur die Zustands-Zeiger. Im Menü/Laden wird nichts weiter gelesen."""
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
        return GameState(False, "FrontEnd (Menü)", world_id)
    player_state = memory.read_pointer(game_state + OFF_PLAYER_STATE)
    item_percentage = None
    power_capacity = 0
    if player_state is not None:
        # amount/capacity je Slot; ItemPercentage zählt jeden eingesammelten Pickup (+1)
        item_percentage = memory.read_u32(slot_address(player_state, SLOT_ITEM_PERCENTAGE))
        power_capacity = memory.read_u32(slot_address(player_state, SLOT_POWER_BEAM) + 4)
    return GameState(True, "", world_id, player_state, item_percentage, power_capacity)
