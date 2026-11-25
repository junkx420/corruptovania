"""Fake Wii memory for the client tests (T06, T07). Mirrors the pointer chains from docs/AP_MEMORY_MAP.md, plus the
inventory (starting inventory as in the AP ISO), the build string with the seed ID (T18) and simple game rules (insert
an energy cell, load a save, reset a value right after it was written)."""

from __future__ import annotations

import struct

from ..client import flag_block, game, inventory
from ..client.memory import MEM1_SIZE, MEM1_START, MemoryAccess, in_ram
from ..patcher import seed_id as seed_id_module

# fixed heap addresses of the fake game
HOLDER = 0x80900000
CPLAYER = 0x80B81AE0
GAME_STATE = 0x80800000
PLAYER_STATE = 0x80995B20
DESCRIPTOR_BASE = 0x808C0000
SAVW_OBJECT_BASE = 0x80980000
GAME_STATE_AFTER_LOAD = 0x80810000  # [0x80680234] after loading (T10: CGameState moves, PS stays)

PAL = seed_id_module.version_for_game_id("RM3P01")

# starting inventory of the AP ISO (starter preset, T01/T19 ``baseline``): (amount, capacity)
START_INVENTORY: dict[int, tuple[int, int]] = {
    **{slot: (1, 1) for slot in (inventory.POWER_BEAM, inventory.CHARGE_BEAM, inventory.BOMB, inventory.COMBAT_VISOR,
                                 inventory.SCAN_VISOR, inventory.SPACE_JUMP, inventory.MORPH_BALL)},
    inventory.SUIT: (0, 6),
    inventory.FUSES: (0, 9),
    **{inventory.FUSE_1 + i: (0, 1) for i in range(9)},
    inventory.FUSES_USED: (0, 9),
    **{inventory.FUSE_1_USED + i: (0, 1) for i in range(9)},
    42: (1, 1),  # HyperModeOriginal
    47: (0, 1),
}


class FakeMemory(MemoryAccess):
    """MEM1 as a ``bytearray``. Counts all reads/writes (``reads``, ``writes``)."""

    def __init__(self, game_id: bytes = b"RM3P01") -> None:
        super().__init__()
        self.mem1 = bytearray(MEM1_SIZE)
        self.running = True
        self.hooked = False
        self.fail_reads = False
        self.reads: list[tuple[int, int]] = []
        self.writes: list[tuple[int, bytes]] = []
        self.revert: dict[int, tuple[int, int]] = {}  # slot -> value the game sets right after a write
        self.poke(MEM1_START, game_id)
        self.set_seed_id(None)

    # ---- primitives ---- #
    def _hook(self) -> None:
        self.hooked = self.running

    def _unhook(self) -> None:
        self.hooked = False

    def _is_hooked(self) -> bool:
        return self.hooked

    def _read(self, address: int, size: int) -> bytes:
        if self.fail_reads or not self.running:
            raise RuntimeError("Dolphin gone")
        self.reads.append((address, size))
        if not in_ram(address, size) or address < MEM1_START or address + size > MEM1_START + MEM1_SIZE:
            return bytes(size)  # MEM2 stays empty
        o = address - MEM1_START
        return bytes(self.mem1[o:o + size])

    def _write(self, address: int, data: bytes) -> None:
        self.writes.append((address, data))
        self.poke(address, data)
        for slot, value in self.revert.items():
            if address == game.slot_address(PLAYER_STATE, slot):
                self.set_slot(slot, *value)

    # ---- helpers for tests (write directly, not counted) ---- #
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

    # ---- seed ID (T18) ---- #
    def set_seed_id(self, seed_id: bytes | None) -> None:
        """Build string of the PAL DOL; ``None`` = unpatched (original text, vanilla ISO)."""
        raw = bytearray(PAL.build_string)
        if seed_id is not None:
            raw[6:22] = seed_id
        self.poke(PAL.build_string_address, bytes(raw))

    # ---- game state ---- #
    def set_ingame(self, world_id: int, item_percentage: int = 0, power_beam: int = 1,
                   game_state: int = GAME_STATE) -> None:
        """Ingame in ``world_id``. If the inventory is empty (new game), the starting inventory is created."""
        self.poke_u32(game.CSTATE_MANAGER_GLOBAL + game.OFF_STATE_MANAGER_PLAYER_HOLDER, HOLDER)
        self.poke_u32(HOLDER + game.OFF_CPLAYER, CPLAYER)
        self.poke_u32(CPLAYER, game.CPLAYER_VTABLE)
        self.poke_u32(game.GAME_STATE_POINTER, game_state)
        self.poke_u64(game_state + game.OFF_WORLD_ID, world_id)
        self.poke_u32(game_state + game.OFF_PLAYER_STATE, PLAYER_STATE)
        if power_beam and not any(self.peek(game.slot_address(PLAYER_STATE, 0), inventory.INVENTORY_SIZE)):
            for slot, value in START_INVENTORY.items():
                self.set_slot(slot, *value)
        self.set_item_percentage(item_percentage)
        self.poke(game.slot_address(PLAYER_STATE, game.SLOT_POWER_BEAM), struct.pack(">II", power_beam, power_beam))

    # ---- inventory ---- #
    def slot(self, slot: int) -> tuple[int, int]:
        return struct.unpack(">II", self.peek(game.slot_address(PLAYER_STATE, slot), 8))

    def set_slot(self, slot: int, amount: int, capacity: int) -> None:
        self.poke(game.slot_address(PLAYER_STATE, slot), struct.pack(">II", amount, capacity))

    def inventory(self) -> dict[int, tuple[int, int]]:
        return inventory.parse_inventory(self.peek(game.slot_address(PLAYER_STATE, 0), inventory.INVENTORY_SIZE))

    def save(self) -> bytes:
        """Save = inventory (all the test needs; death/continue loads it back byte for byte, T15)."""
        return self.peek(game.slot_address(PLAYER_STATE, 0), inventory.INVENTORY_SIZE)

    def load(self, save: bytes, world_id: int) -> None:
        """Load a save or death + continue: inventory = save, new CGameState pointer (T10). The loading phase
        (CPlayer 0) is simulated by the test itself with ``set_menu`` + a poll when it needs one."""
        current = struct.unpack(">I", self.peek(game.GAME_STATE_POINTER, 4))[0]
        game_state = GAME_STATE_AFTER_LOAD if current == GAME_STATE else GAME_STATE
        self.poke(game.slot_address(PLAYER_STATE, 0), save)
        self.set_ingame(world_id, item_percentage=self.slot(game.SLOT_ITEM_PERCENTAGE)[0], game_state=game_state)

    def use_cell(self, cell: int) -> None:
        """Insert an energy cell at a terminal (T15): 22 and Fuse_i amount -1, 52 and Fuse_iUsed amount +1."""
        fuse = inventory.FUSE_1 + cell - 1
        assert self.slot(fuse)[0] == 1, f"cell {cell} not held"
        a, c = self.slot(inventory.FUSES)
        self.set_slot(inventory.FUSES, a - 1, c)
        self.set_slot(fuse, 0, self.slot(fuse)[1])
        a, c = self.slot(inventory.FUSES_USED)
        self.set_slot(inventory.FUSES_USED, a + 1, c)
        self.set_slot(inventory.FUSE_1_USED + cell - 1, 1, 1)

    def set_menu(self) -> None:
        """Menu/loading: CPlayer pointer 0 (AP_MEMORY_MAP.md section 6)."""
        self.poke_u32(HOLDER + game.OFF_CPLAYER, 0)

    def set_item_percentage(self, value: int) -> None:
        self.poke(game.slot_address(PLAYER_STATE, game.SLOT_ITEM_PERCENTAGE), struct.pack(">II", value, 100 + value))

    # ---- flag block ---- #
    def place_block(self, address: int, world_id: int, flags: bytes | None = None, savw_ok: bool = True) -> int:
        """Places a flag block with the full signature at ``W = address``."""
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
        """Block freed: header overwritten."""
        self.poke(address - 4, bytes(0x20))

    def move_block(self, old: int, new: int, world_id: int) -> int:
        flags = self.peek(old + flag_block.OFF_FLAGS, 0x400)
        self.free_block(old)
        return self.place_block(new, world_id, flags)
