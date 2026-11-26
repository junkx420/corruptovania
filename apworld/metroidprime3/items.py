"""Items of the Metroid Prime 3 APWorld (pool and starting items from data/items.py)."""

from __future__ import annotations

from BaseClasses import Item, ItemClassification

from .data import items as item_data

GAME_NAME = "Metroid Prime 3: Corruption"

# "MP3\0" in ASCII. Location ID = BASE_ID + pickup index (1-99), item ID = BASE_ID + ITEM_OFFSETS[name].
BASE_ID = 0x4D503300  # 1297101568

# Fixed offsets so that item IDs never move when the generated data changes order. New items get the next free
# number appended at the end; never renumber or reuse an entry (test_ids checks every data item has one).
ITEM_OFFSETS: dict[str, int] = {
    # AP pool
    "Progressive Beam": 1,
    "Missile Launcher": 2,
    "Progressive Missile": 3,
    "Grapple Lasso": 4,
    "Grapple Swing": 5,
    "Grapple Voltage": 6,
    "Command Visor": 7,
    "X-Ray Visor": 8,
    "Screw Attack": 9,
    "Hazard Shield": 10,
    "Energy Tank": 11,
    "Boost Ball": 12,
    "Spider Ball": 13,
    "Hypermode": 14,
    "Hyper Missile": 15,
    "Hyper Ball": 16,
    "Hyper Grapple": 17,
    "Ship Grapple": 18,
    "Ship Missile": 19,
    "Missile Expansion": 20,
    "Ship Missile Expansion": 21,
    "Energy Cell 1": 22,
    "Energy Cell 2": 23,
    "Energy Cell 3": 24,
    "Energy Cell 4": 25,
    "Energy Cell 5": 26,
    "Energy Cell 6": 27,
    "Energy Cell 7": 28,
    "Energy Cell 8": 29,
    "Energy Cell 9": 30,
    # starting items (precollected; a removed one goes into the pool instead, E23/T31)
    "Charge Beam": 101,
    "Power Beam": 102,
    "Combat Visor": 103,
    "Scan Visor": 104,
    "Space Jump Boots": 105,
    "Morph Ball": 106,
    "Morph Ball Bombs": 107,
}

FILLER_ITEM_NAME = "Missile Expansion"

POOL: list[dict] = list(item_data.ITEMS)
STARTING: list[dict] = list(item_data.STARTING_ITEMS)
# every item record by name (pool and starting items)
RECORDS: dict[str, dict] = {r["name"]: r for r in POOL + STARTING}

item_name_to_id: dict[str, int] = {name: BASE_ID + ITEM_OFFSETS[name] for name in RECORDS}

item_name_groups: dict[str, set[str]] = {
    "Energy Cells": {r["name"] for r in POOL if r["category"] == "energy_cell"},
}


class MP3Item(Item):
    game = GAME_NAME


def classification(name: str) -> ItemClassification:
    return ItemClassification.progression if RECORDS[name]["progression"] else ItemClassification.filler


def pool_names() -> list[str]:
    """The 99 item names of the AP pool, one entry per copy, in data order."""
    return [r["name"] for r in POOL for _ in range(r["count"])]


def starting_names() -> list[str]:
    return [r["name"] for r in STARTING]


def stage_resources(name: str, copy_index: int) -> list[tuple[str, int]]:
    """Resources the ``copy_index``-th (0-based) copy of an item gives (the last stage repeats)."""
    stages = RECORDS[name]["stages"]
    return [tuple(x) for x in stages[min(copy_index, len(stages) - 1)]]
