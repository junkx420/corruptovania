"""Archipelago world for Metroid Prime 3: Corruption (MVP, SPEC E3).

Logic, items and locations come from the generated data in ``data/`` (apworld/tools/convert_db.py). Nothing here
imports randovania (SPEC 3a). Developer notes: docs/AP_APWORLD_DEV.md.
"""

from __future__ import annotations

from typing import Any, ClassVar

from BaseClasses import Item
from worlds.AutoWorld import WebWorld, World

from .data import game as game_data
from .items import (BASE_ID, FILLER_ITEM_NAME, GAME_NAME, ITEM_OFFSETS, RECORDS, MP3Item, classification,
                    item_name_groups, item_name_to_id, pool_names, starting_names)
from .locations import LOCATIONS, location_name_groups, location_name_to_id
from .options import MP3Options
from .regions import GOAL_EVENT, create_regions, starting_resources

SLOT_DATA_VERSION = 1


class MP3Web(WebWorld):
    tutorials = []  # setup guide follows with the client (T06/T07); dev notes: docs/AP_APWORLD_DEV.md


class MP3World(World):
    """Metroid Prime 3: Corruption. Samus Aran fights the Phazon corruption across planets and Leviathans."""

    game = GAME_NAME
    web = MP3Web()
    options_dataclass = MP3Options
    options: MP3Options
    topology_present = True

    item_name_to_id: ClassVar[dict[str, int]] = item_name_to_id
    location_name_to_id: ClassVar[dict[str, int]] = location_name_to_id
    item_name_groups = item_name_groups
    location_name_groups = location_name_groups

    def create_item(self, name: str) -> Item:
        return MP3Item(name, classification(name), self.item_name_to_id[name], self.player)

    def get_filler_item_name(self) -> str:
        return FILLER_ITEM_NAME

    def create_regions(self) -> None:
        create_regions(self)

    def create_items(self) -> None:
        for name in starting_names():
            self.multiworld.push_precollected(self.create_item(name))
        self.multiworld.itempool += [self.create_item(name) for name in pool_names()]

    def set_rules(self) -> None:
        player = self.player
        self.multiworld.completion_condition[player] = lambda state: state.has(GOAL_EVENT, player)

    def fill_slot_data(self) -> dict[str, Any]:
        """Everything the client needs to compute the target inventory (E11). Format: docs/AP_APWORLD_DEV.md."""
        return {
            "slot_data_version": SLOT_DATA_VERSION,
            "seed_name": self.multiworld.seed_name,
            "base_id": BASE_ID,
            "goal_event": GOAL_EVENT,
            "start_location": list(game_data.START_LOCATION),
            "starting_items": starting_names(),
            "starting_resources": starting_resources(),
            "items": {
                name: {
                    "id": BASE_ID + ITEM_OFFSETS[name],
                    "stages": [[[resource, qty] for resource, qty in stage] for stage in record["stages"]],
                    "lock": dict(record["lock"]) if record["lock"] else None,
                }
                for name, record in RECORDS.items()
            },
            "locations": {str(BASE_ID + loc["id"]): loc["id"] for loc in LOCATIONS},
        }
