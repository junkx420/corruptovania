"""Seed regression tests for restrictive fill with location escape rules."""

import os
import unittest

from Fill import distribute_items_restrictive
from test.general import setup_multiworld

from .. import MP3World


class TestGeneration(unittest.TestCase):
    def test_default_seeds(self) -> None:
        self.check_seeds(range(1, 301))

    @unittest.skipUnless(os.environ.get("MP3_EXTENDED_FILL_TESTS") == "1", "Set MP3_EXTENDED_FILL_TESTS=1")
    def test_extended_default_seeds(self) -> None:
        self.check_seeds(range(301, 1201))

    def check_seeds(self, seeds: range) -> None:
        for seed in seeds:
            with self.subTest(seed=seed):
                multiworld = setup_multiworld(MP3World, seed=seed)
                distribute_items_restrictive(multiworld)
                self.assertFalse(multiworld.get_unfilled_locations())

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
