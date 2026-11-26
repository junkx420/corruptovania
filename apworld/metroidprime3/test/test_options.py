"""T31 (E23): starting item and trick options - pool, slot_data, patch data, regions."""

from __future__ import annotations

import itertools
import unittest
from collections import Counter

from Options import OptionError
from test.general import gen_steps, setup_multiworld
from worlds.AutoWorld import call_all
from worlds.generic.Rules import locality_rules

from .. import MP3World
from ..data import tricks as trick_data
from ..items import FILLER_ITEM_NAME, pool_names, starting_names
from ..options import (FIXED_STARTING_ITEMS, REMOVABLE_STARTING_ITEMS, TrickOverrides, resolve_tricks)
from ..output import build_patch_data
from ..patcher import patch_data
from ..regions import reachable_graph

ALL_KEPT_SUBSETS = [list(kept) for r in range(5) for kept in itertools.combinations(REMOVABLE_STARTING_ITEMS, r)]


def make(seed: int = 1, **options):
    multiworld = setup_multiworld(MP3World, seed=seed, options=options)
    return multiworld, multiworld.worlds[1]


class TestStartingItems(unittest.TestCase):
    def test_default_keeps_all_seven(self) -> None:
        multiworld, world = make()
        self.assertEqual(world.starting_item_names, starting_names())
        self.assertEqual(world.removed_starting_items, [])
        self.assertEqual(Counter(i.name for i in multiworld.itempool), Counter(pool_names()))
        self.assertEqual(world.fill_slot_data()["starting_items"], starting_names())
        self.assertEqual(build_patch_data(multiworld, 1).starting_items, patch_data.STANDARD_STARTING_ITEMS)

    def test_every_choice(self) -> None:
        for kept in ALL_KEPT_SUBSETS:
            with self.subTest(kept=kept):
                multiworld, world = make(starting_items=kept)
                removed = [n for n in REMOVABLE_STARTING_ITEMS if n not in kept]
                expected_start = [n for n in starting_names() if n in set(kept) | set(FIXED_STARTING_ITEMS)]
                self.assertEqual(world.starting_item_names, expected_start)
                self.assertEqual(world.removed_starting_items, removed)
                self.assertEqual(sorted(i.name for i in multiworld.precollected_items[1]), sorted(expected_start))
                chain = [loc.item.name for loc in multiworld.get_locations(1) if loc.address and loc.item]
                pool = Counter(i.name for i in multiworld.itempool) + Counter(chain)  # opening chain (T31)
                self.assertEqual(sum(pool.values()), 99)
                expected_pool = Counter(pool_names()) + Counter(removed)
                expected_pool[FILLER_ITEM_NAME] -= len(removed)
                self.assertEqual(pool, expected_pool)
                for name in removed:
                    self.assertTrue(world.create_item(name).advancement, name)
                slot_data = world.fill_slot_data()
                self.assertEqual(slot_data["starting_items"], expected_start)
                for name in removed:
                    resource = "Morph Ball Bomb" if name == "Morph Ball Bombs" else name
                    self.assertNotIn(resource, slot_data["starting_resources"])
                text = build_patch_data(multiworld, 1).starting_items
                self.assertEqual(sorted(patch_data.starting_item_names(text)),
                                 sorted(set(expected_start) - {"Combat Visor"}))

    def test_fixed_items_cannot_be_removed(self) -> None:
        with self.assertRaises(OptionError):
            multiworld = setup_multiworld(MP3World, seed=1, options={"starting_items": ["Power Beam"]}, steps=())
            multiworld.worlds[1].options.starting_items.verify(MP3World, "Tester1", None)


class TestOpeningChain(unittest.TestCase):
    """opening.py: forward chain of own progression items for small starting inventories (T31)."""

    def chain(self, multiworld) -> list:
        return [loc for loc in multiworld.get_locations(1) if loc.address is not None and loc.item is not None]

    def test_default_has_no_chain(self) -> None:
        multiworld, _ = make()
        self.assertEqual(self.chain(multiworld), [])
        self.assertEqual(dict(multiworld.local_early_items[1]), {"Screw Attack": 1})  # T29 unchanged

    def test_chain_is_placed_forwards(self) -> None:
        for kept, seed in (([], 1), (["Space Jump Boots"], 2), (["Morph Ball", "Space Jump Boots"], 3),
                           (["Charge Beam", "Space Jump Boots", "Morph Ball Bombs"], 4)):
            with self.subTest(kept=kept, seed=seed):
                multiworld, world = make(seed, starting_items=kept)
                self.assertNotIn("Screw Attack", multiworld.local_early_items[1])
                chain = self.chain(multiworld)
                self.assertTrue(chain)
                self.assertEqual(sum(1 for i in multiworld.itempool if i.player == 1) + len(chain), 99)
                for location in chain:
                    self.assertTrue(location.locked)
                    self.assertEqual(location.item.player, 1)
                    self.assertTrue(location.item.advancement)
                # forward: sweeping from the start reaches every chain item, and then at least 8 open checks
                state = multiworld.state.copy()
                state.sweep_for_advancements()
                self.assertTrue(all(loc in state.locations_checked for loc in chain))
                open_checks = [loc for loc in multiworld.get_reachable_locations(state, 1)
                               if loc.address is not None and loc.item is None]
                self.assertGreaterEqual(len(open_checks), 8)

    def test_chain_respects_non_local_items(self) -> None:
        """Main.py applies the locality rules before pre_fill; the chain's can_fill sees them."""
        options = {"starting_items": [], "non_local_items": ["Grapple Swing", "Missile Launcher"]}
        multiworld = setup_multiworld(MP3World, steps=gen_steps[:-1], seed=1, options=options)
        locality_rules(multiworld)
        call_all(multiworld, "pre_fill")
        self.assertNotIn("Grapple Swing", {loc.item.name for loc in self.chain(multiworld)})
        self.assertNotIn("Missile Launcher", {loc.item.name for loc in self.chain(multiworld)})


class TestTricks(unittest.TestCase):
    def test_resolve(self) -> None:
        self.assertEqual(resolve_tricks(0, {}), {})
        advanced = resolve_tricks(3, {})
        self.assertEqual(advanced, trick_data.USABLE_TRICKS)
        self.assertEqual(advanced["Invisible Objects"], 2)
        self.assertEqual(resolve_tricks(1, {}), {name: 1 for name in trick_data.USABLE_TRICKS})
        mixed = resolve_tricks(2, {"Combat": "off", "Movement": "advanced", "Slope Jump": 1})
        self.assertNotIn("Combat", mixed)
        self.assertEqual(mixed["Movement"], 3)
        self.assertEqual(mixed["Slope Jump"], 1)
        self.assertEqual(mixed["Knowledge"], 2)

    def test_override_schema(self) -> None:
        TrickOverrides({"Bomb Jump": "Advanced", "Invisible Objects": "intermediate", "Combat": 0, "Movement": False})
        self.assertNotIn("Movement", resolve_tricks(3, {"Movement": False}))
        for bad in ({"Invisible Objects": "advanced"}, {"Open Barriers from Behind": 3}, {"Bomb Jump": "expert"},
                    {"Fall Respawn Skip": "beginner"}, {"Bomb Jump": True}, {"Bomb Jump": 4}):
            with self.subTest(bad=bad), self.assertRaises(Exception):
                TrickOverrides(bad)

    def test_world_uses_slot_tricks(self) -> None:
        multiworld, world = make(trick_level="advanced")
        self.assertEqual(world.tricks, trick_data.USABLE_TRICKS)
        self.assertEqual(world.fill_slot_data()["tricks"], trick_data.USABLE_TRICKS)
        regions = {r.name for r in multiworld.get_regions(1)}
        default_regions = {r.name for r in make()[0].get_regions(1)}
        self.assertGreaterEqual(regions, default_regions)
        graph = reachable_graph(trick_data.USABLE_TRICKS)
        self.assertEqual(len(regions) - 1, len(graph.nodes))  # + Menu
        self.assertEqual(make()[1].fill_slot_data()["tricks"], {})

    def test_tricks_open_more_with_few_items(self) -> None:
        def sphere0(multiworld) -> int:
            state = multiworld.state.copy()
            state.sweep_for_advancements()
            return len([loc for loc in multiworld.get_reachable_locations(state, 1) if loc.address is not None])
        self.assertGreater(sphere0(make(trick_level="advanced")[0]), sphere0(make()[0]))


if __name__ == "__main__":
    unittest.main()
