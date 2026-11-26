"""Rule evaluation, reachability with all items, escape gates (E18), dead-end locations (E22), trick levels as a
parameter (E23, T30) and a cross-check against playthrough_sim."""

import functools
import random
import sys
import unittest
from unittest import mock

from BaseClasses import CollectionState, MultiWorld
from test.general import gen_steps, setup_solo_multiworld

from .. import MP3World
from .. import regions as regions_module
from ..data import game as game_data
from ..data import locations as location_data
from ..data import logic as logic_data
from ..data import tricks as trick_data
from ..items import BASE_ID, RECORDS, pool_names, starting_names
from ..regions import GOAL_EVENT, node_name, reachable_graph
from ..rules import ALWAYS, NEVER, RuleCompiler, StaticState
from . import MP3TestBase, load_playthrough_sim

# Locations whose rule is not implied by reaching their node with the default starting items and no tricks (T25).
DEFAULT_RULE_LOCATIONS = {26, 28, 29, 35, 56, 57, 58, 59, 60, 61, 62, 63, 64, 75, 76, 84, 86, 91, 94, 95, 97, 98, 99}


def multiworld_with_tricks(tricks: dict, seed: int | None = None) -> MultiWorld:
    """A solo multiworld up to pre_fill whose regions use ``tricks`` (what T31's options will pass)."""
    module = sys.modules[MP3World.__module__]
    patched = functools.partial(regions_module.create_regions, tricks=tricks)
    with mock.patch.object(module, "create_regions", patched):
        return setup_solo_multiworld(MP3World, gen_steps, seed)


def state_with(multiworld: MultiWorld, player: int, names) -> CollectionState:
    state = CollectionState(multiworld)
    world = multiworld.worlds[player]
    for name in names:
        state.collect(world.create_item(name), prevent_sweep=True)
    state.sweep_for_advancements()  # only events can be swept: real locations are empty
    return state


def item(name, amount=1, negate=False):
    req = {"type": "item", "name": name, "amount": amount}
    if negate:
        req["negate"] = True
    return req


class TestRules(unittest.TestCase):
    def setUp(self) -> None:
        self.c = RuleCompiler(player=1)

    def check(self, req, counts, expected, events=()):
        self.assertEqual(self.c.compile(req)(StaticState(counts, events)), expected, (req, counts))

    def test_and_or_empty(self) -> None:
        self.assertIs(self.c.compile({"and": []}), ALWAYS)
        self.assertIs(self.c.compile({"or": []}), NEVER)

    def test_before_event_is_satisfied(self) -> None:
        self.assertIs(self.c.compile({"type": "event", "name": "Meta Ridley", "amount": 1, "negate": True}), ALWAYS)

    def test_event(self) -> None:
        req = {"type": "event", "name": "Meta Ridley", "amount": 1}
        self.check(req, {}, False)
        self.check(req, {}, True, events={"Meta Ridley"})

    def test_tricks_default_off(self) -> None:
        self.assertIs(self.c.compile({"type": "trick", "name": "Bomb Jump", "amount": 1}), NEVER)

    def test_trick_levels_come_from_the_parameter(self) -> None:
        trick = lambda name, level: {"type": "trick", "name": name, "amount": level}  # noqa: E731
        c = RuleCompiler(player=1, tricks={"Bomb Jump": 2, "Movement": 0})
        self.assertIs(c.compile(trick("Bomb Jump", 1)), ALWAYS)
        self.assertIs(c.compile(trick("Bomb Jump", 2)), ALWAYS)
        self.assertIs(c.compile(trick("Bomb Jump", 3)), NEVER)
        self.assertIs(c.compile(trick("Movement", 1)), NEVER)
        self.assertIs(c.compile(trick("Knowledge", 1)), NEVER)
        self.assertIs(c.compile({**trick("Bomb Jump", 3), "negate": True}), ALWAYS)
        with self.assertRaises(ValueError):
            RuleCompiler(player=1, tricks={"Bogus Trick": 1})
        with self.assertRaises(ValueError):
            RuleCompiler(player=1, tricks={"Bomb Jump": 6})

    def test_trick_data(self) -> None:
        """data/tricks.py: one report per trick, USABLE_TRICKS within the offered range (E23)."""
        self.assertEqual(set(trick_data.TRICK_REPORT), set(game_data.TRICKS))
        self.assertTrue(trick_data.USABLE_TRICKS)
        for name, level in trick_data.USABLE_TRICKS.items():
            self.assertIn(level, range(1, trick_data.USABLE_MAX_LEVEL + 1), name)
            self.assertEqual(trick_data.TRICK_REPORT[name]["usable_level"], level)
        self.assertEqual(trick_data.TRICK_COVERAGE, {name: 5 for name in game_data.TRICKS})

    def test_no_item_and_node_never(self) -> None:
        self.assertIs(self.c.compile(item("Morph Ball", negate=True)), NEVER)
        self.assertIs(self.c.compile({"type": "node", "node": ("a", "b", "c")}), NEVER)

    def test_progressive_beam(self) -> None:
        self.check(item("Plasma Beam"), {"Progressive Beam": 1}, True)
        self.check(item("Nova Beam"), {"Progressive Beam": 1}, False)
        self.check(item("Nova Beam"), {"Progressive Beam": 2}, True)
        self.check(item("Plasma Beam", 2), {"Progressive Beam": 2}, False)

    def test_missile_lock(self) -> None:
        self.check(item("Missile", 5), {"Missile Expansion": 3}, False)
        self.check(item("Missile", 5), {"Missile Launcher": 1}, True)
        self.check(item("Missile", 10), {"Missile Launcher": 1}, False)
        self.check(item("Missile", 10), {"Missile Launcher": 1, "Missile Expansion": 1}, True)
        self.check(item("Ship Missile", 4), {"Ship Missile Expansion": 4}, False)
        self.check(item("Ship Missile", 4), {"Ship Missile": 1, "Ship Missile Expansion": 1}, True)

    def test_energy_cells_total(self) -> None:
        cells = {f"Energy Cell {i}": 1 for i in range(1, 6)}
        self.check(item("Energy Cells Total", 5), cells, True)
        self.check(item("Energy Cells Total", 6), cells, False)

    def test_damage(self) -> None:
        # 99 + 100 * tanks > int(amount * 1.5)
        dmg = lambda a: {"type": "damage", "name": "Damage", "amount": a}  # noqa: E731
        self.check(dmg(65), {}, True)  # needs > 97
        self.check(dmg(66), {}, False)  # needs > 99
        self.check(dmg(66), {"Energy Tank": 1}, True)
        self.check(dmg(132), {"Energy Tank": 1}, True)  # 199 > 198
        self.check(dmg(133), {"Energy Tank": 1}, False)  # 199 > int(199.5) = 199 fails

    def test_unknown_kind_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.c.compile({"type": "bogus", "name": "x", "amount": 1})


class TestReachability(MP3TestBase):
    def test_all_items_reach_all_99_locations_and_goal(self) -> None:
        state = self.multiworld.get_all_state()
        real = [loc for loc in self.multiworld.get_locations(self.player) if loc.address is not None]
        self.assertEqual(len(real), 99)
        for loc in real:
            self.assertTrue(loc.can_reach(state), loc.name)
        self.assertTrue(state.has(GOAL_EVENT, self.player))
        self.assertTrue(self.multiworld.can_beat_game(state))

    def test_only_unreachable_event_is_gel_processing_oob(self) -> None:
        # trick-only event (T20); everything else exists as an event location
        missing = set(logic_data.EVENTS) - reachable_graph().events
        self.assertEqual(missing, {"Gel Processing Site Out of Bounds"})

    def test_starting_items_alone_do_not_beat_the_game(self) -> None:
        state = CollectionState(self.multiworld)
        state.sweep_for_advancements()
        self.assertFalse(self.multiworld.can_beat_game(state))

    def _state_with(self, names) -> CollectionState:
        state = CollectionState(self.multiworld)
        for name in names:
            state.collect(self.world.create_item(name), prevent_sweep=True)
        state.sweep_for_advancements()  # only events can be swept: real locations are empty
        return state

    def test_escape_gate_holds_wherever_an_event_node_is_reachable(self) -> None:
        """E18: an AP state may only reach a dangerous event node if the escape requirement holds there."""
        compiler = RuleCompiler(self.player)
        gates = {name: (node_name(tuple(ev["node"])), compiler.compile(ev["escape_requirement"]))
                 for name, ev in logic_data.EVENTS.items() if "escape_requirement" in ev}
        self.assertEqual(len(gates), 22)
        progression = sorted({n for n in pool_names() if RECORDS[n]["progression"]})
        full = [n for n in pool_names() if RECORDS[n]["progression"]]
        rng = random.Random(4)
        inventories = [[n for n in full if n != missing] for missing in progression]
        inventories += [rng.sample(full, rng.randint(0, len(full))) for _ in range(40)]
        checked = 0
        for names in inventories:
            state = self._state_with(names)
            for event, (region_name, gate) in gates.items():
                try:
                    region = self.multiworld.get_region(region_name, self.player)
                except KeyError:
                    continue  # node unreachable even with all items
                if region.can_reach(state):
                    checked += 1
                    self.assertTrue(gate(state), (event, sorted(set(full) - set(names))))
        self.assertGreater(checked, 100)

    def test_green_lock_needs_grapple_lasso(self) -> None:
        """Control value from data/README: entering the Gateway Green Lock node requires Grapple Lasso."""
        node = next(tuple(ev["node"]) for name, ev in logic_data.EVENTS.items()
                    if "escape_requirement" in ev and "Green Lock" in name)
        region = self.multiworld.get_region(node_name(node), self.player)
        names = [n for n in pool_names() if RECORDS[n]["progression"] and n != "Grapple Lasso"]
        self.assertFalse(region.can_reach(self._state_with(names)))
        self.assertTrue(region.can_reach(self._state_with(names + ["Grapple Lasso"])))

    def test_matches_playthrough_sim_logic(self) -> None:
        """Reachable nodes, events and locations agree with playthrough_sim.World.reach(logic=True) for random
        inventories (locations: node reached and escape_requirement held, E22)."""
        sim = load_playthrough_sim()
        if sim is None:
            self.skipTest("apworld/tools/playthrough_sim.py not found")
        sim_world = sim.World(sim.load_data())
        full = [n for n in pool_names() if RECORDS[n]["progression"]]
        rng = random.Random(7)
        node_regions = {node_name(node): node for node in reachable_graph().nodes}
        locations = {loc.address - BASE_ID: loc for loc in self.multiworld.get_locations(self.player)
                     if loc.address is not None}
        inventories = [[n for n in full if n != missing] for missing in sorted(set(full))]
        inventories += [rng.sample(full, rng.randint(0, len(full))) for _ in range(40)]
        for names in inventories:
            state = self._state_with(names)
            inv, _ = sim_world.inventory([RECORDS[n] for n in names + starting_names()])
            nodes, events, _, _ = sim_world.reach(inv)
            ap_nodes = {node for name, node in node_regions.items()
                        if self.multiworld.get_region(name, self.player).can_reach(state)}
            self.assertEqual(ap_nodes, set(nodes), sorted(names))
            ap_events = {ev for ev in logic_data.EVENTS if state.has(ev, self.player)}
            self.assertEqual(ap_events, set(events), sorted(names))
            ap_locations = {lid for lid, loc in locations.items() if loc.can_reach(state)}
            self.assertEqual(ap_locations, sim_world.reachable_locations(nodes, inv, events), sorted(names))


class TestDeadEndLocations(MP3TestBase):
    """E22 (T25): a location's access rule is its escape_requirement from the data."""

    # exit items of the three Leviathan cores (randovania/games/prime3/logic_database/* - Seed.txt)
    CORES = {98: ("Hyper Ball",), 97: ("Hyper Missile",), 99: ("Hyper Grapple",)}

    def _state_with(self, names) -> CollectionState:
        state = CollectionState(self.multiworld)
        for name in names:
            state.collect(self.world.create_item(name), prevent_sweep=True)
        state.sweep_for_advancements()
        return state

    def _location(self, pickup: int):
        return next(loc for loc in self.multiworld.get_locations(self.player) if loc.address == BASE_ID + pickup)

    def test_rules_come_from_the_data(self) -> None:
        compiler = RuleCompiler(self.player)
        with_rule = []
        for loc in location_data.LOCATIONS:
            location = self._location(loc["id"])
            if loc["escape_requirement"] == {"and": []}:
                self.assertIs(location.access_rule, ALWAYS, loc["name"])
            else:
                with_rule.append(loc["id"])
                self.assertIsNot(compiler.compile(loc["escape_requirement"]), ALWAYS, loc["name"])
        self.assertEqual(len(with_rule), sum(loc["escape_requirement"] != {"and": []} for loc in location_data.LOCATIONS))
        self.assertTrue(DEFAULT_RULE_LOCATIONS <= set(with_rule))

    def test_default_setup_behaves_as_before(self) -> None:
        """T30: the rules no longer assume starting items or the trick setting, but with the default starting items
        and no tricks only the 22 T25 locations ever differ from their region (random inventories)."""
        full = [n for n in pool_names() if RECORDS[n]["progression"]]
        rng = random.Random(5)
        inventories = [[n for n in full if n != missing] for missing in sorted(set(full))]
        inventories += [rng.sample(full, rng.randint(0, len(full))) for _ in range(60)]
        differs = set()
        for names in inventories:
            state = self._state_with(names)
            for loc in location_data.LOCATIONS:
                location = self._location(loc["id"])
                if location.parent_region.can_reach(state) and not location.can_reach(state):
                    differs.add(loc["id"])
        self.assertLessEqual(differs, DEFAULT_RULE_LOCATIONS)
        self.assertTrue({97, 98, 99} <= differs)

    def test_leviathan_cores_need_their_exit_item(self) -> None:
        """B5: the core's region is reachable without the exit item, the location is not."""
        full = [n for n in pool_names() if RECORDS[n]["progression"]]
        for pickup, exit_items in self.CORES.items():
            location = self._location(pickup)
            names = [n for n in full if n not in exit_items]
            state = self._state_with(names)
            self.assertTrue(location.parent_region.can_reach(state), location.name)
            self.assertFalse(location.can_reach(state), location.name)
            self.assertTrue(location.can_reach(self._state_with(full)), location.name)

    def test_exit_item_never_placed_in_its_own_core(self) -> None:
        """Side effect of E22 (accepted): Archipelago's fill cannot put a core's exit item into that core."""
        for pickup, exit_items in self.CORES.items():
            location = self._location(pickup)
            names = [n for n in pool_names() if RECORDS[n]["progression"] and n not in exit_items]
            for item in exit_items:
                self.assertFalse(location.can_fill(self._state_with(names), self.world.create_item(item)),
                                 (location.name, item))


class TestTricks(unittest.TestCase):
    """E23 (T30): the APWorld evaluates the trick leaves with the slot's levels; checked against the simulator."""

    def test_tricks_open_more_of_the_graph(self) -> None:
        default = reachable_graph()
        usable = reachable_graph(trick_data.USABLE_TRICKS)
        coverage = reachable_graph(trick_data.TRICK_COVERAGE)
        self.assertLessEqual(default.nodes, usable.nodes)
        self.assertLessEqual(usable.nodes, coverage.nodes)
        self.assertNotIn("Gel Processing Site Out of Bounds", default.events)
        self.assertIn("Gel Processing Site Out of Bounds", coverage.events)  # T20: only reachable via tricks
        self.assertIs(reachable_graph({}), default)

    def test_usable_tricks_match_playthrough_sim_logic(self) -> None:
        """With USABLE_TRICKS: reachable nodes, events and locations agree with playthrough_sim.World(tricks=...)
        and some location is reachable with fewer items than without tricks."""
        sim = load_playthrough_sim()
        if sim is None:
            self.skipTest("apworld/tools/playthrough_sim.py not found")
        tricks = dict(trick_data.USABLE_TRICKS)
        sim_world = sim.World(sim.load_data(), tricks=tricks)
        multiworld = multiworld_with_tricks(tricks)
        node_regions = {node_name(node): node for node in reachable_graph(tricks).nodes}
        locations = {loc.address - BASE_ID: loc for loc in multiworld.get_locations(1) if loc.address is not None}
        full = [n for n in pool_names() if RECORDS[n]["progression"]]
        rng = random.Random(9)
        inventories = [rng.sample(full, rng.randint(0, len(full) // 2)) for _ in range(30)]
        earlier = False
        default_world = sim.World(sim.load_data())
        for names in inventories:
            state = state_with(multiworld, 1, names)
            inv, _ = sim_world.inventory([RECORDS[n] for n in names + starting_names()])
            nodes, events, _, _ = sim_world.reach(inv)
            ap_nodes = {node for name, node in node_regions.items()
                        if multiworld.get_region(name, 1).can_reach(state)}
            self.assertEqual(ap_nodes, set(nodes), sorted(names))
            self.assertEqual({ev for ev in logic_data.EVENTS if state.has(ev, 1)}, set(events), sorted(names))
            ap_locations = {lid for lid, loc in locations.items() if loc.can_reach(state)}
            self.assertEqual(ap_locations, sim_world.reachable_locations(nodes, inv, events), sorted(names))
            d_nodes, d_events, _, _ = default_world.reach(dict(inv))
            earlier |= bool(ap_locations - default_world.reachable_locations(d_nodes, inv, d_events))
        self.assertTrue(earlier)
