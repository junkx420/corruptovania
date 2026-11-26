"""Playthrough test (T04 acceptance 5): Archipelago fills solo seeds, playthrough_sim's logic-following player
must win every one of them with the real AP placement.

The simulator (apworld/tools/playthrough_sim.py, T20) already takes a placement ``{pickup index: item record}``;
``ap_placement`` below is the thin adapter from an Archipelago multiworld to that format.
"""

import random
import unittest

from BaseClasses import Location, MultiWorld
from Fill import balance_multiworld_progression, distribute_items_restrictive
from test.general import gen_steps, setup_multiworld, setup_solo_multiworld
from worlds.AutoWorld import call_all

from .. import MP3World
from ..data import tricks as trick_data
from ..items import RECORDS
from ..locations import pickup_index
from . import load_playthrough_sim
from .test_logic import multiworld_with_tricks

SEEDS = range(1, 21)
FOREIGN_ITEM = {"name": "Foreign item", "stages": [[]]}  # an item of another world gives nothing locally


def generate(seed: int, location_rules: bool = True, tricks: dict | None = None,
             options: dict | None = None) -> MultiWorld:
    """The generation steps of Archipelago's Main.py up to progression balancing, without output.
    ``location_rules=False`` drops the locations' escape rules before the fill (logic before E22, control).
    ``tricks``: the slot's trick levels passed directly (T30); ``options``: YAML options of the slot (T31)."""
    if options:
        multiworld = setup_multiworld(MP3World, gen_steps, seed, options)
    elif tricks:
        multiworld = multiworld_with_tricks(tricks, seed)
    else:
        multiworld = setup_solo_multiworld(MP3World, gen_steps, seed)
    if not location_rules:
        for location in multiworld.get_locations(1):
            if location.address is not None:
                location.access_rule = Location.access_rule
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
                    self.assertFalse(result["trapped"], (seed, eager, result["end"]))

    def test_logic_following_player_wins_ap_seeds_with_usable_tricks(self) -> None:
        """E23 (T30): Archipelago's fill with USABLE_TRICKS at the recommended level; the simulator's player uses the
        same tricks (logic and physics) and wins with 99/99 locations, never trapped."""
        sim = load_playthrough_sim()
        if sim is None:
            self.skipTest("apworld/tools/playthrough_sim.py not found")
        tricks = dict(trick_data.USABLE_TRICKS)
        world = sim.World(sim.load_data(), tricks=tricks)
        for seed in SEEDS:
            with self.subTest(seed=seed):
                multiworld = generate(seed, tricks=tricks)
                self.assertTrue(multiworld.can_beat_game(multiworld.get_all_state()))
                placement = ap_placement(multiworld, 1)
                for eager in (0.0, 0.5):
                    result = sim.play(world, placement, random.Random(seed), eager)
                    self.assertTrue(result["won"], (seed, eager, result))
                    self.assertEqual(result["collected"], 99, (seed, eager, result["missing"]))
                    self.assertFalse(result["trapped"], (seed, eager, result["end"]))

    def test_logic_following_player_wins_with_small_starting_items(self) -> None:
        """E23 (T31): seeds with removed starting items (incl. the world's early items) and the YAML trick option; the
        simulator's player starts with the same items and wins with 99/99 locations, never trapped."""
        sim = load_playthrough_sim()
        if sim is None:
            self.skipTest("apworld/tools/playthrough_sim.py not found")
        data = sim.load_data()
        setups = [(["Space Jump Boots"], "off"),  # "only Space Jump" (player guide example)
                  (["Space Jump Boots", "Morph Ball"], "off"),
                  (["Charge Beam", "Space Jump Boots", "Morph Ball Bombs"], "off"),  # without Morph Ball
                  (["Charge Beam", "Morph Ball", "Morph Ball Bombs"], "advanced")]
        for kept, level in setups:
            multiworld0 = generate(1, options={"starting_items": kept, "trick_level": level})
            world0 = multiworld0.worlds[1]
            world = sim.World(data, tricks=world0.tricks, starting_items=world0.starting_item_names)
            for seed in range(1, 11):
                with self.subTest(kept=kept, tricks=level, seed=seed):
                    multiworld = generate(seed, options={"starting_items": kept, "trick_level": level})
                    placement = ap_placement(multiworld, 1)
                    result = sim.play(world, placement, random.Random(seed), 0.5)
                    self.assertTrue(result["won"], (seed, result))
                    self.assertEqual(result["collected"], 99, (seed, result["missing"]))
                    self.assertFalse(result["trapped"], (seed, result["end"]))

    def test_dead_ends_trap_the_player_without_location_rules(self) -> None:
        """Control (E22, T08 B5): the same seeds generated without the location rules, played by a player who
        ignores them too, strand him in a dead end in some seeds."""
        sim = load_playthrough_sim()
        if sim is None:
            self.skipTest("apworld/tools/playthrough_sim.py not found")
        world = sim.World(sim.load_data(), location_escapes=False)
        trapped = []
        for seed in SEEDS:
            placement = ap_placement(generate(seed, location_rules=False), 1)
            result = sim.play(world, placement, random.Random(seed), 0.5, dead_end_rule=False)
            if result["trapped"]:
                trapped.append((seed, result["dead_ends"]))
        self.assertTrue(trapped)
