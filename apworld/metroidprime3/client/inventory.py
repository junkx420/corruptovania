"""Item giving (T07): effect table item -> inventory slots and target/current comparison (SPEC E9, E11).

Inventory: ``PS + 0x54 + slot*0xC``, per slot ``u32 amount, u32 capacity, u32 ?`` (big endian), ``PS = [[0x80680234]+0x24]``
(docs/AP_MEMORY_MAP.md 3). The client only writes amount and capacity, never the third word.

**Origin of the data** (own copy, nothing of it is read at runtime):

- Slot per resource: Randovania ``randovania/games/prime3/logic_database/header.json``, ``resource_database.items``
  (``long_name`` -> ``extra.item_id``), = docs/AP_MEMORY_MAP.md section 3.
- Amounts per pickup (capacity/amount increase): MP3Randomizer ``tools/prime3_patcher/MP3Randomizer/MP3Randomizer/Item.cs``
  (``capacity``/``amount`` per ``ItemName``): Missile Launcher/Expansion +5, Ship Missile +3, Ship Missile Expansion +1,
  Suit +5, everything else +1.
- Stages and launcher lock per item: ``data/items.py`` (converter T03 from Randovania's
  ``randovania/games/prime3/pickup_database/pickup-database.json``: ``progression`` list = stages, ``ammo``/
  ``unlocked_by`` = lock).
- Limit and bit width per slot: docs/AP_SLOT_LIMITS.md section 4 (DOL table ``0x8057D5F8``, = ``max_capacity``).
- Special rules: docs/AP_SLOT_LIMITS.md 6 (suit, energy cells, missile/energy tank), docs/AP_LIVE_TESTS_T11.md
  (write slot 22 too, slot 36 for the hypermode menu), docs/AP_LIVE_TESTS.md test C (slot 68 = locked missiles).

``test/test_client_items.py`` checks the table against ``data/items.py`` (all 99 pool items and the starting items), and
in a repo checkout also against ``header.json`` and the CSV in docs/AP_SLOT_LIMITS.md.

**Target** (E11): computed absolutely from starting items + all received items (``compute_targets``), never from a
stored index. **Writing** (``plan_writes``) only raises and clamps to the slot limit; exceptions:

| Rule | Slots | Behaviour |
|---|---|---|
| ``raise`` | abilities (1 bit) | amount and capacity each to at least the target |
| ``ammo`` | 4 Missile, 20 Energy Tank, 45 Ship Missile | only if capacity < target: capacity = target, raise amount by the same difference (consumption stays) |
| ``suit`` | 17 | Hazard Shield fixed 5/6 (amount is an index, 13 freezes; capacity > 7 breaks on saving). Amount 5-7 and capacity 6-7 are left alone |
| ``cell`` | 22-31 | cell i: amount 1 while received and not inserted (slot 52+i), otherwise nothing; slot 22 = received minus inserted cells. Only raise |
| ``exact`` | 68 | locked missile expansions: 5 per expansion without launcher, 0 with launcher (moved to slot 4) |
"""

from __future__ import annotations

import struct
from collections import Counter
from dataclasses import dataclass
from typing import Collection, Iterable, Mapping, Sequence

from .game import SLOT_SIZE, slot_address

SLOT_COUNT = 70  # slots 0-69 (``add_power_up``: ``cmplwi r4,0x45``, AP_PATCHER_NOTES.md 2.2)
INVENTORY_SIZE = SLOT_COUNT * SLOT_SIZE

# ---- slots (header.json ``item_id``, names as in the DOL table, AP_SLOT_LIMITS.md 1) --------------------------- #
POWER_BEAM = 0
PLASMA_BEAM = 1
NOVA_BEAM = 2
CHARGE_BEAM = 3
MISSILE = 4
ICE_MISSILE = 5
SEEKER_MISSILE = 6
GRAPPLE_LASSO = 7
GRAPPLE_SWING = 8
GRAPPLE_VOLTAGE = 9
BOMB = 10
COMBAT_VISOR = 11
SCAN_VISOR = 12
COMMAND_VISOR = 13
XRAY_VISOR = 14
SPACE_JUMP = 15
SCREW_ATTACK = 16
SUIT = 17
ENERGY_TANK = 20
ITEM_PERCENTAGE = 21
FUSES = 22  # energy cells total (amount = cells held, capacity fixed 9)
FUSE_1 = 23  # Fuse1 .. Fuse9 = 23 .. 31
MORPH_BALL = 32
BOOST_BALL = 33
SPIDER_BALL = 34
HYPER_TANK = 35
HYPER_BEAM = 36  # no pickup; unlocks the "Hypermode" menu category (T11)
HYPER_MISSILE = 37
HYPER_BALL = 38
HYPER_GRAPPLE = 39
SHIP_GRAPPLE = 44
SHIP_MISSILE = 45
FUSES_USED = 52
FUSE_1_USED = 53  # Fuse1Used .. Fuse9Used = 53 .. 61 (amount 1 = cell inserted, T15)
LOCKED_MISSILES = 68  # Stat_TinCanHighScore: load of locked missile expansions (T10 test C)

ENERGY_CELLS = 9
FUSES_CAPACITY = 9
SUIT_AMOUNT = 5  # Hazard Shield (Item.cs +5, T11: 5 works)
SUIT_CAPACITY = 6  # starting capacity = table maximum
SUIT_MAX_VALID = 7  # 3 bits in the save; amount 13 freezes live (T19), 6/7 as amount not tested

START_INVENTORY_LOCATION = -2  # how MultiServer sends the starting inventory (precollected items) with items_handling & 0b100


@dataclass(frozen=True)
class SlotLimit:
    name: str
    tab_max: int  # maximum of the DOL table (= header.json ``max_capacity``)
    bits: int  # bits per field in the save (0 = slot is not saved)

    @property
    def limit(self) -> int:
        """Largest value the client writes: table maximum, at most ``2^bits - 1`` (survives saving)."""
        return min(self.tab_max, (1 << self.bits) - 1)


# docs/AP_SLOT_LIMITS.md section 4 (columns name, tab_max, bits_capacity = bits_amount)
SLOT_LIMITS: dict[int, SlotLimit] = {
    0: SlotLimit("PowerBeam", 1, 1),
    1: SlotLimit("PlasmaBeam", 1, 1),
    2: SlotLimit("NovaBeam", 1, 1),
    3: SlotLimit("ChargeUpgrade", 1, 1),
    4: SlotLimit("Missile", 255, 8),
    5: SlotLimit("IceMissile", 1, 1),
    6: SlotLimit("SeekerMissile", 1, 1),
    7: SlotLimit("GrappleBeamPull", 1, 1),
    8: SlotLimit("GrappleBeamSwing", 1, 1),
    9: SlotLimit("GrappleBeamVoltage", 1, 1),
    10: SlotLimit("Bomb", 1, 1),
    11: SlotLimit("CombatVisor", 1, 1),
    12: SlotLimit("ScanVisor", 1, 1),
    13: SlotLimit("CommandVisor", 1, 1),
    14: SlotLimit("XRayVisor", 1, 1),
    15: SlotLimit("DoubleJump", 1, 1),
    16: SlotLimit("ScrewAttack", 1, 1),
    17: SlotLimit("SuitType", 6, 3),
    20: SlotLimit("EnergyTank", 14, 4),
    21: SlotLimit("ItemPercentage", 255, 8),
    22: SlotLimit("Fuses", 9, 4),
    **{FUSE_1 + i: SlotLimit(f"Fuse{i + 1}", 1, 1) for i in range(ENERGY_CELLS)},
    32: SlotLimit("MorphBall", 1, 1),
    33: SlotLimit("BoostBall", 1, 1),
    34: SlotLimit("SpiderBall", 1, 1),
    35: SlotLimit("HyperModeTank", 1, 1),
    36: SlotLimit("HyperModeBeam", 1, 1),
    37: SlotLimit("HyperModeMissile", 1, 1),
    38: SlotLimit("HyperModeBall", 1, 1),
    39: SlotLimit("HyperModeGrapple", 1, 1),
    43: SlotLimit("HyperModeCharge", 1, 1),
    44: SlotLimit("ShipGrapple", 1, 1),
    45: SlotLimit("ShipMissile", 11, 4),
    47: SlotLimit("PhazonBall", 1, 0),
    52: SlotLimit("FusesUsed", 9, 4),
    **{FUSE_1_USED + i: SlotLimit(f"Fuse{i + 1}Used", 1, 1) for i in range(ENERGY_CELLS)},
    68: SlotLimit("Stat_TinCanHighScore", 99999, 17),
    69: SlotLimit("Stat_TinCanCurrentScore", 99999, 0),
}

# slots the client never writes (game state/counters, not saved or with a game meaning)
READ_ONLY_SLOTS = frozenset({ITEM_PERCENTAGE, 40, 41, 42, 43, 47, FUSES_USED, 69,  # 40-42 story hyper (41: goal, T17)
                             *range(FUSE_1_USED, FUSE_1_USED + ENERGY_CELLS)})

# logic resource (``long_name`` in header.json, names in data/items.py ``stages``) -> slot (``extra.item_id``)
RESOURCE_SLOTS: dict[str, int] = {
    "Power Beam": POWER_BEAM,
    "Plasma Beam": PLASMA_BEAM,
    "Nova Beam": NOVA_BEAM,
    "Charge Beam": CHARGE_BEAM,
    "Missile": MISSILE,
    "Ice Missile": ICE_MISSILE,
    "Seeker Missile": SEEKER_MISSILE,
    "Grapple Lasso": GRAPPLE_LASSO,
    "Grapple Swing": GRAPPLE_SWING,
    "Grapple Voltage": GRAPPLE_VOLTAGE,
    "Morph Ball Bomb": BOMB,
    "Combat Visor": COMBAT_VISOR,
    "Scan Visor": SCAN_VISOR,
    "Command Visor": COMMAND_VISOR,
    "X-Ray Visor": XRAY_VISOR,
    "Space Jump Boots": SPACE_JUMP,
    "Screw Attack": SCREW_ATTACK,
    "Suit Type": SUIT,
    "Energy Tank": ENERGY_TANK,
    "Energy Cells Total": FUSES,
    **{f"Energy Cell {i + 1}": FUSE_1 + i for i in range(ENERGY_CELLS)},
    "Morph Ball": MORPH_BALL,
    "Boost Ball": BOOST_BALL,
    "Spider Ball": SPIDER_BALL,
    "HyperModeTank": HYPER_TANK,
    "Hyper Missile": HYPER_MISSILE,
    "Hyper Ball": HYPER_BALL,
    "Hyper Grapple": HYPER_GRAPPLE,
    "Ship Grapple": SHIP_GRAPPLE,
    "Ship Missile": SHIP_MISSILE,
}

RULE_RAISE = "raise"
RULE_AMMO = "ammo"
RULE_SUIT = "suit"
RULE_CELL = "cell"
RULE_EXACT = "exact"

SLOT_RULES: dict[int, str] = {
    MISSILE: RULE_AMMO,
    ENERGY_TANK: RULE_AMMO,
    SHIP_MISSILE: RULE_AMMO,
    SUIT: RULE_SUIT,
    FUSES: RULE_CELL,
    **{FUSE_1 + i: RULE_CELL for i in range(ENERGY_CELLS)},
    LOCKED_MISSILES: RULE_EXACT,
}

# display names for the log and /inventory
SLOT_LABELS: dict[int, str] = {
    POWER_BEAM: "Power Beam", PLASMA_BEAM: "Plasma Beam", NOVA_BEAM: "Nova Beam", CHARGE_BEAM: "Charge Beam",
    MISSILE: "Missiles", ICE_MISSILE: "Ice Missile", SEEKER_MISSILE: "Seeker Missile", GRAPPLE_LASSO: "Grapple Lasso",
    GRAPPLE_SWING: "Grapple Swing", GRAPPLE_VOLTAGE: "Grapple Voltage", BOMB: "Morph Ball Bombs",
    COMBAT_VISOR: "Combat Visor", SCAN_VISOR: "Scan Visor", COMMAND_VISOR: "Command Visor", XRAY_VISOR: "X-Ray Visor",
    SPACE_JUMP: "Space Jump Boots", SCREW_ATTACK: "Screw Attack", SUIT: "Suit", ENERGY_TANK: "Energy Tanks",
    ITEM_PERCENTAGE: "ItemPercentage", FUSES: "Energy Cells total",
    **{FUSE_1 + i: f"Energy Cell {i + 1}" for i in range(ENERGY_CELLS)},
    MORPH_BALL: "Morph Ball", BOOST_BALL: "Boost Ball", SPIDER_BALL: "Spider Ball", HYPER_TANK: "Hypermode",
    HYPER_BEAM: "Hyper Beam (Hypermode menu)", HYPER_MISSILE: "Hyper Missile", HYPER_BALL: "Hyper Ball",
    HYPER_GRAPPLE: "Hyper Grapple", SHIP_GRAPPLE: "Ship Grapple", SHIP_MISSILE: "Ship Missiles",
    LOCKED_MISSILES: "locked missiles (slot 68)",
}


def slot_limit(slot: int) -> int:
    return SLOT_LIMITS[slot].limit


def slot_label(slot: int) -> str:
    return SLOT_LABELS.get(slot) or (SLOT_LIMITS[slot].name if slot in SLOT_LIMITS else f"slot {slot}")


# ---- effect table ---------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Grant:
    """Increase one copy gives in a slot, the way a real pickup does (Item.cs)."""
    slot: int
    capacity: int = 1
    amount: int = 1


@dataclass(frozen=True)
class ItemEffect:
    stages: tuple[tuple[Grant, ...], ...]  # the n-th copy gives stage n, the last one applies to all further copies
    locked_by: str | None = None  # launcher lock (E15): ammo only counts once this item is held
    locked_slot: int | None = None  # where locked ammo is booked (slot 68); None = nowhere
    also: tuple[Grant, ...] = ()  # additionally per copy (no pickup slot of its own, e.g. slot 36)
    energy_cell: int | None = None  # Energy Cell 1-9: special rule ``cell``
    note: str = ""  # difference to data/items.py or origin


def _single(slot: int, capacity: int = 1, amount: int | None = None) -> tuple[tuple[Grant, ...], ...]:
    return ((Grant(slot, capacity, capacity if amount is None else amount),),)


_HYPER_MENU = (Grant(HYPER_BEAM),)

ITEM_EFFECTS: dict[str, ItemEffect] = {
    # AP pool (data/items.py ITEMS)
    "Progressive Beam": ItemEffect(((Grant(PLASMA_BEAM),), (Grant(NOVA_BEAM),)),
                                   note="stages: Plasma Beam, then Nova Beam (pickup-database progression)"),
    "Missile Launcher": ItemEffect(_single(MISSILE, 5), note="Item.cs MissileLauncher +5/+5, opens the lock"),
    "Progressive Missile": ItemEffect(((Grant(ICE_MISSILE),), (Grant(SEEKER_MISSILE),)),
                                      note="stages: Ice Missile, then Seeker Missile"),
    "Grapple Lasso": ItemEffect(_single(GRAPPLE_LASSO)),
    "Grapple Swing": ItemEffect(_single(GRAPPLE_SWING)),
    "Grapple Voltage": ItemEffect(_single(GRAPPLE_VOLTAGE)),
    "Command Visor": ItemEffect(_single(COMMAND_VISOR)),
    "X-Ray Visor": ItemEffect(_single(XRAY_VISOR)),
    "Screw Attack": ItemEffect(_single(SCREW_ATTACK)),
    "Hazard Shield": ItemEffect(_single(SUIT, 5),
                                note="logic: Suit Type 1; Item.cs Suit +5/+5. The client writes fixed 5/6 (rule suit)"),
    "Energy Tank": ItemEffect(_single(ENERGY_TANK)),
    "Boost Ball": ItemEffect(_single(BOOST_BALL)),
    "Spider Ball": ItemEffect(_single(SPIDER_BALL)),
    "Hypermode": ItemEffect(_single(HYPER_TANK), also=_HYPER_MENU, note="+ slot 36 (Hypermode menu, T11)"),
    "Hyper Missile": ItemEffect(_single(HYPER_MISSILE), also=_HYPER_MENU, note="+ slot 36"),
    "Hyper Ball": ItemEffect(_single(HYPER_BALL), also=_HYPER_MENU, note="+ slot 36"),
    "Hyper Grapple": ItemEffect(_single(HYPER_GRAPPLE), also=_HYPER_MENU, note="+ slot 36"),
    "Ship Grapple": ItemEffect(_single(SHIP_GRAPPLE)),
    "Ship Missile": ItemEffect(_single(SHIP_MISSILE, 3), note="Item.cs ShipMissile +3/+3, opens the lock"),
    "Missile Expansion": ItemEffect(_single(MISSILE, 5), locked_by="Missile Launcher", locked_slot=LOCKED_MISSILES,
                                    note="Item.cs +5/+5; without launcher in slot 68 (T10 test C)"),
    "Ship Missile Expansion": ItemEffect(_single(SHIP_MISSILE, 1), locked_by="Ship Missile",
                                         note="Item.cs +1/+1; without Ship Missile nowhere (slot 69 is not saved)"),
    **{f"Energy Cell {i + 1}": ItemEffect(((Grant(FUSE_1 + i), Grant(FUSES, 0, 1)),), energy_cell=i + 1,
                                          note="rule cell: slot 22 as counter, an inserted cell (slot 52+i) is never "
                                               "given again")
       for i in range(ENERGY_CELLS)},
    # starting items (data/items.py STARTING_ITEMS; the ISO already has them, the client only raises missing ones)
    "Charge Beam": ItemEffect(_single(CHARGE_BEAM)),
    "Power Beam": ItemEffect(_single(POWER_BEAM)),
    "Combat Visor": ItemEffect(_single(COMBAT_VISOR)),
    "Scan Visor": ItemEffect(_single(SCAN_VISOR)),
    "Space Jump Boots": ItemEffect(_single(SPACE_JUMP)),
    "Morph Ball": ItemEffect(_single(MORPH_BALL)),
    "Morph Ball Bombs": ItemEffect(_single(BOMB)),
}


# ---- targets --------------------------------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SlotTarget:
    slot: int
    amount: int
    capacity: int
    rule: str
    sources: tuple[str, ...] = ()


def effective_items(starting: Iterable[str], received: Iterable[tuple[str, int]]) -> list[str]:
    """All items that count: received ``(name, location ID)`` plus the starting items from ``slot_data``.

    With ``items_handling = 0b111`` the server itself sends the precollected starting items as starting inventory
    (location -2). A starting item therefore only counts as far as it was not already received that way (else twice).
    """
    received = list(received)
    from_server = Counter(name for name, location in received if location == START_INVENTORY_LOCATION)
    base = Counter(starting) - from_server
    return list(base.elements()) + [name for name, _ in received]


def used_cells(inventory: Mapping[int, tuple[int, int]]) -> set[int]:
    """Inserted energy cells (1-9): amount of Fuse_iUsed (slot 52+i) > 0 (T15)."""
    return {i + 1 for i in range(ENERGY_CELLS) if inventory.get(FUSE_1_USED + i, (0, 0))[0] > 0}


def compute_targets(items: Sequence[str], cells_used: Collection[int] = ()) -> dict[int, SlotTarget]:
    """Target per slot from all counting items (``effective_items``). Unknown names are skipped."""
    held = set(items)
    copies: Counter[str] = Counter()
    acc: dict[int, list] = {}  # slot -> [amount, capacity, sources]
    cells: set[int] = set()
    locked_seen = False

    def add(slot: int, grant: Grant, source: str) -> None:
        entry = acc.setdefault(slot, [0, 0, []])
        entry[0] += grant.amount
        entry[1] += grant.capacity
        if source not in entry[2]:
            entry[2].append(source)

    for name in items:
        effect = ITEM_EFFECTS.get(name)
        if effect is None:
            continue
        index = copies[name]
        copies[name] += 1
        if effect.energy_cell is not None:
            cells.add(effect.energy_cell)
            continue
        stage = effect.stages[min(index, len(effect.stages) - 1)]
        if effect.locked_slot is not None:
            locked_seen = True
        if effect.locked_by is not None and effect.locked_by not in held:
            if effect.locked_slot is not None:
                for grant in stage:
                    add(effect.locked_slot, grant, name)
            continue
        for grant in stage + effect.also:
            add(grant.slot, grant, name)

    targets: dict[int, SlotTarget] = {}
    for slot, (amount, capacity, sources) in acc.items():
        rule = SLOT_RULES.get(slot, RULE_RAISE)
        if rule == RULE_SUIT:
            amount, capacity = SUIT_AMOUNT, SUIT_CAPACITY
        limit = slot_limit(slot)
        targets[slot] = SlotTarget(slot, min(amount, limit), min(capacity, limit), rule, tuple(sources))
    if locked_seen and LOCKED_MISSILES not in targets:
        # launcher held: the locked load has been moved to slot 4, slot 68 is empty (like the game does, T10)
        targets[LOCKED_MISSILES] = SlotTarget(LOCKED_MISSILES, 0, 0, RULE_EXACT, ("Missile Launcher",))
    if cells:
        available = 0
        for cell in sorted(cells):
            have = 0 if cell in cells_used else 1
            available += have
            slot = FUSE_1 + cell - 1
            targets[slot] = SlotTarget(slot, have, 1, RULE_CELL, (f"Energy Cell {cell}",))
        targets[FUSES] = SlotTarget(FUSES, available, FUSES_CAPACITY, RULE_CELL,
                                    tuple(f"Energy Cell {c}" for c in sorted(cells)))
    return targets


# ---- write plan ------------------------------------------------------------------------------------------------ #

@dataclass(frozen=True)
class SlotWrite:
    slot: int
    old: tuple[int, int]  # (amount, capacity) before
    new: tuple[int, int]
    sources: tuple[str, ...] = ()

    def describe(self) -> str:
        return f"{slot_label(self.slot)} {self.old[0]}/{self.old[1]} -> {self.new[0]}/{self.new[1]}"


def desired_value(target: SlotTarget, current: tuple[int, int]) -> tuple[int, int]:
    """Value the slot should have after the comparison (= ``current`` if there is nothing to write)."""
    amount, capacity = current
    limit = slot_limit(target.slot)
    if target.rule == RULE_EXACT:
        return target.amount, target.capacity
    if target.rule == RULE_AMMO:
        if capacity >= target.capacity:
            return current  # capacity is enough; a lower amount is consumption
        delta = target.capacity - capacity
        return min(max(amount, 0) + delta, target.capacity), target.capacity
    if target.rule == RULE_SUIT:
        new_amount = amount if amount >= SUIT_AMOUNT else SUIT_AMOUNT  # 5-7 stays (story suit?), never write > 7
        new_capacity = capacity if SUIT_CAPACITY <= capacity <= SUIT_MAX_VALID else SUIT_CAPACITY
        return new_amount, new_capacity
    # raise, cell: each field to at least the target
    new_amount = amount if amount >= target.amount else target.amount
    new_capacity = capacity if capacity >= target.capacity else target.capacity
    if (new_amount, new_capacity) == current:
        return current
    return min(new_amount, limit), min(new_capacity, limit)


def plan_writes(targets: Mapping[int, SlotTarget], inventory: Mapping[int, tuple[int, int]]) -> list[SlotWrite]:
    writes = []
    for slot in sorted(targets):
        if slot in READ_ONLY_SLOTS:
            raise ValueError(f"slot {slot} must not be written")
        current = inventory.get(slot, (0, 0))
        new = desired_value(targets[slot], current)
        if new != current:
            writes.append(SlotWrite(slot, current, new, targets[slot].sources))
    return writes


# ---- memory ---------------------------------------------------------------------------------------------------- #

def parse_inventory(raw: bytes) -> dict[int, tuple[int, int]]:
    """``{slot: (amount, capacity)}`` for all 70 slots from ``INVENTORY_SIZE`` bytes at ``PS + 0x54``."""
    return {slot: struct.unpack_from(">II", raw, slot * SLOT_SIZE) for slot in range(SLOT_COUNT)}


def read_inventory(memory, player_state: int) -> dict[int, tuple[int, int]]:
    return parse_inventory(memory.read(slot_address(player_state, 0), INVENTORY_SIZE))


def write_slot(memory, player_state: int, slot: int, value: tuple[int, int]) -> None:
    """Writes amount and capacity (8 bytes), the third word stays. ``memory.write`` checks the game ID."""
    if slot in READ_ONLY_SLOTS or slot not in SLOT_LIMITS:
        raise ValueError(f"slot {slot} must not be written")
    amount, capacity = value
    memory.write(slot_address(player_state, slot), struct.pack(">II", amount, capacity))
