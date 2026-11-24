"""Playthrough test (T04 acceptance 5): Archipelago fills solo seeds, playthrough_sim's logic-following player
must win every one of them with the real AP placement.

The simulator (apworld/tools/playthrough_sim.py, T20) already takes a placement ``{pickup index: item record}``;
``ap_placement`` below is the thin adapter from an Archipelago multiworld to that format.
"""

import random
import unittest

from BaseClasses import MultiWorld
from Fill import balance_multiworld_progression, distribute_items_restrictive
from test.general import gen_steps, setup_solo_multiworld
from worlds.AutoWorld import call_all

from .. import MP3World
from ..items import RECORDS
from ..locations import pickup_index
from . import load_playthrough_sim

SEEDS = range(1, 21)
FOREIGN_ITEM = {"name": "Foreign item", "stages": [[]]}  # an item of another world gives nothing locally


def generate(seed: int) -> MultiWorld:
    """The generation steps of Archipelago's Main.py up to progression balancing, without output."""
    multiworld = setup_solo_multiworld(MP3World, gen_steps, seed)
    distribute_items_restrictive(multiworld)
    call_all(multiworld, "post_fill")
    balance_multiworld_progression(multiworld)
    return multiworld


def ap_placement(multiworld: MultiWorld, player: int) -> dict[int, dict]:
    """Adapter: AP placement of one MP3 player -> playthrough_sim placement (pickup index -> item record)."""
    placement = {}
    for location in multiworld.get_locations(player):
        if location.address is None:
            continue  # event location
        item = location.item
        own = item.player == player and item.game == MP3World.game
        placement[pickup_index(location.address)] = RECORDS[item.name] if own else FOREIGN_ITEM
    return placement


class TestPlaythrough(unittest.TestCase):
    def test_logic_following_player_wins_ap_seeds(self) -> None:
        sim = load_playthrough_sim()
        if sim is None:
            self.skipTest("apworld/tools/playthrough_sim.py not found")
        world = sim.World(sim.load_data())
        for seed in SEEDS:
            with self.subTest(seed=seed):
                multiworld = generate(seed)
                self.assertTrue(multiworld.can_beat_game(multiworld.get_all_state()))
                placement = ap_placement(multiworld, 1)
                self.assertEqual(sorted(placement), list(range(1, 100)))
                for eager in (0.0, 0.5):
                    result = sim.play(world, placement, random.Random(seed), eager)
                    self.assertTrue(result["won"], (seed, eager, result))
                    self.assertEqual(result["collected"], 99, (seed, eager, result["missing"]))
