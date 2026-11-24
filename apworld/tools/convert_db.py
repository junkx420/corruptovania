"""Convert the Corruptovania (Randovania) prime3 logic into standalone Python data for the APWorld.

Usage (from the repo root):
    venv/Scripts/python.exe apworld/tools/convert_db.py [--out apworld/metroidprime3/data]

The logic is loaded through Randovania's own loader (filtered_database / pool_creator / bootstrap),
never by parsing the JSON ourselves. The output is declarative and imports nothing.

Output files (see apworld/metroidprime3/data/README.md for the format):
    logic.py      REGIONS, CONNECTIONS, EVENTS, TEMPLATES, NODE_TYPES
    locations.py  LOCATIONS (99, id = pickup index 1-99), UNPATCHED_LOCATION (index 0, E13)
    items.py      ITEMS (AP pool, 99 items incl. Hypermode, one Missile Expansion less, E17), STARTING_ITEMS
    game.py       VICTORY_REQUIREMENT, START_LOCATION, SETTINGS, TRICKS, requirement kind statistics

Dangerous events (E18): every event that occurs negated ("before <event>") gets an escape_requirement (way from its
event node back to a ship in the state "after X", see EscapeSolver); it is ANDed onto every connection into the event
node. "before <event>" itself stays in the data and counts as satisfied in the logic.

The output is deterministic (no set iteration, no timestamps).
"""

from __future__ import annotations

import argparse
import collections
import pprint
from pathlib import Path

from randovania.game.game_enum import RandovaniaGame
from randovania.game_description import default_database
from randovania.game_description.db.dock import DockLockType
from randovania.game_description.db.dock_node import DockNode
from randovania.game_description.db.event_node import EventNode
from randovania.game_description.db.node import GenericNode
from randovania.game_description.db.pickup_node import PickupNode
from randovania.game_description.db.teleporter_network_node import TeleporterNetworkNode
from randovania.game_description.requirements.node_requirement import NodeRequirement
from randovania.game_description.requirements.requirement_and import RequirementAnd
from randovania.game_description.requirements.requirement_or import RequirementOr
from randovania.game_description.requirements.requirement_template import RequirementTemplate
from randovania.game_description.requirements.resource_requirement import ResourceRequirement
from randovania.game_description.resources.resource_collection import ResourceCollection
from randovania.game_description.resources.resource_type import ResourceType
from randovania.generator.pickup_pool import pool_creator
from randovania.layout import filtered_database
from randovania.layout.base.trick_level import LayoutTrickLevel
from randovania.layout.versioned_preset import VersionedPreset

GAME = RandovaniaGame.METROID_PRIME_CORRUPTION
# Pure bookkeeping counter of Randovania, never used by the logic.
IGNORED_RESOURCES = frozenset({"Item Percentage"})
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "apworld" / "metroidprime3" / "data"

# Requirement kinds. CONVERTED: fully expressed in the output. UNSUPPORTED: kept in the output
# but cannot be evaluated faithfully by AP; the MVP evaluates them as "not satisfied".
CONVERTED_KINDS = frozenset(
    {"and", "or", "template", "item", "event", "trick", "damage", "misc", "misc_negated", "version"}
)
UNSUPPORTED_KINDS = {
    "event_negated": "'Before <event>' is not monotonic. Counts as satisfied; the escape_requirement on every "
                     "connection into the event node keeps the player from being trapped (E18).",
    "item_negated": "'No <item>' is not monotonic. MVP: not satisfied.",
    "node": "NodeRequirement (node resource). MVP: not satisfied.",
}
TYPE_NAMES = {
    ResourceType.ITEM: "item",
    ResourceType.EVENT: "event",
    ResourceType.TRICK: "trick",
    ResourceType.DAMAGE: "damage",
    ResourceType.VERSION: "version",
    ResourceType.MISC: "misc",
}
NETWORK_EVENT = "Teleporter Network: {}"
# E17: Hypermode goes into the AP pool, one of these leaves it, so the pool stays at 99 (= locations).
DROPPED_FROM_POOL = "Missile Expansion"
LOCK_EVENT = "Dock Lock: {} - {} - {}"


def classify(req) -> str:
    """Return the kind of a single requirement object (not recursive)."""
    if isinstance(req, RequirementAnd):
        return "and"
    if isinstance(req, RequirementOr):
        return "or"
    if isinstance(req, RequirementTemplate):
        return "template"
    if isinstance(req, NodeRequirement):
        return "node"
    if isinstance(req, ResourceRequirement):
        name = TYPE_NAMES.get(req.resource.resource_type, f"unknown_resource:{req.resource.resource_type.name}")
        if req.negate and name not in ("trick", "damage", "version"):
            return f"{name}_negated"
        return name
    return f"unknown:{type(req).__name__}"


def ref(node) -> tuple[str, str, str]:
    ident = node.identifier
    return (ident.area_identifier.region, ident.area_identifier.area, ident.node)


class Converter:
    def __init__(self) -> None:
        game_data = GAME.data
        preset_path = GAME.data_path.joinpath("presets", game_data.presets[0]["path"])
        self.preset = VersionedPreset.from_file_sync(preset_path).get_preset()
        self.config = self.preset.configuration
        self.game = filtered_database.game_description_for_layout(self.config)
        self.rdb = self.game.resource_database
        self.kind_counts: collections.Counter[str] = collections.Counter()

    # ---------------- requirements ----------------
    def req(self, r, count: bool = True) -> dict:
        kind = classify(r)
        if count:
            self.kind_counts[kind] += 1
        if kind in ("and", "or"):
            return {kind: [self.req(i, count) for i in r.items]}
        if kind == "template":
            return {"type": "template", "name": r.template_name}
        if kind == "node":
            return {"type": "node", "node": tuple(str(x) for x in (r.node_identifier.as_string,))}
        if kind.startswith("unknown"):
            raise ValueError(f"Unknown requirement type {kind}: {r}")
        out = {"type": TYPE_NAMES[r.resource.resource_type], "name": r.resource.long_name, "amount": r.amount}
        if r.negate:
            out["negate"] = True
        return out

    @staticmethod
    def all_of(parts: list[dict]) -> dict:
        parts = [p for p in parts if p != {"and": []}]
        return parts[0] if len(parts) == 1 else {"and": parts}

    # ---------------- graph ----------------
    def convert_graph(self):
        regions: dict = {}
        connections: list = []
        events: dict = {
            e.long_name: {"kind": "db", "sources": []} for e in self.rdb.event
        }
        node_types: collections.Counter[str] = collections.Counter()
        tp_nodes: dict[str, list] = collections.defaultdict(list)
        rl = self.game.region_list

        def lock_req(dock: DockNode):
            w = dock.default_dock_weakness
            r = dock.override_default_lock_requirement or w.lock.requirement
            return self.req(r)

        for region in rl.regions:
            areas = {}
            for area in region.areas:
                nodes = {}
                for node in area.nodes:
                    if node.is_derived_node:
                        node_types[f"derived:{type(node).__name__}"] += 1
                        continue
                    info: dict
                    if isinstance(node, DockNode):
                        node_types["dock"] += 1
                        w = node.default_dock_weakness
                        info = {"type": "dock", "dock_type": node.dock_type.short_name, "weakness": w.name,
                                "target": ref(rl.node_by_identifier(node.default_connection))}
                        target = rl.node_by_identifier(node.default_connection)
                        open_r = self.req(node.override_default_open_requirement or w.requirement)
                        parts = [open_r]
                        if w.lock is not None:
                            info["lock"] = w.lock.lock_type.name
                            parts.append({"type": "event", "name": LOCK_EVENT.format(*ref(node)), "amount": 1})
                        if isinstance(target, DockNode) and target.default_dock_weakness.lock is not None:
                            parts.append({"type": "event", "name": LOCK_EVENT.format(*ref(target)), "amount": 1})
                        connections.append({"from": ref(node), "to": ref(target), "kind": "dock",
                                            "requirement": self.all_of(parts)})
                        # lock events (faithful to DockNode._lock_connection / DockLockNode)
                        bw = target.default_dock_weakness if isinstance(target, DockNode) else None
                        back_lock = bw.lock if bw is not None and bw is not w else None
                        if w.lock is not None or back_lock is not None:
                            lparts = [lock_req(node)] if w.lock is not None else []
                            if back_lock is not None and back_lock.lock_type == DockLockType.FRONT_BLAST_BACK_BLAST:
                                lparts.append(self.req(back_lock.requirement))
                            lr = self.all_of(lparts) if lparts else {"and": []}
                            if w.lock is not None:
                                events.setdefault(LOCK_EVENT.format(*ref(node)), {"kind": "dock_lock", "sources": []})[
                                    "sources"].append({"node": ref(node), "requirement": lr})
                            if bw is not None and w.can_unlock_from_back(bw):
                                events.setdefault(LOCK_EVENT.format(*ref(target)), {"kind": "dock_lock", "sources": []})[
                                    "sources"].append({"node": ref(node), "requirement": lr})
                    elif isinstance(node, PickupNode):
                        node_types["pickup"] += 1
                        info = {"type": "pickup", "pickup_index": node.pickup_index.index,
                                "category": node.location_category.value}
                    elif isinstance(node, EventNode):
                        node_types["event"] += 1
                        info = {"type": "event", "event": node.event.long_name}
                        events[node.event.long_name]["sources"].append({"node": ref(node), "requirement": {"and": []}})
                    elif isinstance(node, TeleporterNetworkNode):
                        node_types["teleporter_network"] += 1
                        info = {"type": "teleporter_network", "network": node.network,
                                "is_unlocked": self.req(node.is_unlocked),
                                "requirement_to_activate": self.req(node.requirement_to_activate)}
                        tp_nodes[node.network].append(node)
                    elif type(node) is GenericNode:
                        node_types["generic"] += 1
                        info = {"type": "generic"}
                    else:
                        raise ValueError(f"Unknown node type {type(node).__name__} at {ref(node)}")
                    info["heal"] = node.heal
                    nodes[node.name] = info
                    for tgt, r in area.connections.get(node, {}).items():
                        if tgt.is_derived_node:
                            continue
                        connections.append({"from": ref(node), "to": ref(tgt), "kind": "area",
                                            "requirement": self.req(r)})
                areas[area.name] = {"nodes": nodes}
            regions[region.name] = {"areas": areas}

        start = self.config.starting_location.locations
        for network, members in sorted(tp_nodes.items()):
            ev = NETWORK_EVENT.format(network)
            sources = []
            for n in members:
                if n.identifier in start:
                    sources.append({"node": ref(n), "requirement": {"and": []}, "note": "starting node"})
                sources.append({"node": ref(n), "requirement": self.all_of(
                    [self.req(n.is_unlocked, False), self.req(n.requirement_to_activate, False)])})
            events[ev] = {"kind": "teleporter_network", "sources": sources}
            for a in members:
                for b in members:
                    if a is not b:
                        connections.append({"from": ref(a), "to": ref(b), "kind": "teleporter_network",
                                            "requirement": self.all_of([
                                                self.req(a.is_unlocked, False),
                                                {"type": "event", "name": ev, "amount": 1},
                                                self.req(b.is_unlocked, False)])})
        return regions, connections, events, dict(sorted(node_types.items()))

    def check_kinds(self) -> None:
        """Fail loudly if a requirement kind occurs that is neither converted nor known-unsupported."""
        unknown = sorted(set(self.kind_counts) - CONVERTED_KINDS - set(UNSUPPORTED_KINDS))
        if unknown:
            raise ValueError(f"Unknown requirement kinds in the database: {unknown}")

    # ---------------- locations ----------------
    def convert_locations(self) -> tuple[list[dict], dict]:
        """99 AP locations (id = pickup index 1-99). Index 0 is never patched (E13) and kept separately."""
        found: dict[int, dict] = {}
        for region in self.game.region_list.regions:
            for area in region.areas:
                for node in area.nodes:
                    if isinstance(node, PickupNode):
                        index = node.pickup_index.index
                        if index in found:
                            raise ValueError(f"Duplicate pickup index {index}")
                        found[index] = {
                            "id": index,
                            "name": f"{region.name} - {area.name} - {node.name}",
                            "region": region.name,
                            "area": area.name,
                            "node": node.name,
                            "category": node.location_category.value,
                        }
        if sorted(found) != list(range(100)):
            raise ValueError(f"Pickup indices are not exactly 0-99: {sorted(found)}")
        locations = [found[i] for i in range(1, 100)]
        if len({loc["name"] for loc in locations}) != len(locations):
            raise ValueError("Location names are not unique")
        return locations, found[0]

    # ---------------- items ----------------
    def vanilla_item_of_location_0(self) -> str:
        """The standard pickup whose original location is pickup index 0 (information only, E17)."""
        db = default_database.pickup_database_for_game(GAME)
        names = [n for n, d in db.standard_pickups.items() if any(i.index == 0 for i in d.original_locations)]
        if len(names) != 1:
            raise ValueError(f"Expected exactly one vanilla item at pickup 0, got {names}")
        return names[0]

    @staticmethod
    def stages(pickup) -> list[list[tuple[str, int]]]:
        """What each copy gives. One entry per progressive stage (n-th copy gives stage n), else one entry."""
        return [
            [(r.long_name, q) for r, q in cond.resources if r.long_name not in IGNORED_RESOURCES]
            for cond in pickup.conditional_resources
        ]

    def required_amounts(self, files_logic: dict) -> dict[str, int]:
        """Highest amount of each item resource that any requirement asks for."""
        needed: dict[str, int] = {}

        def walk(r: dict) -> None:
            if "and" in r or "or" in r:
                for sub in r.get("and", []) + r.get("or", []):
                    walk(sub)
            elif r.get("type") == "item":
                needed[r["name"]] = max(needed.get(r["name"], 0), r["amount"])

        for conn in files_logic["CONNECTIONS"]:
            walk(conn["requirement"])
        for tpl in files_logic["TEMPLATES"].values():
            walk(tpl)
        for event in files_logic["EVENTS"].values():
            for src in event["sources"]:
                walk(src["requirement"])
        walk(self.req(self.game.victory_condition, False))
        for info_region in files_logic["REGIONS"].values():
            for area in info_region["areas"].values():
                for node in area["nodes"].values():
                    for key in ("is_unlocked", "requirement_to_activate"):
                        if key in node:
                            walk(node[key])
        return needed

    def convert_items(self, needed: dict[str, int]) -> tuple[list[dict], list[dict]]:
        """AP pool (E17): the standard pool (100) minus one Missile Expansion (the last one) = 99 items.
        Hypermode (vanilla item of the unpatched location 0) stays in the pool."""
        pool = pool_creator.calculate_pool_results(self.config, self.game)
        to_place = list(pool.to_place)
        drop = [i for i, p in enumerate(to_place) if p.name == DROPPED_FROM_POOL]
        if not drop:
            raise ValueError(f"Standard pool contains no {DROPPED_FROM_POOL!r}")
        to_place.pop(drop[-1])

        def group(pickups) -> dict[str, list]:
            grouped: dict[str, list] = {}
            for p in pickups:
                grouped.setdefault(p.name, []).append(p)
            return grouped

        shuffled, starting = group(to_place), group(pool.starting)
        all_by_name = {**shuffled, **starting}
        # the item that opens a launcher lock = the item with unlocks_resource for the same locked resource
        openers = {
            ps[0].resource_lock.item_to_lock.long_name: ps[0]
            for ps in all_by_name.values()
            if ps[0].unlocks_resource and ps[0].resource_lock is not None
        }

        def record(ps: list) -> dict:
            p = ps[0]
            stages = self.stages(p)
            gives = {res for stage in stages for res, _ in stage}
            progression = any(res in needed for res in gives)
            lock = None
            if p.resource_lock is not None:
                lk = p.resource_lock
                opener = openers.get(lk.item_to_lock.long_name)
                lock = {"locked_by": lk.locked_by.long_name, "item": lk.item_to_lock.long_name,
                        "temporary": lk.temporary_item.long_name, "respects_lock": p.respects_lock,
                        "opened_by": opener.name if opener is not None else None}
                if not p.unlocks_resource and opener is not None:
                    # An expansion adds nothing logic relevant if its opener already gives the maximum required.
                    opener_gain = dict(self.stages(opener)[0])
                    if all(opener_gain.get(res, 0) >= needed.get(res, 0) for res in gives if res in needed):
                        progression = False
            return {
                "name": p.name,
                "category": p.gui_category.name,
                "location_category": p.generator_params.preferred_location_category.value,
                "count": len(ps),
                "progression": progression,
                "progressive": len(stages) > 1,
                "is_expansion": p.is_expansion,
                "unlocks_lock": p.unlocks_resource,
                "lock": lock,
                "stages": stages,
            }

        return [record(ps) for ps in shuffled.values()], [record(ps) for ps in starting.values()]

    # ---------------- settings ----------------
    def convert_settings(self) -> dict:
        cfg = self.config
        bootstrap = self.game_bootstrap()
        misc_on = set(bootstrap._get_enabled_misc_resources(cfg, self.rdb))
        start = cfg.starting_location.locations
        if len(start) != 1:
            raise ValueError(f"Expected exactly one starting location, got {len(start)}")
        settings = {
            "preset": self.preset.name,
            "starting_location": ref(self.game.region_list.node_by_identifier(start[0])),
            "trick_level": {
                "minimal_logic": cfg.trick_level.minimal_logic,
                "default_level": 0,
                "levels": {t.long_name: cfg.trick_level.level_for_trick(t).as_number for t in self.rdb.trick},
            },
            "damage": {
                "strictness": cfg.damage_strictness.value,
                "starting_energy": cfg.energy_per_tank - 1,
                "energy_per_tank": cfg.energy_per_tank,
                "reductions": {
                    d.long_name: [(r.inventory_item.long_name if r.inventory_item else None, r.damage_multiplier)
                                  for r in self.rdb.damage_reductions.get(d, [])]
                    for d in self.rdb.damage
                },
            },
            "misc_resources": {m.long_name: int(m.short_name in misc_on) for m in self.rdb.misc},
            "version_resources": dict(
                (r.long_name, q) for r, q in bootstrap.version_resources_for_game(cfg, self.rdb)),
            "other": {
                "teleporters": cfg.teleporters.mode.value,
                "skip_final_bosses": cfg.teleporters.skip_final_bosses,
                "dock_rando": cfg.dock_rando.mode.value,
                "available_locations": cfg.available_locations.randomization_mode.value,
                "start_with_corrupted_hypermode": cfg.start_with_corrupted_hypermode,
                "MP3Update": cfg.MP3Update,
                "disable_deflicker": cfg.disable_deflicker,
            },
        }
        return settings

    def game_bootstrap(self):
        return GAME.generator.bootstrap

    def trick_table(self) -> dict:
        return {t.long_name: {"short_name": t.short_name} for t in self.rdb.trick}

    # ---------------- run ----------------
    def run(self) -> dict[str, dict]:
        regions, connections, events, node_types = self.convert_graph()
        templates = {name: self.req(t.requirement) for name, t in self.rdb.requirement_template.items()}
        victory = self.req(self.game.victory_condition)
        self.check_kinds()
        logic = {"REGIONS": regions, "CONNECTIONS": connections, "EVENTS": events,
                 "TEMPLATES": templates, "NODE_TYPES": node_types}
        locations, location_0 = self.convert_locations()
        location_0["vanilla_item"] = self.vanilla_item_of_location_0()
        items, starting_items = self.convert_items(self.required_amounts(logic))
        settings = self.convert_settings()
        files = {
            "logic.py": logic,
            "game.py": {"VICTORY_REQUIREMENT": victory,
                        "START_LOCATION": settings["starting_location"],
                        "SETTINGS": settings,
                        "TRICKS": self.trick_table(),
                        "TRICK_LEVEL_NAMES": {lv.as_number: lv.value for lv in LayoutTrickLevel},
                        "REQUIREMENT_KINDS": dict(sorted(self.kind_counts.items())),
                        "UNSUPPORTED_KINDS": {k: {"count": self.kind_counts.get(k, 0), "reason": v}
                                              for k, v in UNSUPPORTED_KINDS.items()}},
            "locations.py": {"LOCATIONS": locations, "UNPATCHED_LOCATION": location_0},
            "items.py": {"ITEMS": items, "STARTING_ITEMS": starting_items},
        }
        attach_escape_requirements(files)
        return files


# ---------------------------------------------------------------- escape requirements (E18)
# A requirement in disjunctive normal form: a list of terms (OR), each term a dict {(type, name): amount} (AND).
# TRUE = [{}], FALSE = []. Terms are kept minimal: a term that needs at least everything another term needs is dropped.
TRUE: list = [{}]
FALSE: list = []


def _implies(stronger: dict, weaker: dict) -> bool:
    """True if every inventory that satisfies ``stronger`` also satisfies ``weaker``."""
    return all(stronger.get(k, -1) >= v for k, v in weaker.items())


def dnf_or(*alternatives: list) -> list:
    terms = sorted((t for alt in alternatives for t in alt), key=len)
    out: list = []
    for t in terms:
        if not any(_implies(t, o) for o in out):
            out.append(t)
    return out


def dnf_and(a: list, b: list) -> list:
    if not a or not b:
        return FALSE
    merged = []
    for x in a:
        for y in b:
            t = dict(x)
            for k, v in y.items():
                if t.get(k, -1) < v:
                    t[k] = v
            merged.append(t)
    return dnf_or(merged)


def dnf_to_requirement(dnf: list) -> dict:
    """Deterministic requirement tree of a DNF: {"and": []} = TRUE, {"or": []} = FALSE."""

    def atom(key, amount):
        return {"type": key[0], "name": key[1], "amount": amount}

    terms = sorted((sorted(t.items()) for t in dnf), key=lambda t: (len(t), t))
    reqs = []
    for t in terms:
        atoms = [atom(k, v) for k, v in t]
        reqs.append(atoms[0] if len(atoms) == 1 else {"and": atoms})
    if not reqs:
        return {"or": []}
    if reqs == [{"and": []}]:
        return {"and": []}
    return reqs[0] if len(reqs) == 1 else {"or": reqs}


def requirement_atoms(req: dict, templates: dict, out: set | None = None) -> set:
    """All (type, name) leaves of a requirement tree, templates expanded."""
    out = set() if out is None else out
    if "and" in req or "or" in req:
        for r in req.get("and", []) + req.get("or", []):
            requirement_atoms(r, templates, out)
    elif req["type"] == "template":
        requirement_atoms(templates[req["name"]], templates, out)
    else:
        out.add((req["type"], req.get("name"), bool(req.get("negate", False))))
    return out


def dangerous_events(logic: dict, victory: dict) -> list[str]:
    """Every event that occurs negated ("before <event>") anywhere in the data, sorted."""
    found: set[str] = set()
    trees = [c["requirement"] for c in logic["CONNECTIONS"]] + list(logic["TEMPLATES"].values()) + [victory]
    trees += [s["requirement"] for e in logic["EVENTS"].values() for s in e["sources"]]
    for info_region in logic["REGIONS"].values():
        for area in info_region["areas"].values():
            for node in area["nodes"].values():
                trees += [node[k] for k in ("is_unlocked", "requirement_to_activate") if k in node]
    for tree in trees:
        for kind, name, negate in _atoms_no_tpl(tree):
            if kind == "event" and negate:
                found.add(name)
    return sorted(found)


def _atoms_no_tpl(req: dict):
    if "and" in req or "or" in req:
        for r in req.get("and", []) + req.get("or", []):
            yield from _atoms_no_tpl(r)
    else:
        yield req["type"], req.get("name"), bool(req.get("negate", False))


class EscapeSolver:
    """escape_requirement of a dangerous event X (E18).

    State "after X": X is triggered ("before X" false, event X true), the player stands at the event node and owns
    only what he had when entering it. The requirement says when a ship (teleporter_network node whose
    ``is_unlocked`` holds) is reachable from there. It is the least fixpoint of "node reachable from the event node"
    over DNFs, evaluated symbolically:
        item / damage         -> atom
        trick / misc / version -> constant from SETTINGS (preset: all tricks off). With tricks enabled later the
                                 gate is stricter than necessary, never too loose.
        before Y (Y != X)     -> satisfied (as everywhere in the logic)
        event Y               -> atom, unless Y is only reachable after X (with all items, X's node blocked):
                                 then Y is replaced by its own requirement from the event node (recursively).
        "no item", node       -> not satisfied (do not occur)
    """

    def __init__(self, logic: dict, settings: dict) -> None:
        self.logic = logic
        self.settings = settings
        self.templates = logic["TEMPLATES"]
        self.targets = []
        for rname, info_region in logic["REGIONS"].items():
            for aname, area in info_region["areas"].items():
                for nname, node in area["nodes"].items():
                    if node["type"] == "teleporter_network":
                        self.targets.append(((rname, aname, nname), node["is_unlocked"]))
        self.out = collections.defaultdict(list)
        for conn in logic["CONNECTIONS"]:
            self.out[tuple(conn["from"])].append(conn)

    def static(self, kind: str, name: str, amount: int, negate: bool) -> bool:
        table = {"trick": self.settings["trick_level"]["levels"], "misc": self.settings["misc_resources"],
                 "version": self.settings["version_resources"]}[kind]
        have = table.get(name, 0)
        return have < amount if negate else have >= amount

    def to_dnf(self, req: dict, x: str, inlined: set[str], ev_dnf: dict) -> list:
        if "and" in req:
            acc = TRUE
            for r in req["and"]:
                acc = dnf_and(acc, self.to_dnf(r, x, inlined, ev_dnf))
                if not acc:
                    break
            return acc
        if "or" in req:
            return dnf_or(*(self.to_dnf(r, x, inlined, ev_dnf) for r in req["or"]))
        kind, name, amount, negate = req["type"], req.get("name"), req.get("amount", 1), req.get("negate", False)
        if kind == "template":
            return self.to_dnf(self.templates[name], x, inlined, ev_dnf)
        if kind == "event":
            if negate:
                return FALSE if name == x else TRUE
            if name == x:
                return TRUE
            if name in inlined:
                return ev_dnf.get(name, FALSE)
            return [{("event", name): 1}]
        if kind in ("item", "node"):
            if kind == "node" or negate:
                return FALSE
            return [{("item", name): amount}]
        if kind in ("trick", "damage") and negate:
            raise ValueError(f"negated {kind} requirement is not supported: {req}")
        if kind == "damage":
            return TRUE if amount <= 0 else [{(kind, name): amount}]
        if kind in ("trick", "misc", "version"):
            return TRUE if self.static(kind, name, amount, negate) else FALSE
        raise ValueError(f"Unknown requirement type {kind!r}")

    def solve(self, x: str, node: tuple, inlined: set[str]) -> list:
        """Worklist fixpoint with delta propagation. Nothing is propagated out of a ship node: every term that
        passes a ship is implied by a term that already reached it."""
        target_nodes = {n for n, _ in self.targets}
        reach: dict[tuple, list] = {node: TRUE}
        delta: dict[tuple, list] = {node: TRUE}
        ev_dnf: dict[str, list] = {}
        sources = collections.defaultdict(list)  # node -> [(event, requirement)]
        for y in sorted(inlined):
            for s in self.logic["EVENTS"][y]["sources"]:
                sources[tuple(s["node"])].append((y, s["requirement"]))
        users = collections.defaultdict(list)  # inlined event -> connections whose requirement uses it
        static_cache: dict[int, list] = {}
        dynamic: set[int] = set()
        for conns in self.out.values():
            for conn in conns:
                used = {n for k, n, neg in requirement_atoms(conn["requirement"], self.templates)
                        if k == "event" and not neg and n in inlined}
                for y in used:
                    users[y].append(conn)
                if used:
                    dynamic.add(id(conn["requirement"]))
        for _, reqs in sources.items():
            for _, r in reqs:
                if any(k == "event" and not neg and n in inlined for k, n, neg in requirement_atoms(r, self.templates)):
                    dynamic.add(id(r))

        def req_dnf(req: dict) -> list:
            key = id(req)
            if key in dynamic:
                return self.to_dnf(req, x, inlined, ev_dnf)
            if key not in static_cache:
                static_cache[key] = self.to_dnf(req, x, inlined, ev_dnf)
            return static_cache[key]

        queue = [node]
        changed_events: list[str] = []

        def add_node(to: tuple, gain: list) -> None:
            old = reach.get(to, FALSE)
            added = [t for t in dnf_or(gain) if not any(_implies(t, o) for o in old)]
            if not added:
                return
            reach[to] = dnf_or(old, added)
            delta[to] = dnf_or(delta.get(to, FALSE), added)
            queue.append(to)

        def add_event(y: str, gain: list) -> None:
            old = ev_dnf.get(y, FALSE)
            if all(any(_implies(t, o) for o in old) for t in gain):
                return
            ev_dnf[y] = dnf_or(old, gain)
            changed_events.append(y)

        while queue or changed_events:
            while queue:
                frm = queue.pop()
                d = delta.pop(frm, FALSE)
                if not d:
                    continue
                for y, r in sources.get(frm, ()):
                    gain = dnf_and(d, req_dnf(r))
                    if gain:
                        add_event(y, gain)
                if frm in target_nodes and frm != node:
                    continue
                for conn in self.out.get(frm, ()):
                    gain = dnf_and(d, req_dnf(conn["requirement"]))
                    if gain:
                        add_node(tuple(conn["to"]), gain)
            while changed_events:
                y = changed_events.pop()
                for conn in users[y]:
                    frm = tuple(conn["from"])
                    if frm in reach and not (frm in target_nodes and frm != node):
                        gain = dnf_and(reach[frm], req_dnf(conn["requirement"]))
                        if gain:
                            add_node(tuple(conn["to"]), gain)
                for n, reqs in sources.items():
                    if n in reach:
                        for z, r in reqs:
                            if id(r) in dynamic:
                                gain = dnf_and(reach[n], req_dnf(r))
                                if gain:
                                    add_event(z, gain)
        return dnf_or(*(dnf_and(reach[n], self.to_dnf(unlocked, x, inlined, ev_dnf))
                        for n, unlocked in self.targets if n in reach))


def attach_escape_requirements(files: dict[str, dict]) -> None:
    """E18: compute escape_requirement for every dangerous event, store it in EVENTS and AND it onto every
    connection into the event node (marked with ``escape_gate``). Works on the generated data only."""
    import importlib.util
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location("playthrough_sim", Path(__file__).with_name("playthrough_sim.py"))
    playthrough_sim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(playthrough_sim)

    logic, game = files["logic.py"], files["game.py"]
    data = SimpleNamespace(**{k[:-3]: SimpleNamespace(**v) for k, v in files.items()})
    world = playthrough_sim.World(data)
    all_inv = world.all_items()
    _, all_events, _, _ = world.reach(all_inv)
    solver = EscapeSolver(logic, game["SETTINGS"])
    for x in dangerous_events(logic, game["VICTORY_REQUIREMENT"]):
        event = logic["EVENTS"][x]
        nodes = {tuple(s["node"]) for s in event["sources"]}
        if event["kind"] != "db" or len(nodes) != 1:
            raise ValueError(f"dangerous event {x!r} must have exactly one event node, has {sorted(nodes)}")
        (node,) = nodes
        _, without_x, _, _ = world.reach(all_inv, blocked_nodes={node}, blocked_events={x})
        inlined = {y for y in all_events if y not in without_x and y != x}
        escape = dnf_to_requirement(solver.solve(x, node, inlined))
        event["node"] = node
        event["escape_requirement"] = escape
        event["escape_inlined_events"] = sorted(inlined)
        for conn in logic["CONNECTIONS"]:
            if tuple(conn["to"]) == node:
                conn["requirement"] = {"and": [conn["requirement"], escape]}
                conn["escape_gate"] = x


HEADER = "# Generated by apworld/tools/convert_db.py from the Corruptovania prime3 database. Do not edit.\n"


def write(out_dir: Path, files: dict[str, dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for fname, variables in files.items():
        text = HEADER
        for name, value in variables.items():
            text += f"\n{name} = {pprint.pformat(value, width=120, sort_dicts=False)}\n"
        (out_dir / fname).write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    write(args.out, Converter().run())


if __name__ == "__main__":
    main()
