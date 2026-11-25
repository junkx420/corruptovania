"""Warn on entry to a Leviathan seed if the core's exit requirements are missing (T26)."""

from dataclasses import dataclass

from ..items import BASE_ID
from .game import GameState, slot_address
from .inventory import GRAPPLE_VOLTAGE, HYPER_BALL, HYPER_GRAPPLE, HYPER_MISSILE, MISSILE
from .memory import MemoryAccess


@dataclass(frozen=True)
class ExitRequirement:
    slot: int
    name: str
    minimum: int = 1


@dataclass(frozen=True)
class SeedExit:
    name: str
    location_id: int
    requirements: tuple[ExitRequirement, ...]


# Exit edges from the three core pickups in randovania/games/prime3/logic_database/* - Seed.txt.
# World IDs are the PAL MLVL IDs from location_flags.py and flag_block.SAVW_INFO.
SEED_EXITS = {
    0xCD79C43EB6C801FD: SeedExit("Bryyo Seed", BASE_ID + 98, (ExitRequirement(HYPER_BALL, "Hyper Ball"),)),
    0x94BCA72AB1CFEC05: SeedExit("SkyTown Elysia Seed", BASE_ID + 97,
                                (ExitRequirement(HYPER_MISSILE, "Hyper Missile"),
                                 ExitRequirement(MISSILE, "Missiles", 4))),
    0xDE97D48188CA8C99: SeedExit("Pirate Homeworld Seed", BASE_ID + 99,
                                (ExitRequirement(HYPER_GRAPPLE, "Hyper Grapple"),
                                 ExitRequirement(GRAPPLE_VOLTAGE, "Grapple Voltage"))),
}
CORE_LOCATIONS = frozenset(seed.location_id for seed in SEED_EXITS.values())


class SeedWarning:
    def __init__(self) -> None:
        self.enabled = True
        self.core_items: dict[int, str | None] = {}  # core location -> item delivered to this slot, if any
        self.reset_visit()

    def reset_visit(self) -> None:
        self._world_id: int | None = None
        self._evaluated = False

    def observe(self, memory: MemoryAccess, state: GameState) -> str | None:
        if state.world_id != self._world_id:
            self._world_id = state.world_id
            self._evaluated = False
        seed = SEED_EXITS.get(state.world_id)
        if not self.enabled or self._evaluated or seed is None or not state.inventory_valid:
            return None
        if state.player_state is None or seed.location_id not in self.core_items:
            return None  # wait for inventory and the scout reply before deciding about this visit

        core_item = self.core_items[seed.location_id]
        missing = []
        for requirement in seed.requirements:
            amount = memory.read_u32(slot_address(state.player_state, requirement.slot))
            if amount < requirement.minimum and requirement.name != core_item:
                missing.append(requirement.name if requirement.minimum == 1
                               else f"at least {requirement.minimum} missiles (have {amount})")
        self._evaluated = True
        if missing:
            return (f"WARNING - LEVIATHAN SEED: {seed.name} exit requires {' and '.join(missing)}. "
                    "Get what you need before fighting the boss, or you may get stuck after the core pickup.")
        return None
