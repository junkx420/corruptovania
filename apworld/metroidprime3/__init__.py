"""Archipelago world for Metroid Prime 3: Corruption (MVP, SPEC E3).

Logic, items and locations come from the generated data in ``data/`` (apworld/tools/convert_db.py). Nothing here
imports randovania (SPEC 3a). Developer notes: docs/AP_APWORLD_DEV.md.
"""

from __future__ import annotations

from typing import Any, ClassVar

from BaseClasses import Item
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, SuffixIdentifier, Type, components, launch

from .data import game as game_data
from .items import (BASE_ID, FILLER_ITEM_NAME, GAME_NAME, ITEM_OFFSETS, RECORDS, MP3Item, classification,
                    item_name_groups, item_name_to_id, pool_names, starting_names)
from .locations import LOCATIONS, location_name_groups, location_name_to_id
from .options import FIXED_STARTING_ITEMS, REMOVABLE_STARTING_ITEMS, MP3Options, resolve_tricks
from .opening import place_opening
from .output import write_patch_file
from .patcher.patch_data import CONTAINER_FILE_ENDING
from .regions import GOAL_EVENT, create_regions, starting_resources
from .settings import MP3Settings

SLOT_DATA_VERSION = 1


def launch_client(*args: str) -> None:
    """Launcher component "Metroid Prime 3 Client" (T06, docs/AP_CLIENT.md).

    T05b: With an ``.apmp3`` as argument (double click, "Open Patch", dragging the file onto the launcher window) the
    patched ISO is built first, then the client is started (``open_patch.py``, docs/AP_APWORLD_DEV.md).
    """
    if any(isinstance(arg, str) and arg.lower().endswith(CONTAINER_FILE_ENDING) for arg in args):
        from .open_patch import patch_and_launch
        launch(patch_and_launch, name="MetroidPrime3Client", args=args)
        return
    from .client import launch as client_main
    launch(client_main, name="MetroidPrime3Client", args=args)


components.append(Component("Metroid Prime 3 Client", func=launch_client, component_type=Type.CLIENT,
                            game_name=GAME_NAME, supports_uri=True,
                            file_identifier=SuffixIdentifier(CONTAINER_FILE_ENDING)))


class MP3Web(WebWorld):
    tutorials = []  # setup guide follows with the client (T06/T07); dev notes: docs/AP_APWORLD_DEV.md


class MP3World(World):
    """Metroid Prime 3: Corruption. Samus Aran fights the Phazon corruption across planets and Leviathans."""

    game = GAME_NAME
    web = MP3Web()
    options_dataclass = MP3Options
    options: MP3Options
    topology_present = True
    settings: ClassVar[MP3Settings]

    item_name_to_id: ClassVar[dict[str, int]] = item_name_to_id
    location_name_to_id: ClassVar[dict[str, int]] = location_name_to_id
    item_name_groups = item_name_groups
    location_name_groups = location_name_groups

    def create_item(self, name: str) -> Item:
        return MP3Item(name, classification(name), self.item_name_to_id[name], self.player)

    def get_filler_item_name(self) -> str:
        return FILLER_ITEM_NAME

    # set in generate_early (E23, T31)
    starting_item_names: list[str]  # the slot's starting items, data order
    removed_starting_items: list[str]  # removable starting items the player gave up; they go into the pool
    tricks: dict[str, int]  # the slot's trick levels {trick name: 1-3}, only tricks above "off"

    def generate_early(self) -> None:
        kept = set(FIXED_STARTING_ITEMS) | set(self.options.starting_items.value)
        self.starting_item_names = [name for name in starting_names() if name in kept]
        self.removed_starting_items = [name for name in REMOVABLE_STARTING_ITEMS if name not in kept]
        self.tricks = resolve_tricks(self.options.trick_level.value, self.options.trick_overrides.value)
        if all(getattr(self.options, name).value == option.from_any(option.default).value
               for name, option in self.options_dataclass.type_hints.items()):
            # Screw Attack opens two more checks from the starting inventory. Keep it in this player's world.
            self.multiworld.local_early_items[self.player]["Screw Attack"] = 1

    def pre_fill(self) -> None:
        if self.removed_starting_items:
            place_opening(self)  # E23, T31: small starting inventories (opening.py)

    def create_regions(self) -> None:
        create_regions(self, self.tricks)

    def create_items(self) -> None:
        for name in self.starting_item_names:
            self.multiworld.push_precollected(self.create_item(name))
        pool = pool_names()
        # E23: every removed starting item replaces one Missile Expansion (the pool stays at 99 items)
        for name in self.removed_starting_items:
            last = len(pool) - 1 - pool[::-1].index(FILLER_ITEM_NAME)
            pool[last] = name
        self.multiworld.itempool += [self.create_item(name) for name in pool]

    def set_rules(self) -> None:
        player = self.player
        self.multiworld.completion_condition[player] = lambda state: state.has(GOAL_EVENT, player)

    def generate_output(self, output_directory: str) -> None:
        """One ``.apmp3`` per MP3 slot (AP patch data v1, docs/AP_PATCH_TOOL.md 2; container: ``output.py``)."""
        write_patch_file(self.multiworld, self.player, output_directory)

    def fill_slot_data(self) -> dict[str, Any]:
        """Everything the client needs to compute the target inventory (E11). Format: docs/AP_APWORLD_DEV.md."""
        return {
            "slot_data_version": SLOT_DATA_VERSION,
            "seed_name": self.multiworld.seed_name,
            "base_id": BASE_ID,
            "goal_event": GOAL_EVENT,
            "start_location": list(game_data.START_LOCATION),
            "starting_items": list(self.starting_item_names),  # T31: the slot's choice (E23)
            "starting_resources": starting_resources(self.starting_item_names),
            "tricks": dict(self.tricks),  # T31, informational: trick levels the logic expects (empty = none)
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
