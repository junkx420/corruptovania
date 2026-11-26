"""Regressions for the Universal Tracker v0.3.8 world and state rebuild."""

import inspect
import json
import unittest
from collections import Counter

from BaseClasses import CollectionState, Location, LocationProgressType, MultiWorld
from Fill import distribute_items_restrictive
from test.general import setup_multiworld
from worlds.AutoWorld import call_all
from worlds.generic.Rules import exclusion_rules

from .. import MP3World
from ..items import BASE_ID
from ..options import REMOVABLE_STARTING_ITEMS

COURTYARD = "Pirate Homeworld - Command - Command Courtyard - Pickup (Missile Expansion)"


def create_world(multiworld: MultiWorld) -> None:
    for step in ("create_regions", "create_items", "set_rules", "connect_entrances", "generate_basic"):
        call_all(multiworld, step)
        if step == "set_rules":
            exclusion_rules(multiworld, 1, multiworld.worlds[1].options.exclude_locations.value)


def generate_seed(seed: int, options: dict) -> MultiWorld:
    multiworld = setup_multiworld(MP3World, steps=("generate_early",), seed=seed, options=options)
    for name, count in multiworld.worlds[1].options.start_inventory.value.items():
        for _ in range(count):
            multiworld.push_precollected(multiworld.create_item(name, 1))
    create_world(multiworld)
    call_all(multiworld, "pre_fill")
    distribute_items_restrictive(multiworld)
    return multiworld


def regenerate(slot_data: dict) -> MultiWorld:
    """Model TrackerCore.initalize_tracker_core, TMain and run_generator with an empty YAML."""
    assert MP3World.ut_can_gen_without_yaml
    assert isinstance(inspect.getattr_static(MP3World, "interpret_slot_data"), staticmethod)
    passthrough = MP3World.interpret_slot_data(json.loads(json.dumps(slot_data)))
    assert passthrough
    multiworld = setup_multiworld(MP3World, steps=(), seed=90210)
    multiworld.generation_is_fake = True
    multiworld.re_gen_passthrough = {MP3World.game: passthrough}
    call_all(multiworld, "generate_early")
    create_world(multiworld)
    multiworld.precollected_items[1] = [item for item in multiworld.precollected_items[1] if item.code is None]
    return multiworld


def tracker_state(multiworld: MultiWorld, received: list[int]) -> CollectionState:
    """Mirror TrackerCore.updateTracker: replay server items and sweep only addressless events."""
    state = CollectionState(multiworld)
    for code in received:
        item = multiworld.create_item(multiworld.worlds[1].item_id_to_name[code], 1)
        state.collect(item, prevent_sweep=True)
    sweep_events(multiworld, state)
    return state


def sweep_events(multiworld: MultiWorld, state: CollectionState) -> None:
    state.sweep_for_advancements(locations=[loc for loc in multiworld.get_locations(1) if loc.address is None])


class TestUniversalTracker(unittest.TestCase):
    def test_regeneration_matches_filled_seed(self) -> None:
        variants = {
            "default": {},
            "only Space Jump": {"starting_items": ["Space Jump Boots"]},
            "Morph Ball and Space Jump": {"starting_items": ["Morph Ball", "Space Jump Boots"]},
            "tricks": {
                "trick_level": "intermediate",
                "trick_overrides": {"Combat": False, "Movement": "advanced"},
                "start_inventory": {"Energy Tank": 2},
                "exclude_locations": [COURTYARD],
            },
        }
        for variant, options in variants.items():
            for seed in (1, 17, 42):
                with self.subTest(variant=variant, seed=seed):
                    original = generate_seed(seed, options)
                    original_world = original.worlds[1]
                    tracked = regenerate(original_world.fill_slot_data())
                    world = tracked.worlds[1]
                    for name in ("starting_items", "trick_level", "trick_overrides",
                                 "start_inventory", "exclude_locations"):
                        self.assertEqual(getattr(world.options, name).value,
                                         getattr(original_world.options, name).value)
                    self.assertEqual(world.tricks, original_world.tricks)
                    self.assertEqual(world.starting_item_names, original_world.starting_item_names)
                    self.assertEqual(world.removed_starting_items, original_world.removed_starting_items)
                    self.assertEqual({loc.address for loc in tracked.get_locations(1)
                                      if loc.progress_type == LocationProgressType.EXCLUDED},
                                     {BASE_ID + 1, BASE_ID + 2} |
                                     {world.location_name_to_id[name] for name in world.options.exclude_locations.value})

                    # Also guard against the chain being placed if a tracker runs pre_fill.
                    call_all(tracked, "pre_fill")
                    self.assertFalse(tracked.local_early_items[1])
                    self.assertFalse([loc for loc in tracked.get_filled_locations(1) if loc.address is not None])
                    self.assertEqual(len(tracked.itempool), 99)
                    remaining = {loc for loc in original.get_locations(1) if loc.address is not None}
                    self.assertEqual(Counter(item.name for item in tracked.itempool),
                                     Counter(loc.item.name for loc in remaining))
                    self.compare_playthrough(original, tracked, remaining)

    def compare_playthrough(self, original: MultiWorld, tracked: MultiWorld, remaining: set[Location]) -> None:
        received = [item.code for item in original.precollected_items[1]]
        collected = []
        original_locations = {loc.name: loc for loc in original.get_locations(1)}
        tracked_locations = {loc.name: loc for loc in tracked.get_locations(1)}
        self.assertEqual(original_locations.keys(), tracked_locations.keys())
        original_edges = {edge.name: edge for edge in original.get_entrances(1)}
        tracked_edges = {edge.name: edge for edge in tracked.get_entrances(1)}
        self.assertEqual(original_edges.keys(), tracked_edges.keys())

        while True:
            original_state = CollectionState(original)
            for loc in collected:
                original_state.collect(loc.item, prevent_sweep=True)
            sweep_events(original, original_state)
            state = tracker_state(tracked, received)
            self.assertEqual(original_state.prog_items, state.prog_items)
            self.assertEqual({reg.name for reg in original.get_regions(1) if reg.can_reach(original_state)},
                             {reg.name for reg in tracked.get_regions(1) if reg.can_reach(state)})
            for original_spots, tracked_spots in ((original_locations, tracked_locations),
                                                  (original_edges, tracked_edges)):
                self.assertEqual({name for name, spot in original_spots.items() if spot.access_rule(original_state)},
                                 {name for name, spot in tracked_spots.items() if spot.access_rule(state)})
            original_reachable = original.get_reachable_locations(original_state, 1)
            self.assertEqual({loc.name for loc in original_reachable},
                             {loc.name for loc in tracked.get_reachable_locations(state, 1)})
            self.assertEqual(original.has_beaten_game(original_state), tracked.has_beaten_game(state))
            if not remaining:
                self.assertTrue(tracked.has_beaten_game(state))
                break
            sphere = remaining.intersection(original_reachable)
            self.assertTrue(sphere)
            remaining -= sphere
            for loc in sorted(sphere, key=lambda loc: loc.address):
                collected.append(loc)
                received.append(loc.item.code)

    def test_command_courtyard_needs_received_space_jump(self) -> None:
        original = generate_seed(1, {"starting_items": sorted(set(REMOVABLE_STARTING_ITEMS) - {"Space Jump Boots"})})
        world = original.worlds[1]
        tracked = regenerate(world.fill_slot_data())
        space_jump = world.item_name_to_id["Space Jump Boots"]
        received = [item.code for item in tracked.itempool if item.code != space_jump]
        received += [item.code for item in original.precollected_items[1]]
        location = tracked.get_location(COURTYARD, 1)
        self.assertFalse(location.can_reach(tracker_state(tracked, received)))
        self.assertTrue(location.can_reach(tracker_state(tracked, received + [space_jump])))

    def test_older_slot_data(self) -> None:
        for slot_data in ({}, {"slot_data_version": 1}):
            world = regenerate(slot_data).worlds[1]
            for name, option in world.options_dataclass.type_hints.items():
                self.assertEqual(getattr(world.options, name).value, option.from_any(option.default).value)

        # T31 seeds have the effective settings but lack the raw YAML options.
        world = regenerate({"starting_items": ["Space Jump Boots"], "tricks": {"Movement": 2}}).worlds[1]
        self.assertEqual(world.options.starting_items.value, {"Space Jump Boots"})
        self.assertEqual(world.tricks, {"Movement": 2})
        self.assertEqual(world.options.start_inventory.value, {})
        self.assertEqual(world.options.exclude_locations.value, set())
