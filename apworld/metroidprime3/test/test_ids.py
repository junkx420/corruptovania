"""Locations, pool and stable IDs (T04 acceptance 4)."""

import json
import unittest
from collections import Counter

from .. import MP3World
from ..data import items as item_data
from ..data import locations as location_data
from ..items import BASE_ID
from . import MP3TestBase

# Frozen snapshot: these numbers are what clients and old seeds rely on. Never change an existing entry.
EXPECTED_ITEM_IDS = {
    "Progressive Beam": 1297101569,
    "Missile Launcher": 1297101570,
    "Progressive Missile": 1297101571,
    "Grapple Lasso": 1297101572,
    "Grapple Swing": 1297101573,
    "Grapple Voltage": 1297101574,
    "Command Visor": 1297101575,
    "X-Ray Visor": 1297101576,
    "Screw Attack": 1297101577,
    "Hazard Shield": 1297101578,
    "Energy Tank": 1297101579,
    "Boost Ball": 1297101580,
    "Spider Ball": 1297101581,
    "Hypermode": 1297101582,
    "Hyper Missile": 1297101583,
    "Hyper Ball": 1297101584,
    "Hyper Grapple": 1297101585,
    "Ship Grapple": 1297101586,
    "Ship Missile": 1297101587,
    "Missile Expansion": 1297101588,
    "Ship Missile Expansion": 1297101589,
    "Energy Cell 1": 1297101590,
    "Energy Cell 2": 1297101591,
    "Energy Cell 3": 1297101592,
    "Energy Cell 4": 1297101593,
    "Energy Cell 5": 1297101594,
    "Energy Cell 6": 1297101595,
    "Energy Cell 7": 1297101596,
    "Energy Cell 8": 1297101597,
    "Energy Cell 9": 1297101598,
    "Charge Beam": 1297101669,
    "Power Beam": 1297101670,
    "Combat Visor": 1297101671,
    "Scan Visor": 1297101672,
    "Space Jump Boots": 1297101673,
    "Morph Ball": 1297101674,
    "Morph Ball Bombs": 1297101675,
}


class TestIds(unittest.TestCase):
    def test_base_id(self) -> None:
        self.assertEqual(BASE_ID, 1297101568)

    def test_99_locations_with_pickup_index_ids(self) -> None:
        ids = MP3World.location_name_to_id
        self.assertEqual(len(ids), 99)
        self.assertEqual(sorted(ids.values()), [BASE_ID + i for i in range(1, 100)])
        for loc in location_data.LOCATIONS:
            self.assertEqual(ids[loc["name"]], BASE_ID + loc["id"])
        self.assertNotIn(location_data.UNPATCHED_LOCATION["name"], ids)

    def test_item_ids_stable(self) -> None:
        self.assertEqual(MP3World.item_name_to_id, EXPECTED_ITEM_IDS)

    def test_every_data_item_has_an_id(self) -> None:
        names = {r["name"] for r in item_data.ITEMS + item_data.STARTING_ITEMS}
        self.assertEqual(names, set(MP3World.item_name_to_id))
        self.assertEqual(len(set(MP3World.item_name_to_id.values())), len(MP3World.item_name_to_id))

    def test_no_location_0_item(self) -> None:
        self.assertFalse(hasattr(item_data, "LOCATION_0_ITEM"))


class TestPool(MP3TestBase):
    def test_pool_is_99_items_with_hypermode(self) -> None:
        pool = [item for item in self.multiworld.itempool if item.player == self.player]
        self.assertEqual(len(pool), 99)
        counts = Counter(item.name for item in pool)
        self.assertEqual(counts, Counter({r["name"]: r["count"] for r in item_data.ITEMS}))
        self.assertEqual(counts["Hypermode"], 1)
        self.assertEqual(counts["Missile Expansion"], 48)
        self.assertTrue(all(item.code is not None for item in pool))

    def test_99_real_locations(self) -> None:
        real = [loc for loc in self.multiworld.get_locations(self.player) if loc.address is not None]
        self.assertEqual(len(real), 99)
        self.assertTrue(all(loc.item is None for loc in real))
        events = [loc for loc in self.multiworld.get_locations(self.player) if loc.address is None]
        self.assertTrue(all(loc.item is not None and loc.item.code is None for loc in events))

    def test_starting_items_precollected(self) -> None:
        names = [item.name for item in self.multiworld.precollected_items[self.player]]
        self.assertEqual(names, [r["name"] for r in item_data.STARTING_ITEMS])

    def test_slot_data(self) -> None:
        slot_data = self.world.fill_slot_data()
        json.dumps(slot_data)
        self.assertEqual(slot_data["starting_items"], [r["name"] for r in item_data.STARTING_ITEMS])
        self.assertEqual(slot_data["starting_resources"]["Morph Ball Bomb"], 1)
        self.assertEqual(slot_data["items"]["Progressive Beam"]["stages"], [[["Plasma Beam", 1]], [["Nova Beam", 1]]])
        self.assertEqual(slot_data["items"]["Missile Expansion"]["lock"]["opened_by"], "Missile Launcher")
        self.assertEqual(len(slot_data["locations"]), 99)
        self.assertEqual(slot_data["goal_event"], "Aurora Unit 313")


class TestNoRandovania(unittest.TestCase):
    def test_no_randovania_import(self) -> None:
        """SPEC 3a / acceptance 6: the APWorld must not depend on randovania at runtime."""
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    self.assertNotEqual(name.split(".")[0], "randovania", f"{path}: imports {name}")
