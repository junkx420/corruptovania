"""Rule evaluation, reachability with all items, escape gates (E18) and a cross-check against playthrough_sim."""

import random
import unittest

from BaseClasses import CollectionState

from ..data import logic as logic_data
from ..items import RECORDS, pool_names, starting_names
from ..regions import GOAL_EVENT, node_name, reachable_graph
from ..rules import ALWAYS, NEVER, RuleCompiler, StaticState
from . import MP3TestBase, load_playthrough_sim


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

    def test_trick_never(self) -> None:
        self.assertIs(self.c.compile({"type": "trick", "name": "Bomb Jump", "amount": 1}), NEVER)

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
        """Reachable nodes and events agree with playthrough_sim.World.reach(logic=True) for random inventories."""
        sim = load_playthrough_sim()
        if sim is None:
            self.skipTest("apworld/tools/playthrough_sim.py not found")
        sim_world = sim.World(sim.load_data())
        full = [n for n in pool_names() if RECORDS[n]["progression"]]
        rng = random.Random(7)
        node_regions = {node_name(node): node for node in reachable_graph().nodes}
        for _ in range(40):
            names = rng.sample(full, rng.randint(0, len(full)))
            state = self._state_with(names)
            inv, _ = sim_world.inventory([RECORDS[n] for n in names + starting_names()])
            nodes, events, _, _ = sim_world.reach(inv)
            ap_nodes = {node for name, node in node_regions.items()
                        if self.multiworld.get_region(name, self.player).can_reach(state)}
            self.assertEqual(ap_nodes, set(nodes), sorted(names))
            ap_events = {ev for ev in logic_data.EVENTS if state.has(ev, self.player)}
            self.assertEqual(ap_events, set(events), sorted(names))
