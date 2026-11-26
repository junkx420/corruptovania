"""Seed regression tests for restrictive fill with location escape rules."""

import os
import unittest

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from test.general import setup_multiworld

from .. import MP3World
from .test_options import ALL_KEPT_SUBSETS


class TestGeneration(unittest.TestCase):
    def test_default_seeds(self) -> None:
        self.check_seeds(range(1, 301))

    @unittest.skipUnless(os.environ.get("MP3_EXTENDED_FILL_TESTS") == "1", "Set MP3_EXTENDED_FILL_TESTS=1")
    def test_extended_default_seeds(self) -> None:
        self.check_seeds(range(301, 1201))

    def check_seeds(self, seeds: range, options: dict | None = None) -> None:
        for seed in seeds:
            with self.subTest(seed=seed, options=options):
                multiworld = setup_multiworld(MP3World, seed=seed, options=options)
                distribute_items_restrictive(multiworld)
                self.assertFalse(multiworld.get_unfilled_locations())
                if options:
                    self.assertTrue(multiworld.can_beat_game(CollectionState(multiworld)))

    def test_every_starting_item_choice(self) -> None:
        """E23 (T31): all 16 starting item choices fill with Archipelago's fill (3 seeds each; 60 with
        MP3_EXTENDED_FILL_TESTS=1). Measured in T31: 0 failures in 300 seeds per choice (docs/AP_OPTIONS.md)."""
        seeds = range(1, 61) if os.environ.get("MP3_EXTENDED_FILL_TESTS") == "1" else range(1, 4)
        for kept in ALL_KEPT_SUBSETS:
            self.check_seeds(seeds, {"starting_items": kept})

    def test_tricks_with_small_starting_items(self) -> None:
        self.check_seeds(range(1, 4), {"starting_items": ["Space Jump Boots"], "trick_level": "advanced"})
        self.check_seeds(range(1, 4), {"starting_items": [], "trick_overrides": {"Bomb Jump": "advanced"}})

    def test_screw_attack_is_placed_in_the_first_sphere(self) -> None:
        multiworld = setup_multiworld(MP3World, seed=51)
        state = multiworld.state.copy()
        state.sweep_for_advancements()
        starting_checks = set(multiworld.get_unfilled_locations(1)) & set(multiworld.get_reachable_locations(state, 1))
        distribute_items_restrictive(multiworld)

        screw_attack, = multiworld.find_item_locations("Screw Attack", 1)
        self.assertIn(screw_attack, starting_checks)

    def test_custom_options_do_not_request_early_screw_attack(self) -> None:
        multiworld = setup_multiworld(MP3World, seed=51, options={"progression_balancing": 0})
        self.assertNotIn("Screw Attack", multiworld.local_early_items[1])
