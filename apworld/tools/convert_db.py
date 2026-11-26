"""Convert the Corruptovania (Randovania) prime3 logic into standalone Python data for the APWorld.

Usage (from the repo root):
    venv/Scripts/python.exe apworld/tools/convert_db.py [--out apworld/metroidprime3/data]

The logic is loaded through Randovania's own loader (filtered_database / pool_creator / bootstrap),
never by parsing the JSON ourselves. The output is declarative and imports nothing.

Output files (see apworld/metroidprime3/data/README.md for the format):
    logic.py      REGIONS, CONNECTIONS, EVENTS, TEMPLATES, NODE_TYPES
    locations.py  LOCATIONS (99, id = pickup index 1-99, escape_requirement E22), UNPATCHED_LOCATION (index 0, E13)
    items.py      ITEMS (AP pool, 99 items incl. Hypermode, one Missile Expansion less, E17), STARTING_ITEMS
    game.py       VICTORY_REQUIREMENT, START_LOCATION, SETTINGS, TRICKS, requirement kind statistics
    tricks.py     TRICK_REPORT (uses per level, rooms, locations/events reachable earlier), USABLE_TRICKS (E23)

Dangerous events (E18): every event that occurs negated ("before <event>") gets an escape_requirement (way from its
event node back to a ship in the state "after X", see EscapeSolver); it is ANDed onto every connection into the event
node. "before <event>" itself stays in the data and counts as satisfied in the logic.

Dead-end locations (E22): every pickup node gets an escape_requirement too (way back to a ship in the state after the
pickup and after the events every way there triggers, see attach_location_escapes). It is stored in LOCATIONS and is
the location's own access rule; ``{"and": []}`` where every state that reaches the node already satisfies it.

Independent of the setup (E23, T30): no escape requirement assumes starting items (they are normal item leaves), every
escape is computed without tricks, and "trivial" means trivial for every starting inventory and every trick setting
up to TRICK_COVERAGE. Trick leaves stay in the normal requirement trees; the APWorld evaluates them per slot.

The output is deterministic (no set iteration, no timestamps).
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import pprint
from pathlib import Path
from types import SimpleNamespace

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
# Highest Corruptovania trick level (5 = hypermode). The location rules (E22) stay safe for every trick setting up to
# this level for every trick (TRICK_COVERAGE in attach_location_escapes), so the APWorld may enable any of them.
MAX_TRICK_LEVEL = max(level.as_number for level in LayoutTrickLevel)

# Trick recommendation for the APWorld options (E23, T31). A trick is offered up to the highest level <= USABLE_MAX_LEVEL
# at which it is asked for by at least MIN_TRICK_USES requirements and makes at least one location reachable earlier,
# provided it never shares an AND term with an unsupported requirement kind ("no item", node; "before <event>" is
# handled by E18) and is not excluded below. The playthrough simulator checks the result
# (apworld/tools/playthrough_sim.py --matrix, data/README.md "Tricks").
USABLE_MAX_LEVEL = 3  # E23: global trick level "off ... advanced"
MIN_TRICK_USES = 3
EXCLUDED_TRICKS = {
    "Single Room Out of Bounds": "leaves the level geometry; the dangerous event Gel Processing Site Out of Bounds "
                                 "(E18) exists only through it (with Bomb Jump), and the logic models out of bounds "
                                 "only for single rooms",
    "Fall Respawn Skip": "relies on the respawn position after a fall, which the logic does not model",
    "Hazards without Hazard Shield": "walks through Phazon/hazards on damage requirements; the AP damage rule checks "
                                     "every requirement with full energy (no damage adds up), too optimistic for "
                                     "hazard routes",
}


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
        reentry = attach_reentry_requirements(files)
        attach_location_escapes(files, reentry)
        mark_after_goal_locations(files)
        files["tricks.py"] = trick_report(files)
        return files


# ---------------------------------------------------------------- escape requirements (E18)
# A requirement in disjunctive normal form: a list of terms (OR), each term a dict {(type, name): amount} (AND).
# TRUE = [{}], FALSE = []. Terms are kept minimal: a term that needs at least everything another term needs is dropped.
TRUE: list = [{}]
FALSE: list = []


def _implies(stronger: dict, weaker: dict) -> bool:
    """True if every inventory that satisfies ``stronger`` also satisfies ``weaker``."""
    if not weaker.keys() <= stronger.keys():
        return False
    for key, amount in weaker.items():
        if stronger[key] < amount:
            return False
    return True


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
    if a == TRUE:
        return b
    if b == TRUE:
        return a
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
    """escape_requirement of a node: when a ship is reachable from it (E18 for dangerous events, E22 for pickups).

    State: the events in ``triggered`` have happened ("before X" false), those in ``assumed`` (default: the same set)
    count as reached (event X true), the player stands at the node and owns only what he had when entering it. The
    requirement says when a ship (teleporter_network node whose ``is_unlocked`` holds) is reachable from there. It is
    the least fixpoint of "node reachable from the start node" over DNFs, evaluated symbolically:
        item / damage         -> atom (starting items too: the data assume no starting inventory, E23)
        trick                 -> constant from ``tricks`` (default: every trick off, so escapes are computed without
                                 tricks: stricter than necessary when the APWorld enables tricks, never too loose)
        misc / version        -> constant from SETTINGS
        before Y (Y not triggered) -> satisfied (as everywhere in the logic)
        event Y               -> atom, unless Y is only reachable after the start node (with all items, the node
                                 blocked): then Y is replaced by its own requirement from there (recursively).
        "no item", node       -> not satisfied (do not occur)
    E18 uses ``triggered = assumed = {X}``. ``known`` (item amounts that count as owned) is only for analyses in the
    tests; the generated data never use it.
    """

    def __init__(self, logic: dict, settings: dict, known: dict[str, int] | None = None,
                 tricks: dict[str, int] | None = None) -> None:
        self.logic = logic
        self.settings = settings
        self.known = dict(known or {})
        self.tricks = dict(tricks or {})
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
        table = {"trick": self.tricks, "misc": self.settings["misc_resources"],
                 "version": self.settings["version_resources"]}[kind]
        have = table.get(name, 0)
        return have < amount if negate else have >= amount

    def to_dnf(self, req: dict, triggered: frozenset[str], inlined: set[str], ev_dnf: dict,
               assumed: frozenset[str] | None = None) -> list:
        assumed = triggered if assumed is None else assumed
        if "and" in req:
            acc = TRUE
            for r in req["and"]:
                acc = dnf_and(acc, self.to_dnf(r, triggered, inlined, ev_dnf, assumed))
                if not acc:
                    break
            return acc
        if "or" in req:
            return dnf_or(*(self.to_dnf(r, triggered, inlined, ev_dnf, assumed) for r in req["or"]))
        kind, name, amount, negate = req["type"], req.get("name"), req.get("amount", 1), req.get("negate", False)
        if kind == "template":
            return self.to_dnf(self.templates[name], triggered, inlined, ev_dnf, assumed)
        if kind == "event":
            if negate:
                return FALSE if name in triggered else TRUE
            if name in assumed:
                return TRUE
            if name in inlined:
                return ev_dnf.get(name, FALSE)
            return [{("event", name): 1}]
        if kind in ("item", "node"):
            if kind == "node" or negate:
                return FALSE
            if self.known.get(name, 0) >= amount:
                return TRUE
            return [{("item", name): amount}]
        if kind in ("trick", "damage") and negate:
            raise ValueError(f"negated {kind} requirement is not supported: {req}")
        if kind == "damage":
            return TRUE if amount <= 0 else [{(kind, name): amount}]
        if kind in ("trick", "misc", "version"):
            return TRUE if self.static(kind, name, amount, negate) else FALSE
        raise ValueError(f"Unknown requirement type {kind!r}")

    def solve(self, triggered: frozenset[str], node: tuple, inlined: set[str],
              assumed: frozenset[str] | None = None) -> list:
        """DNF under which a ship is reachable from ``node`` (see the class docstring)."""
        reach, ev_dnf = self.reach_dnf(node, triggered, inlined, assumed=assumed)
        return dnf_or(*(dnf_and(reach[n], self.to_dnf(unlocked, triggered, inlined, ev_dnf, assumed))
                        for n, unlocked in self.targets if n in reach))

    def reach_dnf(self, node: tuple, triggered: frozenset[str], inlined: set[str],
                  stop_at_ships: bool = True, assumed: frozenset[str] | None = None,
                  base: tuple[dict, dict] | None = None) -> tuple[dict[tuple, list], dict[str, list]]:
        """Worklist fixpoint with delta propagation: DNF per node reachable from ``node`` and per inlined event.
        With ``stop_at_ships`` nothing is propagated out of a ship node (other than ``node``): every term that
        passes a ship is implied by a term that already reached it.

        ``base`` = the result of the same call on a solver with fewer tricks: the fixpoint continues from there and
        only re-evaluates the requirements that ask for a trick (the logic is monotonic in tricks). Values that do not
        change keep their identity (``reach[n] is base[0][n]``)."""
        target_nodes = {n for n, _ in self.targets} if stop_at_ships else set()
        if base is None:
            reach: dict[tuple, list] = {node: TRUE}
            delta: dict[tuple, list] = {node: TRUE}
            ev_dnf: dict[str, list] = {}
        else:
            reach, delta, ev_dnf = dict(base[0]), {}, dict(base[1])
        sources = collections.defaultdict(list)  # node -> [(event, requirement)]
        for y in sorted(inlined):
            for s in self.logic["EVENTS"][y]["sources"]:
                sources[tuple(s["node"])].append((y, s["requirement"]))
        event_users = collections.defaultdict(list)
        connection_users = collections.defaultdict(list)
        dependencies: dict[int, tuple[str, ...]] = {}
        req_cache: dict[int, tuple[tuple[int, ...], list]] = {}
        revisions: collections.Counter = collections.Counter()

        def index_requirement(req: dict) -> tuple[str, ...]:
            key = id(req)
            if key not in dependencies:
                dependencies[key] = tuple(sorted(n for k, n, neg in requirement_atoms(req, self.templates)
                                                if k == "event" and not neg and n in inlined))
            return dependencies[key]

        for conns in self.out.values():
            for conn in conns:
                for y in index_requirement(conn["requirement"]):
                    connection_users[y].append(conn)
        for n, reqs in sources.items():
            for z, req in reqs:
                for y in index_requirement(req):
                    event_users[y].append((n, z, req))

        def req_dnf(req: dict) -> list:
            key = id(req)
            version = tuple(revisions[y] for y in dependencies[key])
            cached = req_cache.get(key)
            if cached is None or cached[0] != version:
                cached = req_cache[key] = (version, self.to_dnf(req, triggered, inlined, ev_dnf, assumed))
            return cached[1]

        queue = [node] if base is None else []
        changed_events: dict[str, None] = {}

        def add_node(to: tuple, gain: list) -> None:
            old = reach.get(to, FALSE)
            added = [t for t in gain if not any(_implies(t, o) for o in old)]
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
            revisions[y] += 1
            changed_events[y] = None

        if base is not None:
            def asks_for_trick(req: dict) -> bool:
                return any(k == "trick" for k, _, _ in requirement_atoms(req, self.templates))

            for frm, conns in self.out.items():
                if frm in reach and not (frm in target_nodes and frm != node):
                    for conn in conns:
                        if asks_for_trick(conn["requirement"]):
                            gain = dnf_and(reach[frm], req_dnf(conn["requirement"]))
                            if gain:
                                add_node(tuple(conn["to"]), gain)
            for n, reqs in sources.items():
                if n in reach:
                    for y, r in reqs:
                        if asks_for_trick(r):
                            gain = dnf_and(reach[n], req_dnf(r))
                            if gain:
                                add_event(y, gain)

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
                y, _ = changed_events.popitem()
                for conn in connection_users[y]:
                    frm = tuple(conn["from"])
                    if frm in reach and not (frm in target_nodes and frm != node):
                        gain = dnf_and(reach[frm], req_dnf(conn["requirement"]))
                        if gain:
                            add_node(tuple(conn["to"]), gain)
                for n, z, req in event_users[y]:
                    if n in reach:
                        gain = dnf_and(reach[n], req_dnf(req))
                        if gain:
                            add_event(z, gain)
        return reach, ev_dnf


_SIMULATOR = None


def _simulator_world(files: dict[str, dict], tricks: dict[str, int] | None = None):
    """playthrough_sim.World on the data generated so far (compiled at call time); ``tricks`` = trick levels."""
    global _SIMULATOR
    if _SIMULATOR is None:
        spec = importlib.util.spec_from_file_location("playthrough_sim",
                                                      Path(__file__).with_name("playthrough_sim.py"))
        _SIMULATOR = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_SIMULATOR)
    data = SimpleNamespace(**{k[:-3]: SimpleNamespace(**v) for k, v in files.items() if k != "tricks.py"})
    return _SIMULATOR.World(data, tricks=tricks)


def trick_coverage(game: dict) -> dict[str, int]:
    """The trick setting the location rules are made safe for (E23): every trick at MAX_TRICK_LEVEL."""
    return {name: MAX_TRICK_LEVEL for name in game["TRICKS"]}


def attach_escape_requirements(files: dict[str, dict]) -> None:
    """E18: compute escape_requirement for every dangerous event, store it in EVENTS and AND it onto every
    connection into the event node (marked with ``escape_gate``). Works on the generated data only."""
    logic, game = files["logic.py"], files["game.py"]
    world = _simulator_world(files)
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
        escape = dnf_to_requirement(solver.solve(frozenset({x}), node, inlined))
        event["node"] = node
        event["escape_requirement"] = escape
        event["escape_inlined_events"] = sorted(inlined)
        for conn in logic["CONNECTIONS"]:
            if tuple(conn["to"]) == node:
                conn["requirement"] = {"and": [conn["requirement"], escape]}
                conn["escape_gate"] = x


# ---------------------------------------------------------------- re-entry requirements (E24)
def gate_base(conn: dict) -> dict:
    """The database requirement of a connection, without the E18/E24 gate."""
    return conn["requirement"]["and"][0] if conn.get("escape_gate") else conn["requirement"]


def before_endpoints(logic: dict, x: str) -> list[tuple]:
    """Targets of the connections whose database requirement asks for "before <x>", sorted."""
    ends = set()
    for conn in logic["CONNECTIONS"]:
        if any(k == "event" and n == x and neg for k, n, neg in requirement_atoms(gate_base(conn), logic["TEMPLATES"])):
            ends.add(tuple(conn["to"]))
    return sorted(ends)


def attach_reentry_requirements(files: dict[str, dict]) -> dict[int, tuple[list, list[str]]]:
    """E24: the way back in after a dangerous event. The logic counts "before X" as satisfied, so it keeps using the
    connections that only exist before X. For every such connection the converter compares the cost of its target b
    before and after X (forward DNF from the start, every event inlined, the E18 gates in place):
        before(b): normal logic ("before X" satisfied), after(b): X has happened ("before X" false, X reached).
    - ``lost``: b is unreachable after X even with every item and every trick (TRICK_COVERAGE). Nothing is gated;
      the converter checks that no location node is lost after X (else it raises).
    - ``safe``: before(b) with every trick implies after(b) without tricks, so for every trick setting the way back
      in costs nothing new. Nothing is gated.
    - ``gated``: without tricks, before(b) does not imply after(b) (Vaccine re-entry, T30/T36). after(b) without
      tricks is ANDed into ``reentry_requirement``, which is added as a third part to every connection into X's node:
      the logic only triggers X once the way back to b holds (stricter than needed for a player who never wants b).
    - ``location``: like ``gated``, but b is the pickup node of a location. Then the location's own rule gets
      after(b) instead (returned, ANDed by attach_location_escapes): the logic only expects the location once it is
      reachable even after X, and X itself stays free (Flux Control Tunnel Cover, T36).
    - ``tricks_only``: without tricks the way back costs nothing new, with some trick setting it does. Not gated
      (it would make the default logic stricter for nothing); listed in ``reentry_endpoints`` and data/README.md.
    ``reentry_endpoints`` = {class: [nodes]} for the classes that are not empty, on every dangerous event that has one.
    Returns {location id: (after DNF, [events])} for the ``location`` class.
    """
    logic, game = files["logic.py"], files["game.py"]
    settings, start = game["SETTINGS"], tuple(game["START_LOCATION"])
    coverage = trick_coverage(game)
    damage = settings["damage"]
    every = set(logic["EVENTS"])
    for name, ev in logic["EVENTS"].items():
        for src in ev["sources"]:
            negated = {n for k, n, neg in requirement_atoms(src["requirement"], logic["TEMPLATES"]) if k == "event" and neg}
            if negated:
                raise ValueError(f"event {name!r}: 'before' {sorted(negated)} in an event source is not supported (E24)")
    location_nodes = {loc["id"]: (loc["region"], loc["area"], loc["node"]) for loc in files["locations.py"]["LOCATIONS"]}
    location_of = {node: lid for lid, node in location_nodes.items()}
    for_locations: dict[int, tuple[list, list[str]]] = {}
    plain = EscapeSolver(logic, settings)
    before, before_ev = plain.reach_dnf(start, frozenset(), every, stop_at_ships=False)
    before_t, _ = EscapeSolver(logic, settings, tricks=coverage).reach_dnf(
        start, frozenset(), every, stop_at_ships=False, base=(before, before_ev))
    all_inv = _simulator_world(files).all_items()
    gates = {}
    for x in sorted(name for name, ev in logic["EVENTS"].items() if "escape_requirement" in ev):
        done = frozenset({x}) | forced_escape_events(files, x)
        after_files = _after_event_files(files, x, done)
        w_after = _simulator_world(after_files)
        reached_t, _, _, _ = _simulator_world(after_files, tricks=coverage).reach(all_inv, events=done)
        lost_locations = sorted(lid for lid, n in location_nodes.items() if n not in reached_t)
        if lost_locations:
            raise ValueError(f"locations {lost_locations} are unreachable after {x!r} even with every item and trick: "
                             f"they are missable and need a decision (E24)")

        def holds_after(terms: list, b: tuple) -> bool:
            """Every inventory of ``terms`` reaches ``b`` after X without tricks, i.e. ``terms`` implies after(b)."""
            return all(b in w_after.reach(_term_inventory(t, {}, damage), events=done)[0] for t in terms)

        after = None
        classes: dict[str, list] = {"gated": [], "location": [], "tricks_only": [], "lost": []}
        reentry = TRUE
        for b in before_endpoints(logic, x):
            if b not in reached_t:
                classes["lost"].append(b)
                continue
            if holds_after(before_t.get(b, FALSE), b):
                continue
            if holds_after(before.get(b, FALSE), b):
                classes["tricks_only"].append(b)
                continue
            if after is None:  # forward DNF after X: X's own gate gone, X and the forced events reached
                stripped = dict(logic, CONNECTIONS=[dict(c, requirement=gate_base(c)) if c.get("escape_gate") == x
                                                    else c for c in logic["CONNECTIONS"]])
                after, _ = EscapeSolver(stripped, settings).reach_dnf(start, done, every - done, stop_at_ships=False,
                                                                      assumed=done)
            behind = [tuple(c["to"]) for c in plain.out.get(b, ())]
            if b in location_of and all(holds_after(before.get(t, FALSE), t) for t in behind):
                # nothing behind the pickup node gets more expensive: the location rule is enough
                classes["location"].append(b)
                lid = location_of[b]
                dnf, names = for_locations.get(lid, (TRUE, []))
                for_locations[lid] = (dnf_and(dnf, after.get(b, FALSE)), names + [x])
            else:
                classes["gated"].append(b)
                reentry = dnf_and(reentry, after.get(b, FALSE))
        if not reentry:
            raise ValueError(f"{x!r}: the way back in is impossible without tricks, so the event could never happen")
        event = logic["EVENTS"][x]
        if done != {x}:
            event["reentry_assumed_events"] = sorted(done - {x})
        if any(classes.values()):
            event["reentry_endpoints"] = {k: v for k, v in classes.items() if v}
        if reentry != TRUE:
            gates[x] = event["reentry_requirement"] = dnf_to_requirement(reentry)
    for conn in logic["CONNECTIONS"]:
        if conn.get("escape_gate") in gates:
            conn["requirement"] = {"and": conn["requirement"]["and"] + [gates[conn["escape_gate"]]]}
    return for_locations


def _substitute_events(req: dict, done: frozenset) -> dict:
    """``req`` in the state after the events ``done``: "before Y" never holds and event Y always does."""
    if "and" in req:
        return {"and": [_substitute_events(r, done) for r in req["and"]]}
    if "or" in req:
        return {"or": [_substitute_events(r, done) for r in req["or"]]}
    if req["type"] == "event" and req["name"] in done:
        return {"or": []} if req.get("negate") else {"and": []}
    return req


def _after_event_files(files: dict[str, dict], x: str, done: frozenset) -> dict[str, dict]:
    """The generated data in the state after the events ``done`` (``x`` among them), X's own gate gone (X has
    happened). For the simulator World (E24)."""
    logic = files["logic.py"]
    conns = []
    for conn in logic["CONNECTIONS"]:
        if conn.get("escape_gate") == x:
            conn = {k: v for k, v in conn.items() if k != "escape_gate"} | {"requirement": gate_base(conn)}
        conns.append(dict(conn, requirement=_substitute_events(conn["requirement"], done)))
    unlock_keys = ("is_unlocked", "requirement_to_activate")
    regions = {r: {"areas": {a: {"nodes": {n: {k: _substitute_events(v, done) if k in unlock_keys else v
                                                for k, v in info.items()}
                                            for n, info in area["nodes"].items()}}
                             for a, area in region["areas"].items()}}
               for r, region in logic["REGIONS"].items()}
    events = {name: dict(ev, sources=[dict(s, requirement=_substitute_events(s["requirement"], done))
                                      for s in ev["sources"]])
              for name, ev in logic["EVENTS"].items()}
    new_logic = dict(logic, REGIONS=regions, CONNECTIONS=conns, EVENTS=events,
                     TEMPLATES={k: _substitute_events(v, done) for k, v in logic["TEMPLATES"].items()})
    return dict(files, **{"logic.py": new_logic})


def forced_escape_events(files: dict[str, dict], x: str) -> frozenset:
    """E24: the events that every way from X's node to a ship triggers after X, even with every item and every trick
    (TRICK_COVERAGE). The player has them once he is out (e.g. both Xenoresearch Seeker Gates after the Power
    Outage), so the way back in may use them."""
    logic = files["logic.py"]
    node = tuple(logic["EVENTS"][x]["node"])
    w = _simulator_world(_after_event_files(files, x, frozenset({x})), tricks=trick_coverage(files["game.py"]))
    inv = w.all_items()
    ships = {n for n, _ in w.ships}
    local, _, _, _ = w.reach(inv, start=[node], events={x}, blocked_nodes=ships - {node})
    candidates = sorted(name for name, ev in logic["EVENTS"].items()
                        if name != x and any(tuple(s["node"]) in local for s in ev["sources"]))
    forced = set()
    for y in candidates:
        ev = logic["EVENTS"][y]
        blocked = {tuple(s["node"]) for s in ev["sources"]} if ev["kind"] == "db" else set()
        reached, evs, _, _ = w.reach(inv, start=[node], events={x}, blocked_events={y}, blocked_nodes=blocked)
        if not any(n in reached and fn(inv, evs, False) for n, fn in w.ships):
            forced.add(y)
    return frozenset(forced)


# ---------------------------------------------------------------- escape requirements of pickup nodes (E22)
def _term_inventory(term: dict, base: dict[str, int], damage: dict) -> dict[str, int]:
    """Smallest inventory (resource amounts) satisfying an item-only DNF term: ``base`` plus the term's item atoms;
    damage atoms become Energy Tanks with the same formula as the logic (data README, SETTINGS["damage"])."""
    inv = dict(base)
    tanks = 0
    for (kind, name), amount in term.items():
        if kind == "item":
            inv[name] = max(inv.get(name, 0), amount)
        elif kind == "damage":
            if damage["reductions"].get(name):
                raise ValueError(f"damage reductions for {name!r} are not supported by the E22 triviality check")
            needed = int(amount * damage["strictness"])
            tanks = max(tanks, (needed - damage["starting_energy"]) // damage["energy_per_tank"] + 1)
        else:
            raise ValueError(f"unexpected atom {kind!r} {name!r} in an item-only entry term")
    if tanks > 0:
        inv["Energy Tank"] = max(inv.get("Energy Tank", 0), tanks)
    return inv


def attach_location_escapes(files: dict[str, dict], reentry: dict[int, tuple[list, list[str]]] | None = None
                            ) -> list[int]:
    """E22: escape_requirement of every pickup node (location 1-99), stored in LOCATIONS. Returns the ids of the
    locations whose escape_requirement is not trivially satisfied.

    Same solver as E18, state "after the pickup and after all events on the way there": starting at the pickup node,
    with events that are only reachable through the pickup node inlined (``escape_inlined_events``, cycle-free).
    Connections already carry the E18 gates. Independent of the setup (E23):
    - No starting items are assumed: they are item leaves like every other item.
    - The way out is computed without tricks.
    - ``escape_triggered_events``: events that every way to the node without tricks triggers (the node is unreachable
      with all items when the event, and for a database event its node, is blocked): "before Y" is false.
      ``escape_assumed_events``: the part that every way even with TRICK_COVERAGE triggers: Y counts as reached. The
      other triggered events stay event leaves (a trick may skip them on the way in).

    The requirement counts as trivially satisfied (stored as ``{"and": []}``) when every state that reaches the
    pickup node satisfies it, for every starting inventory and every trick setting up to TRICK_COVERAGE: for every
    minimal item set that reaches the node with TRICK_COVERAGE (forward DNF from the start, all events inlined, no
    starting items), the requirement holds with the events that set reaches without tricks. The logic is monotonic in
    items, tricks and events ("before X" satisfied), so checking these sets is enough.
    """
    logic, game = files["logic.py"], files["game.py"]
    locations = files["locations.py"]["LOCATIONS"]
    coverage = trick_coverage(game)
    world = _simulator_world(files)  # compiled now: the E18 gates are part of the connections
    world_t = _simulator_world(files, tricks=coverage)
    all_inv = world.all_items()
    reached, all_events, _, _ = world.reach(all_inv)
    damage = game["SETTINGS"]["damage"]
    solver = EscapeSolver(logic, game["SETTINGS"])
    nodes = {loc["id"]: (loc["region"], loc["area"], loc["node"]) for loc in locations}
    unreachable = sorted(lid for lid, node in nodes.items() if node not in reached)
    if unreachable:
        raise ValueError(f"locations unreachable with all items: {unreachable}")

    triggered: dict[int, set[str]] = {lid: set() for lid in nodes}
    assumed: dict[int, set[str]] = {lid: set() for lid in nodes}
    for y in sorted(all_events):
        event = logic["EVENTS"][y]
        event_nodes = {tuple(s["node"]) for s in event["sources"]} if event["kind"] == "db" else set()
        without_y, _, _, _ = world.reach(all_inv, blocked_nodes=event_nodes, blocked_events={y})
        without_y_t, _, _, _ = world_t.reach(all_inv, blocked_nodes=event_nodes, blocked_events={y})
        for lid, node in nodes.items():
            if node not in without_y:
                triggered[lid].add(y)
                if node not in without_y_t:
                    assumed[lid].add(y)

    # minimal item sets per node with every trick enabled (forward from the start, every event inlined)
    entry_solver = EscapeSolver(logic, game["SETTINGS"], tricks=coverage)
    entry, _ = entry_solver.reach_dnf(tuple(game["START_LOCATION"]), frozenset(), set(logic["EVENTS"]),
                                      stop_at_ships=False)

    def implied_by_entry(node: tuple, dnf: list) -> bool:
        rule, _ = world.compile(dnf_to_requirement(dnf))
        terms = entry.get(node, FALSE)
        if not terms:
            raise ValueError(f"entry DNF of {node} is empty, but the node is reachable")
        for term in terms:
            inv = _term_inventory(term, {}, damage)
            term_reached, _, _, _ = world_t.reach(inv)
            if node not in term_reached:
                raise ValueError(f"entry term {term} does not reach {node} in the simulator")
            _, term_events, _, _ = world.reach(inv)  # events without tricks: the fewest any setting reaches
            if not rule(inv, term_events, False):
                return False
        return True

    nontrivial = []
    for loc in locations:
        lid, node = loc["id"], nodes[loc["id"]]
        _, without_p, _, _ = world.reach(all_inv, blocked_nodes={node})
        inlined = {y for y in all_events if y not in without_p}
        if inlined & triggered[lid]:
            raise ValueError(f"location {lid}: events both triggered on the way and only reachable after it: "
                             f"{sorted(inlined & triggered[lid])}")
        dnf = solver.solve(frozenset(triggered[lid]), node, inlined, assumed=frozenset(assumed[lid]))
        if lid in (reentry or {}):  # E24: the way to the pickup node after a dangerous event
            dnf = dnf_and(dnf, reentry[lid][0])
        if not dnf:
            raise ValueError(f"location {lid} {loc['name']!r}: no way back to a ship even with all items")
        if dnf == TRUE or implied_by_entry(node, dnf):
            loc["escape_requirement"] = {"and": []}
            continue
        nontrivial.append(lid)
        loc["escape_requirement"] = dnf_to_requirement(dnf)
        loc["escape_triggered_events"] = sorted(triggered[lid])
        loc["escape_assumed_events"] = sorted(assumed[lid])
        loc["escape_inlined_events"] = sorted(inlined)
        if lid in (reentry or {}):
            loc["reentry_events"] = sorted(reentry[lid][1])
    return nontrivial


def mark_after_goal_locations(files: dict[str, dict]) -> list[int]:
    """E24 (T36): ``"missable": "after_goal"`` on every location the logic reaches only after the goal event, even
    with every item and every trick (TRICK_COVERAGE). The database lets the player into G.F.S. Olympus from the
    gunship only after Aurora Unit 313 (start Valhalla), while the game lets him in once before (Olympus intro) and
    never again once he leaves. The APWorld should place only filler there (excluded locations). Returns the ids."""
    victory = files["game.py"]["VICTORY_REQUIREMENT"]
    if victory.get("type") != "event" or victory.get("negate"):
        raise ValueError(f"the victory requirement must be a single event: {victory}")
    world_t = _simulator_world(files, tricks=trick_coverage(files["game.py"]))
    reached, _, _, _ = world_t.reach(world_t.all_items(), blocked_events={victory["name"]})
    marked = []
    for loc in files["locations.py"]["LOCATIONS"]:
        if (loc["region"], loc["area"], loc["node"]) not in reached:
            loc["missable"] = "after_goal"
            marked.append(loc["id"])
    return marked


# ---------------------------------------------------------------- trick report (E23)
def _symbolic_terms(req: dict, templates: dict) -> list[frozenset]:
    """Requirement as an OR of AND terms over its leaves (type, name, amount, negate), templates expanded."""
    if "and" in req:
        acc = [frozenset()]
        for r in req["and"]:
            sub = _symbolic_terms(r, templates)
            acc = sorted({a | b for a in acc for b in sub}, key=sorted)
        return acc
    if "or" in req:
        return sorted({t for r in req["or"] for t in _symbolic_terms(r, templates)}, key=sorted)
    if req["type"] == "template":
        return _symbolic_terms(templates[req["name"]], templates)
    return [frozenset({(req["type"], req.get("name", ""), req.get("amount", 1), bool(req.get("negate", False)))})]


def _requirement_trees(logic: dict, victory: dict) -> list[tuple[str, tuple | None, dict]]:
    """Every requirement tree of the data that may hold a trick: (kind, node it starts at, tree). Connections without
    their E18 gate (the gates are computed without tricks), templates only where they are used."""
    trees = []
    for conn in logic["CONNECTIONS"]:
        req = conn["requirement"]["and"][0] if conn.get("escape_gate") else conn["requirement"]
        trees.append(("connection", tuple(conn["from"]), req))
    for event in logic["EVENTS"].values():
        trees += [("event source", tuple(src["node"]), src["requirement"]) for src in event["sources"]]
    for rname, info_region in logic["REGIONS"].items():
        for aname, area in info_region["areas"].items():
            for nname, node in area["nodes"].items():
                trees += [("teleporter", (rname, aname, nname), node[k])
                          for k in ("is_unlocked", "requirement_to_activate") if k in node]
    trees.append(("victory", None, victory))
    return trees


def _leaf_counts(req: dict, out: collections.Counter) -> None:
    if "and" in req or "or" in req:
        for r in req.get("and", []) + req.get("or", []):
            _leaf_counts(r, out)
    elif req["type"] == "trick":
        out[(req["name"], req["amount"])] += 1


class _AccessAnalysis:
    """Minimal item sets (DNF, all events inlined, no starting items) of every location's AP access (node reachable
    and escape_requirement) and of every event, per trick setting. Trick settings are evaluated incrementally on top
    of the result without tricks."""

    def __init__(self, logic: dict, game: dict, locations: list[dict]) -> None:
        self.logic, self.game = logic, game
        self.events = set(logic["EVENTS"])
        self.locations = [(loc["id"], (loc["region"], loc["area"], loc["node"]), loc["escape_requirement"],
                           sorted({n for k, n, _ in requirement_atoms(loc["escape_requirement"], logic["TEMPLATES"])
                                   if k == "event"}))
                          for loc in locations]
        self.base = self._run({}, None)

    def _run(self, tricks: dict[str, int], base) -> tuple[dict, dict, dict, dict]:
        solver = EscapeSolver(self.logic, self.game["SETTINGS"], tricks=tricks)
        entry, ev_dnf = solver.reach_dnf(tuple(self.game["START_LOCATION"]), frozenset(), self.events,
                                         stop_at_ships=False, base=None if base is None else base[:2])
        rules, access = {}, {}
        for lid, node, requirement, rule_events in self.locations:
            if base is not None and all(ev_dnf.get(e) is base[1].get(e) for e in rule_events):
                rules[lid] = base[2][lid]
            else:
                rules[lid] = solver.to_dnf(requirement, frozenset(), self.events, ev_dnf)
            if base is not None and rules[lid] is base[2][lid] and entry.get(node) is base[0].get(node):
                access[lid] = base[3][lid]
            else:
                access[lid] = dnf_and(entry.get(node, FALSE), rules[lid])
        return entry, ev_dnf, rules, access

    def gains(self, tricks: dict[str, int], db_events: list[str]) -> tuple[list[int], list[str], list[str]]:
        """Locations and database events reachable with fewer items than without tricks, and database events
        reachable only with these tricks."""
        _, ev_dnf, _, access = self._run(tricks, self.base)
        base_events = self.base[1]
        events = {k: v for k, v in ev_dnf.items() if k in db_events and v is not base_events.get(k)}
        return (_gains(self.base[3], {k: v for k, v in access.items() if v is not self.base[3][k]}),
                _gains(base_events, events),
                sorted(k for k, v in events.items() if v and not base_events.get(k)))


def _gains(base: dict, more: dict) -> list:
    """Keys whose DNF in ``more`` has a term that no term of ``base`` implies (reachable with fewer items)."""
    return sorted(k for k, terms in more.items()
                  if any(not any(_implies(t, b) for b in base.get(k, FALSE)) for t in terms))


def trick_report(files: dict[str, dict]) -> dict:
    """tricks.py (E23, T30): how every trick is used and what it changes, plus the recommendation USABLE_TRICKS.

    Per trick: ``uses`` = trick leaves in the database per level (templates counted once), ``requirements`` =
    connections/event sources whose requirement asks for the trick at that level (templates expanded), ``rooms`` where
    they start, ``with_before``/``with_damage``/``with_unsupported`` = AND terms that combine the trick with "before
    <event>", a damage requirement or an unsupported kind ("no item", node). Per level L (the trick alone at L, all
    others off): ``earlier_locations`` (AP location access, i.e. node and escape_requirement, possible with fewer items
    than without the trick), ``earlier_events`` (database events, likewise) and ``new_events`` (database events
    reachable only with the trick, even with every item). ``usable_level`` is the recommendation (0 = not offered,
    criteria at USABLE_MAX_LEVEL), ``reason`` explains it.
    """
    logic, game = files["logic.py"], files["game.py"]
    locations = files["locations.py"]["LOCATIONS"]
    templates = logic["TEMPLATES"]
    trees = _requirement_trees(logic, game["VICTORY_REQUIREMENT"])
    leaf_uses: collections.Counter = collections.Counter()
    for tree in [t for _, _, t in trees] + list(templates.values()):
        _leaf_counts(tree, leaf_uses)

    requirements: collections.Counter = collections.Counter()
    rooms: dict[str, set[str]] = collections.defaultdict(set)
    combined: collections.Counter = collections.Counter()
    for _, node, tree in trees:
        terms = _symbolic_terms(tree, templates)
        seen = set()
        for term in terms:
            for kind, name, amount, _ in term:
                if kind != "trick":
                    continue
                seen.add((name, amount))
                others = {(k, neg) for k, _, _, neg in term}
                if ("event", True) in others:
                    combined[(name, "before")] += 1
                if ("damage", False) in others:
                    combined[(name, "damage")] += 1
                if ("item", True) in others or any(k == "node" for k, _ in others):
                    combined[(name, "unsupported")] += 1
        for name, amount in seen:
            requirements[(name, amount)] += 1
            if node is not None:
                rooms[name].add(f"{node[0]} - {node[1]}")

    db_events = sorted(name for name, ev in logic["EVENTS"].items() if ev["kind"] == "db")
    analysis = _AccessAnalysis(logic, game, locations)
    report = {}
    for trick in game["TRICKS"]:
        levels = sorted({lv for (name, lv) in set(leaf_uses) | set(requirements) if name == trick})
        entry = {
            "short_name": game["TRICKS"][trick]["short_name"],
            "uses": {lv: leaf_uses[(trick, lv)] for lv in levels},
            "requirements": {lv: requirements[(trick, lv)] for lv in levels},
            "rooms": sorted(rooms[trick]),
            "with_before": combined[(trick, "before")],
            "with_damage": combined[(trick, "damage")],
            "with_unsupported": combined[(trick, "unsupported")],
            "earlier_locations": {},
            "earlier_events": {},
            "new_events": {},
        }
        for lv in levels:
            locs, evs, new = analysis.gains({trick: lv}, db_events)
            entry["earlier_locations"][lv], entry["earlier_events"][lv], entry["new_events"][lv] = locs, evs, new
        entry["usable_level"], entry["reason"] = _usable_level(trick, entry)
        report[trick] = entry
    usable = {trick: r["usable_level"] for trick, r in report.items() if r["usable_level"] > 0}
    combined = {}
    for label, tricks in (("usable", usable), ("coverage", trick_coverage(game))):
        locs, evs, new = analysis.gains(tricks, db_events)
        combined[label] = {"tricks": tricks, "earlier_locations": locs, "earlier_events": evs, "new_events": new}
    return {
        "TRICK_COVERAGE": trick_coverage(game),
        "USABLE_MAX_LEVEL": USABLE_MAX_LEVEL,
        "USABLE_TRICKS": usable,
        "TRICK_REPORT": report,
        "COMBINED_REPORT": combined,
    }


def _usable_level(trick: str, entry: dict) -> tuple[int, str]:
    """Recommended highest level for the APWorld options (0 = not offered) and why."""
    if trick in EXCLUDED_TRICKS:
        return 0, f"excluded: {EXCLUDED_TRICKS[trick]}"
    if entry["with_unsupported"]:
        return 0, "combined with an unsupported requirement kind"
    best, why = 0, f"fewer than {MIN_TRICK_USES} requirements at levels 1-{USABLE_MAX_LEVEL}"
    for lv in sorted(level for level in entry["requirements"] if level <= USABLE_MAX_LEVEL):
        count = sum(n for level, n in entry["requirements"].items() if level <= lv)
        if count < MIN_TRICK_USES:
            continue
        if not any(entry["earlier_locations"].get(level) for level in entry["earlier_locations"] if level <= lv):
            why = f"makes no location reachable earlier at levels 1-{lv}"
            continue
        best = lv
    if best:
        count = sum(n for level, n in entry["requirements"].items() if level <= best)
        why = f"{count} requirements at levels 1-{best}, makes locations reachable earlier"
    return best, why


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
