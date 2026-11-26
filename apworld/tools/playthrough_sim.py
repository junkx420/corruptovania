"""Playthrough simulator for the generated APWorld data (T20, E18, T25/E22).

Works only on the data in apworld/metroidprime3/data (no randovania import), so it can also be used by the
APWorld tests (T04b). Two parts:

1. ``World``: a fast evaluator of the requirement trees (AP logic and "physical" game rules).
2. ``fill`` + ``play``: a random AP-style fill (assumed fill like Archipelago's fill_restrictive) and a player
   who follows the logic. Entering a dangerous event node triggers that event; the player then stands at the node
   and can only move on along real ways ("before X" is now false). Collecting a location means walking to its
   pickup node; if the player cannot walk back from there to where he stood, he now stands at the pickup node
   (a dead end, T08 B5). He only enters a location whose ``escape_requirement`` (E22) holds.

Modes of ``World.reach``:
    logic=True   AP logic: every "before <event>" counts as satisfied, connections carry the escape gate (E18),
                 a location is only collected (``placement``) once its escape_requirement holds (E22).
    logic=False  physical: "before X" is satisfied while X has not been triggered, connections use their base
                 requirement (without the escape gate), untriggered dangerous event nodes are not entered but
                 reported as ``hits`` (entering them triggers the event, the caller decides).

Setup (E23, T30): ``World(data, tricks=..., starting_items=...)``. ``tricks`` = {trick name: level 0-5} (default:
every trick off), used by the logic and by the player's physics alike. ``starting_items`` = item names the player
starts with (default: data/items.py STARTING_ITEMS); every default starting item left out goes into the pool and one
Missile Expansion leaves it per item, so the pool stays at 99 (E23).

Usage (from the repo root):
    venv/Scripts/python.exe apworld/tools/playthrough_sim.py [--seeds 100] [--first 0] [--eager 0.5] [-v]
        [--no-dead-end-rule] [--without "Morph Ball,Space Jump Boots"] [--start "Power Beam,..."]
        [--tricks "Movement=2,Knowledge=1"] [--trick-level 2] [--usable]
    venv/Scripts/python.exe apworld/tools/playthrough_sim.py --matrix [--seeds 100]   (check matrix, data/README.md)
    venv/Scripts/python.exe apworld/tools/playthrough_sim.py --start-table   (sphere 0 per starting-item choice)
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import itertools
import math
import random
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

DEFAULT_DATA = Path(__file__).resolve().parents[1] / "metroidprime3" / "data"
GOAL_EVENT = "Aurora Unit 313"
# E23: removed starting items go into the pool, one of these leaves it per item (the pool stays at 99).
POOL_FILLER = "Missile Expansion"
# E23: always kept (the client needs Power Beam > 0, scanning is mandatory); the others can be removed.
FIXED_STARTING_ITEMS = ("Power Beam", "Combat Visor", "Scan Visor")


def load_data(directory: Path = DEFAULT_DATA) -> SimpleNamespace:
    """Load the generated modules (logic, game, items, locations and, if present, tricks) from a directory."""

    def load(name: str) -> ModuleType:
        spec = importlib.util.spec_from_file_location(f"_mp3data_{name}", directory / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    names = ["logic", "game", "items", "locations"] + (["tricks"] if (directory / "tricks.py").is_file() else [])
    return SimpleNamespace(**{n: load(n) for n in names})


def _true(inv, evs, phys):
    return True


def _false(inv, evs, phys):
    return False


class World:
    """Compiled logic graph. ``data`` has the attributes logic, game, items, locations (modules or namespaces)."""

    def __init__(self, data, tricks: dict[str, int] | None = None, location_escapes: bool = True,
                 starting_items: list[str] | None = None) -> None:
        """``tricks``: trick levels (default: all off). ``starting_items``: item names (default: the data's starting
        items; see the module docstring for the pool). ``location_escapes=False`` ignores the escape_requirement of
        the locations (logic before E22)."""
        self.data = data
        logic, game = data.logic, data.game
        settings = game.SETTINGS
        self.tricks = dict(tricks or {})
        unknown = sorted(set(self.tricks) - set(game.TRICKS))
        if unknown:
            raise ValueError(f"unknown tricks: {unknown}")
        self.starting, self._pool = self._setup(starting_items)
        self.misc = settings["misc_resources"]
        self.version = settings["version_resources"]
        self.damage = settings["damage"]
        self.templates = logic.TEMPLATES
        self._tpl_cache: dict[str, tuple] = {}
        self.start = tuple(game.START_LOCATION)

        self.dangerous = {name: tuple(ev["node"]) for name, ev in logic.EVENTS.items() if "escape_requirement" in ev}
        self.dangerous_node = {node: name for name, node in self.dangerous.items()}
        self._gates: dict[str, object] = {}

        # connections: (from, to, logic_fn, logic_deps, phys_fn, phys_deps)
        self.out: dict[tuple, list[int]] = collections.defaultdict(list)
        self.conns: list[tuple] = []
        for conn in logic.CONNECTIONS:
            req = conn["requirement"]
            base = req["and"][0] if conn.get("escape_gate") else req
            lf, ld = self.compile(req)
            pf, pd = (lf, ld) if base is req else self.compile(base)
            self.out[tuple(conn["from"])].append(len(self.conns))
            self.conns.append((tuple(conn["from"]), tuple(conn["to"]), lf, ld, pf, pd))
        # event sources: (event, node, fn, deps)
        self.node_events: dict[tuple, list[int]] = collections.defaultdict(list)
        self.sources: list[tuple] = []
        for name, ev in logic.EVENTS.items():
            for src in ev["sources"]:
                fn, deps = self.compile(src["requirement"])
                self.node_events[tuple(src["node"])].append(len(self.sources))
                self.sources.append((name, tuple(src["node"]), fn, deps))
        self.loc_node = {loc["id"]: (loc["region"], loc["area"], loc["node"]) for loc in data.locations.LOCATIONS}
        self.node_loc = {node: lid for lid, node in self.loc_node.items()}
        # location rules (E22) as (fn, deps); data without the field (or location_escapes=False): always
        self.loc_rule = {
            loc["id"]: self.compile(loc.get("escape_requirement", {"and": []}) if location_escapes else {"and": []})
            for loc in data.locations.LOCATIONS}
        self.victory, _ = self.compile(game.VICTORY_REQUIREMENT)
        self.ships = [((r, a, n), self.compile(info["is_unlocked"])[0])
                      for r, region in logic.REGIONS.items() for a, area in region["areas"].items()
                      for n, info in area["nodes"].items() if info["type"] == "teleporter_network"]

    # ------------------------------------------------------------ requirement compiler
    def compile(self, req: dict) -> tuple:
        """Return (fn(inv, events, physical) -> bool, frozenset of keys ('i'|'e', name) the result depends on)."""
        if "and" in req or "or" in req:
            is_and = "and" in req
            parts = [self.compile(r) for r in req["and" if is_and else "or"]]
            deps = frozenset().union(*(d for _, d in parts)) if parts else frozenset()
            fns = tuple(f for f, _ in parts)
            if is_and:
                fns = tuple(f for f in fns if f is not _true)
                if any(f is _false for f in fns):
                    return _false, frozenset()
                if not fns:
                    return _true, frozenset()
                if len(fns) == 1:
                    return fns[0], deps
                return (lambda inv, evs, phys: all(f(inv, evs, phys) for f in fns)), deps
            fns = tuple(f for f in fns if f is not _false)
            if any(f is _true for f in fns):
                return _true, frozenset()
            if not fns:
                return _false, frozenset()
            if len(fns) == 1:
                return fns[0], deps
            return (lambda inv, evs, phys: any(f(inv, evs, phys) for f in fns)), deps
        kind, name, amount, negate = req["type"], req.get("name"), req.get("amount", 1), req.get("negate", False)
        if kind == "template":
            if name not in self._tpl_cache:
                self._tpl_cache[name] = self.compile(self.templates[name])
            return self._tpl_cache[name]
        if kind == "node":
            return _false, frozenset()
        if kind == "item":
            if negate:
                return _false, frozenset()  # "no item": not monotonic, does not occur
            return (lambda inv, evs, phys: inv.get(name, 0) >= amount), frozenset({("i", name)})
        if kind == "event":
            if negate:  # "before <event>": AP logic satisfied, physically satisfied until triggered
                return (lambda inv, evs, phys: not phys or name not in evs), frozenset({("e", name)})
            return (lambda inv, evs, phys: name in evs), frozenset({("e", name)})
        if kind == "damage":
            reductions = self.damage["reductions"].get(name, [])
            needed_base = int(amount * self.damage["strictness"])
            start, per_tank = self.damage["starting_energy"], self.damage["energy_per_tank"]

            def damage(inv, evs, phys):
                reduction = 1.0
                for item, multiplier in reductions:
                    if item is None or inv.get(item, 0) > 0:
                        reduction = min(reduction, multiplier)
                return start + per_tank * inv.get("Energy Tank", 0) > math.ceil(reduction * needed_base)

            deps = {("i", "Energy Tank")} | {("i", item) for item, _ in reductions if item}
            return damage, frozenset(deps)
        table = {"trick": self.tricks, "misc": self.misc, "version": self.version}.get(kind)
        if table is None:
            raise ValueError(f"unknown requirement type {kind!r}")
        have = table.get(name, 0)
        return (_true if (have < amount if negate else have >= amount) else _false), frozenset()

    # ------------------------------------------------------------ inventory
    @staticmethod
    def give(inv: dict, copies: collections.Counter, record: dict) -> list[str]:
        """Add one copy of an item record to ``inv``; return the changed resource names."""
        stages = record["stages"]
        k = copies[record["name"]]
        copies[record["name"]] += 1
        changed = []
        for resource, qty in stages[min(k, len(stages) - 1)]:
            inv[resource] = inv.get(resource, 0) + qty
            changed.append(resource)
        return changed

    def inventory(self, records) -> tuple[dict, collections.Counter]:
        inv: dict[str, int] = {}
        copies: collections.Counter = collections.Counter()
        for record in records:
            self.give(inv, copies, record)
        return inv, copies

    def _setup(self, starting_items: list[str] | None) -> tuple[list[dict], list[dict]]:
        """Starting item records and the pool (one record per copy) for a choice of starting items (E23)."""
        items = self.data.items
        default = list(items.STARTING_ITEMS)
        pool = [r for r in items.ITEMS for _ in range(r["count"])]
        if starting_items is None:
            return default, pool
        records = {r["name"]: r for r in list(items.ITEMS) + default}
        unknown = sorted(set(starting_items) - set(records))
        if unknown:
            raise ValueError(f"unknown starting items: {unknown}")
        names = list(dict.fromkeys(starting_items))
        filler = records[POOL_FILLER]
        for record in default:
            if record["name"] not in names:  # removed: into the pool, one filler out
                pool.append(record)
                pool.remove(filler)
        for name in names:
            if name not in {r["name"] for r in default}:  # a pool item given at the start: filler takes its place
                pool.remove(records[name])
                pool.append(filler)
        return [records[n] for n in names], pool

    def pool(self) -> list[dict]:
        """The AP pool, one record per copy."""
        return list(self._pool)

    def all_items(self) -> dict:
        return self.inventory(self.pool() + self.starting)[0]

    def sphere0(self) -> list[int]:
        """Locations the AP logic allows with the starting items alone (empty: the setup cannot start)."""
        inv, _ = self.inventory(self.starting)
        reached, evs, _, _ = self.reach(inv)
        return sorted(self.reachable_locations(reached, inv, evs))

    # ------------------------------------------------------------ reachability
    def reach(self, inv: dict, *, logic: bool = True, gated: bool | None = None, start=None, events=(),
              blocked_nodes=(), blocked_events=(), placement: dict | None = None,
              copies: collections.Counter | None = None):
        """Least fixpoint of reachable nodes and events.

        ``gated`` (default: = ``logic``): use the escape and re-entry gates on connections into dangerous event nodes.
        ``logic=True, gated=False`` is the logic as it was before E18 (used by the converter and for analyses).

        ``placement`` (location id -> item record): items at reached locations are collected on the way (sweep),
        in logic mode only once the location's escape_requirement holds (E22); ``inv``/``copies`` are then updated
        in place. Returns (reached nodes, events, hits, collected location ids).
        ``hits``: untriggered dangerous event nodes the player could enter (physical mode only).
        """
        phys = not logic
        evs = set(events)
        blocked_nodes = set(blocked_nodes)
        blocked_events = set(blocked_events)
        if copies is None:
            copies = collections.Counter()
        stop = {node for node, name in self.dangerous_node.items() if name not in evs} if phys else set()
        reached: set = set()
        hits: set = set()
        collected: list[int] = []
        done: set[int] = set()
        pending: dict[tuple, set] = collections.defaultdict(set)
        tasks: list[tuple[int, int]] = []  # (0, conn index), (1, source index) or (2, location id)
        conns, sources = self.conns, self.sources
        if gated is None:
            gated = logic
        fn_i, dep_i = (2, 3) if gated else (4, 5)

        def add_node(node) -> None:
            reached.add(node)
            tasks.extend((0, ci) for ci in self.out.get(node, ()))
            tasks.extend((1, si) for si in self.node_events.get(node, ()))
            if placement is not None:
                lid = self.node_loc.get(node)
                if lid is not None and lid in placement:
                    tasks.append((2, lid))

        for node in ([self.start] if start is None else start):
            if node not in reached:
                add_node(node)
        while tasks:
            kind, idx = tasks.pop()
            if kind == 0:
                conn = conns[idx]
                to = conn[1]
                if to in reached or to in blocked_nodes or (to in hits):
                    continue
                if conn[fn_i](inv, evs, phys):
                    if to in stop:
                        hits.add(to)
                    else:
                        add_node(to)
                else:
                    task = (0, idx)
                    for key in conn[dep_i]:
                        pending[key].add(task)
            elif kind == 1:
                name, _, fn, deps = sources[idx]
                if name in evs or name in blocked_events:
                    continue
                if fn(inv, evs, phys):
                    evs.add(name)
                    tasks.extend(pending.pop(("e", name), ()))
                else:
                    task = (1, idx)
                    for key in deps:
                        pending[key].add(task)
            else:
                if idx in done:
                    continue
                fn, deps = self.loc_rule[idx]
                if phys or fn(inv, evs, phys):
                    done.add(idx)
                    collected.append(idx)
                    for resource in self.give(inv, copies, placement[idx]):
                        tasks.extend(pending.pop(("i", resource), ()))
                else:
                    for key in deps:
                        pending[key].add((2, idx))
        return reached, evs, hits, collected

    def reachable_locations(self, reached, inv: dict | None = None, evs=None) -> set[int]:
        """Locations whose node is in ``reached``; with ``inv`` only those the AP logic allows (E22)."""
        if inv is None:
            return {lid for lid, node in self.loc_node.items() if node in reached}
        return {lid for lid, node in self.loc_node.items() if node in reached and self.location_ok(lid, inv, evs)}

    def location_ok(self, lid: int, inv: dict, evs) -> bool:
        """The location's escape_requirement (E22), evaluated like the AP logic does."""
        return self.loc_rule[lid][0](inv, evs, False)

    def can_return(self, lid: int, to: tuple, inv: dict, evs) -> bool:
        """Physically: from the pickup node of ``lid`` back to the node ``to`` (inventory and events as given)."""
        reached, _, _, _ = self.reach(inv, logic=False, start=[self.loc_node[lid]], events=evs)
        return to in reached

    def ship_reachable(self, node: tuple, inv: dict, evs) -> bool:
        """Physically: a ship (teleporter_network node whose is_unlocked holds) is reachable from ``node``."""
        reached, evs, _, _ = self.reach(inv, logic=False, start=[node], events=evs)
        return any(n in reached and fn(inv, evs, True) for n, fn in self.ships)

    def escape_ok(self, event: str, inv: dict, evs) -> bool:
        """The gate of a dangerous event (E18 escape_requirement and, if present, the E24 reentry_requirement),
        evaluated like the AP logic does."""
        fn = self._gates.get(event)
        if fn is None:
            ev = self.data.logic.EVENTS[event]
            parts = [ev["escape_requirement"]] + ([ev["reentry_requirement"]] if "reentry_requirement" in ev else [])
            fn = self._gates[event] = self.compile({"and": parts})[0]
        return fn(inv, evs, False)


# ---------------------------------------------------------------- fill
def fill(world: World, rng: random.Random, attempts: int = 20) -> dict[int, dict] | None:
    """AP-style random fill: progression items one by one (random order) onto random locations that are reachable
    with all still unplaced progression items + starting items + everything collectable (sweep). Then filler."""
    pool = world.pool()
    start = list(world.starting)
    progression = [r for r in pool if r["progression"]]
    filler = [r for r in pool if not r["progression"]]
    locations = sorted(world.loc_node)
    for _ in range(attempts):
        items = progression[:]
        rng.shuffle(items)
        placed: dict[int, dict] = {}
        ok = True
        while items:
            item = items.pop()
            inv, copies = world.inventory(items + start)
            reached, evs, _, _ = world.reach(inv, placement=placed, copies=copies)
            free = [lid for lid in locations if lid not in placed and world.loc_node[lid] in reached
                    and world.location_ok(lid, inv, evs)]
            if not free:
                ok = False
                break
            placed[rng.choice(free)] = item
        if not ok:
            continue
        rest = [lid for lid in locations if lid not in placed]
        rng.shuffle(filler)
        placed.update(zip(rest, filler))
        return placed
    return None


# ---------------------------------------------------------------- player
def play(world: World, placement: dict[int, dict], rng: random.Random | None = None, eager: float = 0.0,
         dead_end_rule: bool = True) -> dict:
    """A player who follows the logic.

    Each step looks at what is physically reachable from the current position. An untriggered dangerous event
    node may only be entered if its escape gate holds (what the AP logic asks of every connection into it), a
    location only if its escape_requirement holds (E22, what the AP logic asks of the location; ignored with
    ``dead_end_rule=False``). The player enters one of the allowed event nodes (random among them if ``rng``, else
    the first by name) when nothing new is left to collect, or earlier with probability ``eager``. Otherwise he
    collects the allowed locations: first every one he can walk back from to his position even without its item,
    then the others one by one. If he cannot walk back from a pickup node (with its item), he now stands there
    (recorded in ``dead_ends``) and the step ends. Entering an event node triggers the event; the player then
    stands at its node. He keeps playing after the goal (to see whether locations got lost) and stops when nothing
    is left. Won = goal event triggered. ``trapped`` = no ship is reachable from where he ended.
    """
    inv, copies = world.inventory(world.starting)
    evs: set[str] = set()
    collected: set[int] = set()
    pos = world.start
    order: list[str] = []
    dead_ends: list[int] = []
    while True:
        reached, evs, hits, _ = world.reach(inv, logic=False, start=[pos], events=evs)
        new = sorted(world.reachable_locations(reached) - collected)
        if dead_end_rule:
            new = [lid for lid in new if world.location_ok(lid, inv, evs)]
        allowed = [x for x in sorted(world.dangerous_node[n] for n in hits) if world.escape_ok(x, inv, evs)]
        if allowed and (not new or (rng is not None and eager and rng.random() < eager)):
            event = rng.choice(allowed) if rng is not None else allowed[0]
            evs.add(event)
            order.append(event)
            pos = world.dangerous[event]
            continue
        if not new:
            break
        risky = []
        for lid in new:
            if world.can_return(lid, pos, inv, evs):
                world.give(inv, copies, placement[lid])
                collected.add(lid)
            else:
                risky.append(lid)
        for lid in risky:
            world.give(inv, copies, placement[lid])
            collected.add(lid)
            if not world.can_return(lid, pos, inv, evs):
                dead_ends.append(lid)
                pos = world.loc_node[lid]
                break
    return {
        "won": GOAL_EVENT in evs,
        "collected": len(collected),
        "missing": sorted(set(world.loc_node) - collected),
        "triggered": order,
        "untriggered_dangerous": sorted(set(world.dangerous) - set(order)),
        "end": pos,
        "dead_ends": dead_ends,
        "trapped": not world.ship_reachable(pos, inv, evs),
    }


def simulate(world: World, seeds, verbose: bool = False, eager: float = 0.0, dead_end_rule: bool = True) -> dict:
    """Fill + play for each seed in ``seeds``. Returns a summary."""
    summary = collections.Counter()
    failures = []
    for seed in seeds:
        rng = random.Random(seed)
        placement = fill(world, rng)
        if placement is None:
            summary["fill_failed"] += 1
            failures.append((seed, "fill failed"))
            continue
        result = play(world, placement, rng, eager, dead_end_rule)
        summary["seeds"] += 1
        summary["won"] += result["won"]
        summary["all_99_collected"] += result["collected"] == len(world.loc_node)
        summary["trapped"] += result["trapped"]
        if not result["won"]:
            failures.append((seed, result))
        if verbose:
            print(f"seed {seed}: won={result['won']} collected={result['collected']} missing={result['missing']} "
                  f"untriggered={result['untriggered_dangerous']} dead_ends={result['dead_ends']} "
                  f"trapped={result['trapped']}", flush=True)
    return {"summary": dict(summary), "failures": failures}


# ---------------------------------------------------------------- check matrix (T30, data/README.md)
def usable_tricks(data) -> dict[str, int]:
    """USABLE_TRICKS of data/tricks.py at their recommended level (E23)."""
    return dict(data.tricks.USABLE_TRICKS)


def matrix_variants(data) -> list[tuple[str, dict]]:
    """The check matrix: (label, World keyword arguments)."""
    default = [r["name"] for r in data.items.STARTING_ITEMS]

    def without(*names: str) -> list[str]:
        return [n for n in default if n not in names]

    return [
        ("Standard", {}),
        ("without Morph Ball", {"starting_items": without("Morph Ball")}),
        ("without Morph Ball Bombs", {"starting_items": without("Morph Ball Bombs")}),
        ("without Space Jump Boots", {"starting_items": without("Space Jump Boots")}),
        ("without Charge Beam", {"starting_items": without("Charge Beam")}),
        ("only Power Beam + Combat/Scan Visor", {"starting_items": list(FIXED_STARTING_ITEMS)}),
        ("usable tricks at the recommended level", {"tricks": usable_tricks(data)}),
    ]


def run_variant(data, kwargs: dict, seeds, eager: float = 0.5) -> dict:
    """Sphere 0 and the simulator summary of one setup (``simulate`` skipped when sphere 0 is empty)."""
    world = World(data, **kwargs)
    sphere0 = world.sphere0()
    result = {"sphere0": sphere0, "summary": {}, "failures": []}
    if sphere0:
        result.update(simulate(world, seeds, eager=eager))
    return result


def start_table(data) -> list[tuple[tuple[str, ...], list[int]]]:
    """Sphere 0 for every choice of the removable starting items (E23): (removed items, locations)."""
    removable = [r["name"] for r in data.items.STARTING_ITEMS if r["name"] not in FIXED_STARTING_ITEMS]
    rows = []
    for k in range(len(removable) + 1):
        for removed in itertools.combinations(removable, k):
            names = [r["name"] for r in data.items.STARTING_ITEMS if r["name"] not in removed]
            rows.append((removed, World(data, starting_items=names).sphere0()))
    return rows


def _parse_tricks(text: str) -> dict[str, int]:
    out = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        name, _, level = part.rpartition("=")
        out[name.strip()] = int(level)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--eager", type=float,
                        help="probability to trigger an allowed dangerous event before collecting (0..1; "
                             "default 0, with --matrix 0.5)")
    parser.add_argument("--no-dead-end-rule", action="store_true",
                        help="counter-check: fill and player ignore the locations' escape_requirement (before E22)")
    parser.add_argument("--start", help="comma separated starting items (default: the data's starting items)")
    parser.add_argument("--without", help="comma separated default starting items to remove")
    parser.add_argument("--tricks", default="", help='trick levels, e.g. "Movement=2,Knowledge=1"')
    parser.add_argument("--trick-level", type=int, help="the same level for every trick")
    parser.add_argument("--usable", action="store_true", help="USABLE_TRICKS of data/tricks.py")
    parser.add_argument("--matrix", action="store_true",
                        help="run the check matrix (eager 0.5; fill failures allowed with only fixed starting items)")
    parser.add_argument("--start-table", action="store_true", help="sphere 0 for every starting-item choice")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    data = load_data(args.data)
    seeds = range(args.first, args.first + args.seeds)
    if args.start_table:
        for removed, sphere0 in start_table(data):
            print(f"without {', '.join(removed) or '-':55} sphere 0: {len(sphere0):>2} {sphere0}")
        return
    if args.matrix:
        failed = False
        for label, kwargs in matrix_variants(data):
            t0 = time.time()
            result = run_variant(data, kwargs, seeds, eager=0.5 if args.eager is None else args.eager)
            summary = result["summary"]
            filled = summary.get("seeds", 0)
            minimal_start = kwargs.get("starting_items") == list(FIXED_STARTING_ITEMS)
            ok = (bool(result["sphere0"]) and filled > 0 and (minimal_start or filled == len(seeds))
                  and summary["won"] == summary["all_99_collected"] == filled and summary["trapped"] == 0)
            failed |= not ok
            print(f"{label:40} sphere 0: {len(result['sphere0']):>2}  {summary}  {time.time() - t0:.0f}s", flush=True)
        sys.exit(1 if failed else 0)
    tricks = {t: args.trick_level for t in data.game.TRICKS} if args.trick_level is not None else {}
    if args.usable:
        tricks.update(usable_tricks(data))
    tricks.update(_parse_tricks(args.tricks))
    start = None
    if args.start:
        start = [n.strip() for n in args.start.split(",") if n.strip()]
    if args.without:
        drop = {n.strip() for n in args.without.split(",")}
        start = [n for n in (start or [r["name"] for r in data.items.STARTING_ITEMS]) if n not in drop]
    rule = not args.no_dead_end_rule
    world = World(data, tricks=tricks, location_escapes=rule, starting_items=start)
    print(f"sphere 0: {world.sphere0()}")
    t0 = time.time()
    result = simulate(world, seeds, args.verbose, args.eager or 0.0, rule)
    print(result["summary"], f"{time.time() - t0:.1f}s")
    for seed, why in result["failures"]:
        print("FAILED", seed, why)
    sys.exit(1 if result["failures"] else 0)


if __name__ == "__main__":
    main()
