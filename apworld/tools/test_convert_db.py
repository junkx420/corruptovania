"""Acceptance tests for apworld/tools/convert_db.py (T03, T20, T25) and apworld/tools/playthrough_sim.py.

Run from the repo root:
    venv/Scripts/python.exe -m pytest apworld/tools/test_convert_db.py -s

The generated data is produced once per session by running the converter as a subprocess.
Randovania is only used here as the reference ("Corruptovania loader"), never by the generated files.
"""

from __future__ import annotations

import ast
import collections
import importlib.util
import os
import random
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = Path(__file__).resolve().parent
CONVERTER = TOOLS_DIR / "convert_db.py"
COMMITTED_DATA = REPO_ROOT / "apworld" / "metroidprime3" / "data"
GENERATED_FILES = ("game.py", "items.py", "locations.py", "logic.py")

# Every requirement "type" value the generated data may contain. A new one must fail the tests.
KNOWN_REQUIREMENT_TYPES = frozenset(
    {"template", "item", "event", "trick", "damage", "misc", "version", "node"}
)
EXPECTED_LOCATION_0_ITEM = "Hypermode"
DROPPED_FROM_POOL = "Missile Expansion"
GOAL_EVENT = "Aurora Unit 313"


def _load_simulator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("playthrough_sim", TOOLS_DIR / "playthrough_sim.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("playthrough_sim", module)
    spec.loader.exec_module(module)
    return module


playthrough_sim = _load_simulator()


# ---------------------------------------------------------------- helpers
def _run_converter(out_dir: Path, hash_seed: str) -> None:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    subprocess.run(
        [sys.executable, str(CONVERTER), "--out", str(out_dir)],
        cwd=REPO_ROOT, env=env, check=True, timeout=600,
    )


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_gen_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Data:
    """The generated modules, loaded from a directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.logic = _load(directory / "logic.py")
        self.game = _load(directory / "game.py")
        self.items = _load(directory / "items.py")
        self.locations = _load(directory / "locations.py")


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def out_a(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("convert_a")
    _run_converter(path, "1")
    return path


@pytest.fixture(scope="session")
def out_b(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("convert_b")
    _run_converter(path, "12345")
    return path


@pytest.fixture(scope="session")
def data(out_a) -> Data:
    return Data(out_a)


@pytest.fixture(scope="session")
def converter():
    sys.path.insert(0, str(TOOLS_DIR))
    try:
        import convert_db
    finally:
        sys.path.remove(str(TOOLS_DIR))
    return convert_db.Converter()


# ---------------------------------------------------------------- 1. reproducibility
def test_output_is_byte_identical_for_different_hash_seeds(out_a, out_b):
    assert sorted(p.name for p in out_a.iterdir()) == sorted(GENERATED_FILES)
    assert sorted(p.name for p in out_b.iterdir()) == sorted(GENERATED_FILES)
    for name in GENERATED_FILES:
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes(), f"{name} differs between hash seeds"


def test_committed_data_is_up_to_date(out_a):
    for name in GENERATED_FILES:
        committed = COMMITTED_DATA / name
        assert committed.exists(), f"{committed} missing: run the generation command from data/README.md"
        # git may check the files out with CRLF (core.autocrlf); only the content has to match
        assert committed.read_bytes().replace(b"\r\n", b"\n") == (out_a / name).read_bytes(), (
            f"{name} is stale: regenerate it"
        )


# ---------------------------------------------------------------- 2. locations
def test_exactly_99_locations_with_ids_1_to_99(data):
    locations = data.locations.LOCATIONS
    assert len(locations) == 99
    assert [loc["id"] for loc in locations] == list(range(1, 100))
    assert len({loc["name"] for loc in locations}) == 99
    for loc in locations:
        assert loc["name"] == f"{loc['region']} - {loc['area']} - {loc['node']}"
    assert data.locations.UNPATCHED_LOCATION["id"] == 0
    assert data.locations.UNPATCHED_LOCATION["vanilla_item"] == EXPECTED_LOCATION_0_ITEM


def test_location_id_is_pickup_index_in_corruptovania_loader(data, converter):
    from randovania.game_description.resources.pickup_index import PickupIndex

    region_list = converter.game.region_list
    for loc in data.locations.LOCATIONS:
        node = region_list.node_from_pickup_index(PickupIndex(loc["id"]))
        assert node.pickup_index.index == loc["id"]
        assert region_list.nodes_to_region(node).name == loc["region"]
        assert region_list.nodes_to_area(node).name == loc["area"]
        assert node.name == loc["node"]
        assert node.location_category.value == loc["category"]
        # the location node exists in the converted logic graph with the same index
        info = data.logic.REGIONS[loc["region"]]["areas"][loc["area"]]["nodes"][loc["node"]]
        assert info["type"] == "pickup"
        assert info["pickup_index"] == loc["id"]

    node0 = region_list.node_from_pickup_index(PickupIndex(0))
    unpatched = data.locations.UNPATCHED_LOCATION
    assert (region_list.nodes_to_region(node0).name, region_list.nodes_to_area(node0).name, node0.name) == (
        unpatched["region"], unpatched["area"], unpatched["node"])


# ---------------------------------------------------------------- 3. items
def test_exactly_99_items_standard_pool_minus_one_missile_expansion(data, converter):
    """E17 (revised): Hypermode (vanilla item of the unpatched location 0) is in the AP pool,
    one Missile Expansion less, 99 items = 99 locations."""
    from randovania.game_description import default_database
    from randovania.generator.pickup_pool import pool_creator

    pool = pool_creator.calculate_pool_results(converter.config, converter.game)
    standard = collections.Counter(p.name for p in pool.to_place)
    assert sum(standard.values()) == 100, "the standard pool is expected to have 100 items"

    db = default_database.pickup_database_for_game(converter.preset.game)
    at_zero = [n for n, d in db.standard_pickups.items() if any(i.index == 0 for i in d.original_locations)]
    assert at_zero == [EXPECTED_LOCATION_0_ITEM]

    expected = standard.copy()
    expected[DROPPED_FROM_POOL] -= 1

    actual = collections.Counter()
    for item in data.items.ITEMS:
        assert item["name"] not in actual, "ITEMS must list each name once, with a count"
        actual[item["name"]] += item["count"]

    assert sum(actual.values()) == 99 == len(data.locations.LOCATIONS)
    assert actual == +expected
    assert actual[EXPECTED_LOCATION_0_ITEM] == 1
    assert actual[DROPPED_FROM_POOL] == standard[DROPPED_FROM_POOL] - 1
    assert not hasattr(data.items, "LOCATION_0_ITEM"), "location 0 is no part of the AP logic"


def test_item_records_are_complete(data):
    for item in data.items.ITEMS + data.items.STARTING_ITEMS:
        assert set(item) == {"name", "category", "location_category", "count", "progression", "progressive",
                             "is_expansion", "unlocks_lock", "lock", "stages"}
        assert item["count"] >= 1
        assert item["stages"], item["name"]
    by_name = {i["name"]: i for i in data.items.ITEMS}
    assert by_name["Progressive Beam"]["stages"] == [[("Plasma Beam", 1)], [("Nova Beam", 1)]]
    assert by_name["Progressive Missile"]["stages"] == [[("Ice Missile", 1)], [("Seeker Missile", 1)]]
    assert by_name["Missile Expansion"]["lock"]["opened_by"] == "Missile Launcher"
    assert by_name["Ship Missile Expansion"]["lock"]["opened_by"] == "Ship Missile"
    assert by_name["Missile Launcher"]["unlocks_lock"] is True
    assert sorted(i["name"] for i in data.items.STARTING_ITEMS) == sorted(
        ["Charge Beam", "Power Beam", "Combat Visor", "Scan Visor", "Space Jump Boots", "Morph Ball",
         "Morph Ball Bombs"])


def test_start_and_settings(data):
    assert data.game.START_LOCATION == ("G.F.S. Valhalla", "Docking Bay 5", "Samus Ship")
    settings = data.game.SETTINGS
    assert settings["starting_location"] == data.game.START_LOCATION
    assert settings["trick_level"]["minimal_logic"] is False
    assert set(settings["trick_level"]["levels"].values()) == {0}
    assert set(settings["trick_level"]["levels"]) == set(data.game.TRICKS)
    assert settings["damage"]["strictness"] == 1.5


# ---------------------------------------------------------------- 4. unknown requirement types
def _walk_requirement_types(req: dict, found: set[str]) -> None:
    if "and" in req or "or" in req:
        for sub in req.get("and", []) + req.get("or", []):
            _walk_requirement_types(sub, found)
    else:
        found.add(req["type"])


def test_no_unknown_requirement_type_in_generated_data(data):
    found: set[str] = set()
    logic = data.logic
    for conn in logic.CONNECTIONS:
        _walk_requirement_types(conn["requirement"], found)
    for tpl in logic.TEMPLATES.values():
        _walk_requirement_types(tpl, found)
    for event in logic.EVENTS.values():
        for src in event["sources"]:
            _walk_requirement_types(src["requirement"], found)
    _walk_requirement_types(data.game.VICTORY_REQUIREMENT, found)
    for region in logic.REGIONS.values():
        for area in region["areas"].values():
            for node in area["nodes"].values():
                for key in ("is_unlocked", "requirement_to_activate"):
                    if key in node:
                        _walk_requirement_types(node[key], found)
    assert found <= KNOWN_REQUIREMENT_TYPES, f"unknown requirement types: {sorted(found - KNOWN_REQUIREMENT_TYPES)}"

    import_kinds = set(data.game.REQUIREMENT_KINDS)
    known_kinds = set(data.game.UNSUPPORTED_KINDS) | {
        "and", "or", "template", "item", "event", "trick", "damage", "misc", "misc_negated", "version"}
    assert import_kinds <= known_kinds, f"unknown requirement kinds: {sorted(import_kinds - known_kinds)}"
    # the only unsupported kind that actually occurs is "before event"
    occurring = {k for k, v in data.game.UNSUPPORTED_KINDS.items() if v["count"] > 0}
    assert occurring == {"event_negated"}
    assert data.game.UNSUPPORTED_KINDS["event_negated"]["count"] == 54


def test_converter_rejects_unknown_requirement_types(converter):
    class Mystery:
        pass

    with pytest.raises(ValueError, match="Unknown requirement type"):
        converter.req(Mystery())

    converter.kind_counts["mystery_kind"] += 1
    try:
        with pytest.raises(ValueError, match="Unknown requirement kinds"):
            converter.check_kinds()
    finally:
        del converter.kind_counts["mystery_kind"]


# ---------------------------------------------------------------- 5. dangerous events, escape gates (E18)
def _negated_events(req: dict, out: set[str]) -> None:
    if "and" in req or "or" in req:
        for sub in req.get("and", []) + req.get("or", []):
            _negated_events(sub, out)
    elif req["type"] == "event" and req.get("negate"):
        out.add(req["name"])


def _events_occurring_negated(data: Data) -> set[str]:
    """Events that occur negated anywhere, searched independently of the converter (gates stripped)."""
    logic = data.logic
    found: set[str] = set()
    for conn in logic.CONNECTIONS:
        _negated_events(conn["requirement"]["and"][0] if conn.get("escape_gate") else conn["requirement"], found)
    for tpl in logic.TEMPLATES.values():
        _negated_events(tpl, found)
    for event in logic.EVENTS.values():
        for src in event["sources"]:
            _negated_events(src["requirement"], found)
    _negated_events(data.game.VICTORY_REQUIREMENT, found)
    for region in logic.REGIONS.values():
        for area in region["areas"].values():
            for node in area["nodes"].values():
                for key in ("is_unlocked", "requirement_to_activate"):
                    if key in node:
                        _negated_events(node[key], found)
    return found


@pytest.fixture(scope="session")
def world(data):
    return playthrough_sim.World(data)


def test_every_dangerous_event_has_an_escape_requirement_and_gates_its_node(data):
    events = data.logic.EVENTS
    dangerous = _events_occurring_negated(data)
    assert len(dangerous) == 22
    assert {name for name, ev in events.items() if "escape_requirement" in ev} == dangerous
    node_of = {}
    for name in dangerous:
        ev = events[name]
        assert ev["kind"] == "db"
        assert [tuple(s["node"]) for s in ev["sources"]] == [tuple(ev["node"])]
        node_of[tuple(ev["node"])] = name
    gated = collections.Counter()
    for conn in data.logic.CONNECTIONS:
        into = node_of.get(tuple(conn["to"]))
        assert conn.get("escape_gate") == into, conn
        if into is not None:
            req = conn["requirement"]
            assert set(req) == {"and"} and len(req["and"]) == 2
            assert req["and"][1] == events[into]["escape_requirement"]
            gated[into] += 1
    assert set(gated) == dangerous, "every dangerous event node must have at least one gated connection"


def _event_atoms(req: dict, out: set[str]) -> set[str]:
    if "and" in req or "or" in req:
        for sub in req.get("and", []) + req.get("or", []):
            _event_atoms(sub, out)
    else:
        assert req["type"] in ("item", "event", "damage"), req  # tricks/misc/version are folded into constants
        if req["type"] == "event":
            assert not req.get("negate"), req
            out.add(req["name"])
    return out


def test_escape_requirements_are_cycle_free(world, data):
    """No escape_requirement contains its own event or an event that is only reachable after it
    (all items, no tricks; with all escape gates and without)."""
    full = world.all_items()
    for gated in (True, False):
        _, all_events, _, _ = world.reach(full, gated=gated)
        for name, node in sorted(world.dangerous.items()):
            atoms = _event_atoms(data.logic.EVENTS[name]["escape_requirement"], set())
            assert name not in atoms
            _, without, _, _ = world.reach(full, gated=gated, blocked_nodes={node}, blocked_events={name})
            only_after = {y for y in atoms if y in all_events and y not in without}
            assert not only_after, f"{name}: escape requirement uses events only reachable after it: {only_after}"
    # the cases named in F-02 really had to be inlined
    inlined = {n: data.logic.EVENTS[n]["escape_inlined_events"] for n in world.dangerous}
    assert "Proving Grounds Barrier Removed" in inlined["Gandrayda"]
    assert inlined["Turbine Chamber Bomb Part 1"]
    assert inlined["Ready Room Briefing"]


# Control values (no tricks): the item that is missing after the trigger when the node was entered with minimal items.
TRAPS = {
    "Gateway Green Lock": "Grapple Lasso",
    "Imperial Crypt Ice Floor": "Screw Attack",
    "Xenoresearch Power Outage": "Seeker Missile",
    "Gandrayda": "Grapple Voltage",
}
NO_TRAP = ("Aurora Chamber (Elysia) Vaccine", "Spire Bomb Leviathan Shield")
GREEDY_ORDERS = 12


def _entry_state(world, event: str, inv: dict) -> tuple[bool, set]:
    """Can the event node be entered with ``inv`` (before triggering it), and which events are reached by then."""
    node = world.dangerous[event]
    reached, events, _, _ = world.reach(inv, gated=False, blocked_nodes={node}, blocked_events={event})
    enter = any(c[0] in reached and c[1] == node and c[4](inv, events, False) for c in world.conns)
    return enter, events


def _minimal_entry_inventories(world, event: str) -> list[dict]:
    """Starting items + a minimal part of the pool (greedy removal of single copies in fixed shuffled orders)."""
    start = list(world.data.items.STARTING_ITEMS)
    pool = sorted(world.pool(), key=lambda r: r["name"])
    found = []
    for seed in range(GREEDY_ORDERS):
        order = list(range(len(pool)))
        random.Random(seed).shuffle(order)
        keep = set(order)
        for i in order:
            trial = keep - {i}
            if _entry_state(world, event, world.inventory(start + [pool[j] for j in sorted(trial)])[0])[0]:
                keep = trial
        found.append(world.inventory(start + [pool[j] for j in sorted(keep)])[0])
    return found


def test_escape_control_values(world):
    resources = sorted(world.all_items())
    for event, missing in TRAPS.items():
        trapped = 0
        for inv in _minimal_entry_inventories(world, event):
            enter, events = _entry_state(world, event, inv)
            assert enter
            if world.escape_ok(event, inv, events):
                continue  # this minimal route already brings the item along
            trapped += 1
            fixes = []
            for res in resources:
                more = {**inv, res: inv.get(res, 0) + 1}
                if world.escape_ok(event, more, _entry_state(world, event, more)[1]):
                    fixes.append(res)
            assert fixes == [missing], f"{event}: with minimal items the escape needs {fixes}, expected {missing}"
        assert trapped, f"{event}: no minimal entry inventory is trapped"
    for event in NO_TRAP:
        for inv in _minimal_entry_inventories(world, event):
            enter, events = _entry_state(world, event, inv)
            assert enter and world.escape_ok(event, inv, events), f"{event} must not be a trap"
    # Flux Control Tunnel Cover: Spider Ball or X-Ray Visor
    event = "Flux Control Tunnel Cover"
    full = world.all_items()
    for drop, ok in ((("Spider Ball",), True), (("X-Ray Visor",), True), (("Spider Ball", "X-Ray Visor"), False)):
        inv = {k: 0 if k in drop else v for k, v in full.items()}
        enter, events = _entry_state(world, event, inv)
        assert enter
        assert world.escape_ok(event, inv, events) is ok, f"{event} without {drop}"


# ---------------------------------------------------------------- 6. reachability (replaces the T03 evaluator)
def reachability_report(world, data) -> tuple[bool, list[dict], list[str], list[str]]:
    """All items (pool + start), no tricks, AP logic with escape gates ("before event" = satisfied)."""
    reached, events, _, _ = world.reach(world.all_items())
    goal = GOAL_EVENT in events
    missing = [loc for loc in data.locations.LOCATIONS if world.loc_node[loc["id"]] not in reached]
    missing_dangerous = sorted(set(world.dangerous) - events)
    lines = [
        "Reachability: all items (pool + start), no tricks, escape gates on, 'before event' = satisfied",
        f"Goal event {GOAL_EVENT!r} reachable from {data.game.START_LOCATION}: {goal}",
        f"Locations reachable: {99 - len(missing)} / 99",
        f"Dangerous events reachable: {len(world.dangerous) - len(missing_dangerous)} / {len(world.dangerous)}",
    ]
    lines += [f"  unreachable: id {loc['id']:>2}  {loc['name']}" for loc in missing]
    lines += [f"  unreachable dangerous event: {name}" for name in missing_dangerous]
    return goal, missing, missing_dangerous, lines


# Its only entry needs the tricks "Single Room Out of Bounds" and "Bomb Jump" (level 3), with and without gates.
TRICK_ONLY_DANGEROUS = ["Gel Processing Site Out of Bounds"]


def test_everything_reachable_with_all_items_no_tricks_and_gates(world, data, capsys):
    goal, missing, missing_dangerous, lines = reachability_report(world, data)
    with capsys.disabled():
        print("\n" + "\n".join(lines))
    assert goal
    assert not missing
    assert missing_dangerous == TRICK_ONLY_DANGEROUS
    # the gates take nothing away: without them the same events are reached
    full = world.all_items()
    assert world.reach(full)[1] == world.reach(full, gated=False)[1]
    # with every trick enabled all 22 dangerous events are reachable through the gates
    all_tricks = playthrough_sim.World(data, tricks={t: 5 for t in data.game.TRICKS})
    assert set(world.dangerous) <= all_tricks.reach(full)[1]
    # location 0 is no AP location and not needed for that
    assert data.locations.UNPATCHED_LOCATION["id"] not in world.loc_node


# ---------------------------------------------------------------- 7. playthrough simulator
SIM_SEEDS = range(100)  # fixed seed range; the run takes about 16 s


def test_logic_following_player_wins_every_seed(world, capsys):
    """AP-style random fill + a player who follows the logic. He triggers allowed dangerous events at random,
    half of the time even before collecting what is reachable (eager = 0.5), and only enters a location whose
    escape_requirement holds (E22); if he cannot walk back from a pickup node he stays there."""
    result = playthrough_sim.simulate(world, SIM_SEEDS, eager=0.5)
    with capsys.disabled():
        print(f"\nPlaythrough simulator, seeds {SIM_SEEDS.start}-{SIM_SEEDS.stop - 1}: {result['summary']}")
    assert result["summary"].get("fill_failed", 0) == 0
    assert result["summary"]["won"] == len(SIM_SEEDS), result["failures"][:3]
    assert result["summary"]["all_99_collected"] == len(SIM_SEEDS)
    assert result["summary"]["trapped"] == 0


def test_simulator_detects_traps_without_gates(world):
    """Control: without the escape gate the same player gets trapped."""
    ungated = playthrough_sim.World(world.data)
    ungated.escape_ok = lambda event, inv, evs: True
    result = playthrough_sim.simulate(ungated, range(10), eager=1.0)
    assert result["summary"]["won"] < 10


# Seeds of the simulator's own fill in which the player, without location 98's rule, enters the Bryyo Leviathan Core
# before he owns Hyper Ball: 3 and 19 here (7 of seeds 0-99: 3, 19, 25, 27, 30, 41, 58).
B5_SEEDS = range(20)


def test_simulator_detects_dead_ends_without_location_rule(world):
    """Control (E22): fill and player without the locations' escape_requirement (logic before T25) get stuck in
    dead ends; with only location 98's rule removed the player is stranded in the Bryyo Leviathan Core (T08 B5)."""
    old_logic = playthrough_sim.World(world.data, location_escapes=False)
    result = playthrough_sim.simulate(old_logic, range(10), eager=0.5, dead_end_rule=False)
    assert result["summary"]["won"] < 10
    assert result["summary"]["trapped"] > 0

    b5 = playthrough_sim.World(world.data)
    b5.loc_rule[98] = (playthrough_sim._true, frozenset())
    stranded = []
    for seed in B5_SEEDS:
        rng = random.Random(seed)
        outcome = playthrough_sim.play(b5, playthrough_sim.fill(b5, rng), rng, 0.5)
        if outcome["trapped"]:
            stranded.append((seed, outcome["end"], outcome["dead_ends"]))
    assert stranded, "B5 not reproduced"
    assert all(end == world.loc_node[98] for _, end, _ in stranded), stranded



# ---------------------------------------------------------------- 7b. dead-end locations (E22)
# Control values from randovania/games/prime3/logic_database/* - Seed.txt: the only way out of each Leviathan core
# after its pickup ("Use Hyper Ball" = Hyper Ball + Hypermode, "Use Grapple Voltage" = Grapple Lasso + Voltage).
SEED_ESCAPES = {
    98: ({"Hyper Ball": 1, "HyperModeTank": 1, "Energy Tank": 1}, "Hyper Ball"),
    97: ({"Hyper Missile": 1, "Missile": 4}, "Hyper Missile"),
    99: ({"Hyper Grapple": 1, "Grapple Voltage": 1, "Grapple Lasso": 1}, "Hyper Grapple"),
}
# Every location whose escape_requirement is not implied by reaching it (documented in data/README.md).
NONTRIVIAL_LOCATION_ESCAPES = [26, 28, 29, 35, 56, 57, 58, 59, 60, 61, 62, 63, 64, 75, 76, 84, 86, 94, 95, 97, 98, 99]
# Locations whose escape needs their own vanilla item: that item can no longer be placed there (accepted, E22).
SELF_LOCKED_VANILLA = {63: "Boost Ball", 64: "Spider Ball", 76: "Hazard Shield", 95: "Nova Beam",
                       97: "Hyper Missile", 98: "Hyper Ball", 99: "Hyper Grapple"}


def _terms(req: dict) -> list[dict]:
    """A stored escape requirement (OR of ANDs of atoms) as a list of {name: amount} terms."""
    if req == {"and": []}:
        return [{}]
    alternatives = req["or"] if "or" in req else [req]
    out = []
    for alt in alternatives:
        atoms = alt["and"] if "and" in alt else [alt]
        out.append({a["name"]: a["amount"] for a in atoms})
    return out


def location_escape_report(data) -> list[str]:
    lines = ["Locations with a non-trivial escape_requirement (E22):"]
    for loc in data.locations.LOCATIONS:
        if loc["escape_requirement"] != {"and": []}:
            terms = _terms(loc["escape_requirement"])
            shortest = min(terms, key=lambda t: (len(t), sorted(t)))
            lines.append(f"  {loc['id']:>2}  {loc['name']}: {len(terms)} way(s) out, e.g. "
                         + " + ".join(f"{k}" if v == 1 else f"{k} >= {v}" for k, v in sorted(shortest.items())))
    return lines


def test_every_location_has_an_escape_requirement(data, world, capsys):
    full = world.all_items()
    _, events, _, _ = world.reach(full)
    nontrivial = []
    for loc in data.locations.LOCATIONS:
        req = loc["escape_requirement"]
        _event_atoms(req, set())  # only item/event/damage leaves, no "before"
        if req == {"and": []}:
            assert "escape_triggered_events" not in loc and "escape_inlined_events" not in loc
            continue
        nontrivial.append(loc["id"])
        assert loc["escape_triggered_events"] == sorted(loc["escape_triggered_events"])
        assert loc["escape_inlined_events"] == sorted(loc["escape_inlined_events"])
        assert world.location_ok(loc["id"], full, events), f"{loc['name']}: no escape even with all items"
        # starting items are owned anyway and never part of the requirement
        start = {r for item in data.items.STARTING_ITEMS for r, _ in item["stages"][0]}
        assert not any(start & set(term) for term in _terms(req)), loc["name"]
    with capsys.disabled():
        print("\n" + "\n".join(location_escape_report(data)))
    assert nontrivial == NONTRIVIAL_LOCATION_ESCAPES


def test_location_escape_control_values(data, world):
    """Locations 97/98/99 (Leviathan cores): one way out each, needing exactly the exit items; with everything
    but the exit item the core is reachable but the location is not in the logic."""
    full = world.all_items()
    for lid, (term, exit_item) in SEED_ESCAPES.items():
        loc = data.locations.LOCATIONS[lid - 1]
        assert loc["id"] == lid
        assert _terms(loc["escape_requirement"]) == [term], loc["name"]
        inv = {**full, exit_item: 0}
        reached, events, _, _ = world.reach(inv)
        assert world.loc_node[lid] in reached, f"{loc['name']} must stay reachable without {exit_item}"
        assert not world.location_ok(lid, inv, events)
        assert world.location_ok(lid, full, world.reach(full)[1])
    # Missile >= 4 for 97: entering the core already needs Missile >= 5, so Hyper Missile is the only missing item
    inv = {**full, "Missile": 3}
    assert not world.location_ok(97, inv, world.reach(inv)[1])


def test_location_escapes_are_cycle_free(data, world):
    """No escape_requirement uses an event that is only reachable through its own pickup node, or one that every
    way to the node already triggers (those count as satisfied)."""
    full = world.all_items()
    _, all_events, _, _ = world.reach(full)
    for loc in data.locations.LOCATIONS:
        atoms = _event_atoms(loc["escape_requirement"], set())
        if not atoms:
            continue
        node = world.loc_node[loc["id"]]
        _, without, _, _ = world.reach(full, blocked_nodes={node})
        assert not {y for y in atoms if y in all_events and y not in without}, loc["name"]
        assert not atoms & set(loc["escape_triggered_events"]), loc["name"]


def _inventories(world, count: int, seed: int) -> list[dict]:
    """Starting items plus: all progression but one item (each), and ``count`` random progression subsets."""
    start = list(world.data.items.STARTING_ITEMS)
    progression = [r for r in world.pool() if r["progression"]]
    names = sorted({r["name"] for r in progression})
    sets = [[r for r in progression if r["name"] != name] for name in names]
    rng = random.Random(seed)
    sets += [rng.sample(progression, rng.randint(0, len(progression))) for _ in range(count)]
    return [world.inventory(start + s)[0] for s in sets]


def test_logic_never_expects_a_location_without_a_way_back(data, world):
    """Independent of the converter's solver: wherever the logic allows a location (node reachable, escape
    requirement holds), a ship is reachable from its pickup node (AP logic from that node, events reached so far).
    Without the location rule this fails (control)."""
    def stranded(check_rule: bool) -> list:
        found = []
        for inv in _inventories(world, 25, 11):
            reached, events, _, _ = world.reach(inv)
            for lid in sorted(world.reachable_locations(reached)):
                if check_rule and not world.location_ok(lid, inv, events):
                    continue
                back, back_events, _, _ = world.reach(inv, start=[world.loc_node[lid]], events=events)
                if not any(n in back and fn(inv, back_events, False) for n, fn in world.ships):
                    found.append(lid)
        return found

    assert stranded(True) == []
    assert set(stranded(False)) >= {97, 98, 99}


def test_self_locked_vanilla_items(data, world, converter):
    """E22 side effect: a location whose escape needs its own vanilla item cannot hold it any more."""
    from randovania.game_description import default_database

    db = default_database.pickup_database_for_game(converter.preset.game)
    vanilla = {i.index: name for name, d in db.standard_pickups.items() for i in d.original_locations}
    records = {r["name"]: r for r in data.items.ITEMS}
    full = world.all_items()
    locked = {}
    for lid in NONTRIVIAL_LOCATION_ESCAPES:
        name = vanilla.get(lid)
        if name is None:
            continue  # expansion or Energy Cell
        resources = [r for r, _ in records[name]["stages"][0]] if name in records else [name]
        inv = {**full, **{r: 0 for r in resources}}
        if not world.location_ok(lid, inv, world.reach(inv)[1]):
            locked[lid] = name
    assert locked == SELF_LOCKED_VANILLA


# ---------------------------------------------------------------- 8. no randovania import
def _assert_no_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        pytest.fail(f"{path.name} imports {names}; generated data must be import-free")


def test_generated_files_import_nothing_from_randovania(out_a):
    for name in GENERATED_FILES:
        _assert_no_imports(out_a / name)
        assert "randovania" not in (out_a / name).read_text(encoding="utf-8").lower().replace("corruptovania", "")


def test_committed_data_package_does_not_import_randovania():
    assert (COMMITTED_DATA / "__init__.py").exists()
    assert (COMMITTED_DATA / "README.md").exists()
    for path in sorted(COMMITTED_DATA.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(a.name.split(".")[0] == "randovania" for a in node.names), path
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "randovania", path


if __name__ == "__main__":  # python apworld/tools/test_convert_db.py -> print the reachability reports only
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _run_converter(Path(tmp), "1")
        generated = Data(Path(tmp))
        print("\n".join(reachability_report(playthrough_sim.World(generated), generated)[3]))
        print("\n".join(location_escape_report(generated)))
