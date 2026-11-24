"""Fake-Wii-Speicher für die Client-Tests (T06). Bildet die Pointer-Ketten aus docs/AP_MEMORY_MAP.md nach."""

from __future__ import annotations

import struct

from ..client import flag_block, game
from ..client.memory import MEM1_SIZE, MEM1_START, MemoryAccess, in_ram

# feste Heap-Adressen des Fake-Spiels
HOLDER = 0x80900000
CPLAYER = 0x80B81AE0
GAME_STATE = 0x80800000
PLAYER_STATE = 0x80995B20
DESCRIPTOR_BASE = 0x808C0000
SAVW_OBJECT_BASE = 0x80980000


class FakeMemory(MemoryAccess):
    """MEM1 als ``bytearray``. Zählt alle Lese-/Schreibzugriffe (``reads``, ``writes``)."""

    def __init__(self, game_id: bytes = b"RM3P01") -> None:
        super().__init__()
        self.mem1 = bytearray(MEM1_SIZE)
        self.running = True
        self.hooked = False
        self.fail_reads = False
        self.reads: list[tuple[int, int]] = []
        self.writes: list[tuple[int, bytes]] = []
        self.poke(MEM1_START, game_id)

    # ---- Primitive ---- #
    def _hook(self) -> None:
        self.hooked = self.running

    def _unhook(self) -> None:
        self.hooked = False

    def _is_hooked(self) -> bool:
        return self.hooked

    def _read(self, address: int, size: int) -> bytes:
        if self.fail_reads or not self.running:
            raise RuntimeError("Dolphin weg")
        self.reads.append((address, size))
        if not in_ram(address, size) or address < MEM1_START or address + size > MEM1_START + MEM1_SIZE:
            return bytes(size)  # MEM2 bleibt leer
        o = address - MEM1_START
        return bytes(self.mem1[o:o + size])

    def _write(self, address: int, data: bytes) -> None:
        self.writes.append((address, data))
        self.poke(address, data)

    # ---- Hilfen für Tests (schreiben direkt, ohne Zählung) ---- #
    def poke(self, address: int, data: bytes) -> None:
        o = address - MEM1_START
        self.mem1[o:o + len(data)] = data

    def poke_u32(self, address: int, value: int) -> None:
        self.poke(address, struct.pack(">I", value))

    def poke_u64(self, address: int, value: int) -> None:
        self.poke(address, struct.pack(">Q", value))

    def peek(self, address: int, size: int) -> bytes:
        o = address - MEM1_START
        return bytes(self.mem1[o:o + size])

    # ---- Spielzustand ---- #
    def set_ingame(self, world_id: int, item_percentage: int = 0, power_beam: int = 1) -> None:
        self.poke_u32(game.CSTATE_MANAGER_GLOBAL + game.OFF_STATE_MANAGER_PLAYER_HOLDER, HOLDER)
        self.poke_u32(HOLDER + game.OFF_CPLAYER, CPLAYER)
        self.poke_u32(CPLAYER, game.CPLAYER_VTABLE)
        self.poke_u32(game.GAME_STATE_POINTER, GAME_STATE)
        self.poke_u64(GAME_STATE + game.OFF_WORLD_ID, world_id)
        self.poke_u32(GAME_STATE + game.OFF_PLAYER_STATE, PLAYER_STATE)
        self.set_item_percentage(item_percentage)
        self.poke(game.slot_address(PLAYER_STATE, game.SLOT_POWER_BEAM), struct.pack(">II", power_beam, power_beam))

    def set_menu(self) -> None:
        """Menü/Laden: CPlayer-Zeiger 0 (AP_MEMORY_MAP.md Abschnitt 6)."""
        self.poke_u32(HOLDER + game.OFF_CPLAYER, 0)

    def set_item_percentage(self, value: int) -> None:
        self.poke(game.slot_address(PLAYER_STATE, game.SLOT_ITEM_PERCENTAGE), struct.pack(">II", value, 100 + value))

    # ---- Flag-Block ---- #
    def place_block(self, address: int, world_id: int, flags: bytes | None = None, savw_ok: bool = True) -> int:
        """Legt einen Flag-Block mit voller Signatur an ``W = address`` an."""
        savw_id, list1_len = flag_block.SAVW_INFO[world_id]
        index = sorted(flag_block.SAVW_INFO).index(world_id)
        descriptor = DESCRIPTOR_BASE + index * 0x40
        savw_object = SAVW_OBJECT_BASE + index * 0x60
        self.poke(descriptor + flag_block.DESC_FOURCC_OFFSET, b"SAVW")
        self.poke_u64(descriptor + flag_block.DESC_ID_OFFSET, savw_id if savw_ok else savw_id ^ 1)
        self.poke_u32(savw_object + flag_block.SAVW_OBJECT_LIST1_COUNT, list1_len)
        self.poke(address - 4, flag_block.GUARD)
        self.poke_u64(address, world_id)
        self.poke_u32(address + flag_block.OFF_DESCRIPTOR, descriptor)
        self.poke_u32(address + flag_block.OFF_SAVW_OBJECT, savw_object)
        self.poke_u32(address + flag_block.OFF_FLAG_COUNT, 0x400)
        self.poke(address + flag_block.OFF_FLAGS, flags if flags is not None else bytes(0x400))
        return address

    def set_flag(self, block: int, byte: int, value: int = 1) -> None:
        self.poke(block + flag_block.OFF_FLAGS + byte, bytes([value]))

    def free_block(self, address: int) -> None:
        """Block freigegeben: Kopf überschrieben."""
        self.poke(address - 4, bytes(0x20))

    def move_block(self, old: int, new: int, world_id: int) -> int:
        flags = self.peek(old + flag_block.OFF_FLAGS, 0x400)
        self.free_block(old)
        return self.place_block(new, world_id, flags)
