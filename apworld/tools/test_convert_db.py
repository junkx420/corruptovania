"""Acceptance tests for apworld/tools/convert_db.py (T03).

Run from the repo root:
    venv/Scripts/python.exe -m pytest apworld/tools/test_convert_db.py -s

The generated data is produced once per session by running the converter as a subprocess.
Randovania is only used here as the reference ("Corruptovania loader"), never by the generated files.
"""

from __future__ import annotations

import ast
import collections
import importlib.util
import math
import os
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
GOAL_EVENT = "Aurora Unit 313"


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
        assert committed.read_bytes() == (out_a / name).read_bytes(), f"{name} is stale: regenerate it"


# ---------------------------------------------------------------- 2. locations
def test_exactly_99_locations_with_ids_1_to_99(data):
    locations = data.locations.LOCATIONS
    assert len(locations) == 99
    assert [loc["id"] for loc in locations] == list(range(1, 100))
    assert len({loc["name"] for loc in locations}) == 99
    for loc in locations:
        assert loc["name"] == f"{loc['region']} - {loc['area']} - {loc['node']}"
    assert data.locations.UNPATCHED_LOCATION["id"] == 0


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
def test_exactly_99_items_matching_standard_pool_minus_location_0(data, converter):
    from randovania.game_description import default_database
    from randovania.generator.pickup_pool import pool_creator

    pool = pool_creator.calculate_pool_results(converter.config, converter.game)
    standard = collections.Counter(p.name for p in pool.to_place)
    assert sum(standard.values()) == 100, "the standard pool is expected to have 100 items"

    db = default_database.pickup_database_for_game(converter.preset.game)
    at_zero = [n for n, d in db.standard_pickups.items() if any(i.index == 0 for i in d.original_locations)]
    assert at_zero == [EXPECTED_LOCATION_0_ITEM]
    assert data.items.LOCATION_0_ITEM["name"] == EXPECTED_LOCATION_0_ITEM

    expected = standard.copy()
    expected[EXPECTED_LOCATION_0_ITEM] -= 1
    expected = +expected  # drops zero counts

    actual = collections.Counter()
    for item in data.items.ITEMS:
        assert item["name"] not in actual, "ITEMS must list each name once, with a count"
        actual[item["name"]] += item["count"]

    assert sum(actual.values()) == 99 == len(data.locations.LOCATIONS)
    assert actual == expected
    assert EXPECTED_LOCATION_0_ITEM not in actual


def test_item_records_are_complete(data):
    for item in data.items.ITEMS + data.items.STARTING_ITEMS + [data.items.LOCATION_0_ITEM]:
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


# ---------------------------------------------------------------- 5. reachability
class Evaluator:
    """Minimal AP-style evaluator of the generated data (what T04 has to implement)."""

    def __init__(self, data: Data, tricks: dict[str, int] | None = None, before_event: bool = False) -> None:
        self.data = data
        self.before_event = before_event  # value of every "before <event>" requirement (MVP: False)
        settings = data.game.SETTINGS
        self.tricks = dict(settings["trick_level"]["levels"]) if tricks is None else tricks
        self.misc = settings["misc_resources"]
        self.version = settings["version_resources"]
        self.damage = settings["damage"]
        self.templates = data.logic.TEMPLATES
        self.items: dict[str, int] = collections.defaultdict(int)
        self.events: set[str] = set()

    def give(self, record: dict) -> None:
        stages = record["stages"]
        for copy in range(record["count"]):
            for resource, amount in stages[min(copy, len(stages) - 1)]:
                self.items[resource] += amount

    def energy(self) -> int:
        return self.damage["starting_energy"] + self.damage["energy_per_tank"] * self.items["Energy Tank"]

    def sat(self, req: dict) -> bool:
        if "and" in req:
            return all(self.sat(r) for r in req["and"])
        if "or" in req:
            return any(self.sat(r) for r in req["or"])
        kind, amount, negate = req["type"], req.get("amount", 1), req.get("negate", False)
        if kind == "template":
            return self.sat(self.templates[req["name"]])
        if kind == "node":
            return False  # unsupported in the MVP
        if kind == "event":
            return self.before_event if negate else req["name"] in self.events  # "before event": MVP not satisfied
        if kind == "item":
            return False if negate else self.items[req["name"]] >= amount  # "no item": not satisfied
        if kind == "damage":
            reduction = 1.0
            for item, multiplier in self.damage["reductions"].get(req["name"], []):
                if item is None or self.items[item] > 0:
                    reduction = min(reduction, multiplier)
            needed = math.ceil(reduction * int(amount * self.damage["strictness"]))
            return self.energy() > needed
        table = {"trick": self.tricks, "misc": self.misc, "version": self.version}.get(kind)
        if table is None:
            raise AssertionError(f"unknown requirement type {kind}")
        have = table.get(req["name"], 0)
        return have < amount if negate else have >= amount

    def run(self) -> set[tuple[str, str, str]]:
        logic = self.data.logic
        reached = {tuple(self.data.game.START_LOCATION)}
        changed = True
        while changed:
            changed = False
            for conn in logic.CONNECTIONS:
                if tuple(conn["to"]) not in reached and tuple(conn["from"]) in reached and self.sat(conn["requirement"]):
                    reached.add(tuple(conn["to"]))
                    changed = True
            for name, event in logic.EVENTS.items():
                if name in self.events:
                    continue
                for src in event["sources"]:
                    if tuple(src["node"]) in reached and self.sat(src["requirement"]):
                        self.events.add(name)
                        changed = True
                        break
        return reached


def _all_items_no_tricks(data: Data, before_event: bool = False) -> Evaluator:
    ev = Evaluator(data, tricks={name: 0 for name in data.game.TRICKS}, before_event=before_event)
    for record in data.items.ITEMS + data.items.STARTING_ITEMS + [data.items.LOCATION_0_ITEM]:
        ev.give(record)
    return ev


def unreachable_report(data: Data) -> tuple[bool, list[dict], list[str]]:
    """(goal reachable, unreachable locations, lines of the report)."""
    ev = _all_items_no_tricks(data)
    reached = ev.run()
    goal = ev.sat(data.game.VICTORY_REQUIREMENT)
    missing = [loc for loc in data.locations.LOCATIONS
               if (loc["region"], loc["area"], loc["node"]) not in reached]
    lines = [
        "Reachability: all items (pool + start + vanilla item of location 0), no tricks, "
        "'before event' = not satisfied, 'no item' = not satisfied",
        f"Goal event {GOAL_EVENT!r} reachable from {data.game.START_LOCATION}: {goal}",
        f"Locations reachable: {99 - len(missing)} / 99, unreachable: {len(missing)}",
    ]
    lines += [f"  unreachable: id {loc['id']:>2}  {loc['name']}" for loc in missing]
    # Information only: the same check if every "before <event>" requirement counted as satisfied.
    optimistic = _all_items_no_tricks(data, before_event=True)
    reached_opt = optimistic.run()
    missing_opt = [loc["id"] for loc in data.locations.LOCATIONS
                   if (loc["region"], loc["area"], loc["node"]) not in reached_opt]
    lines.append(f"Information: with every 'before event' counted as satisfied, unreachable ids: {missing_opt}")
    return goal, missing, lines


def test_goal_reachable_with_all_items_no_tricks(data, capsys):
    goal, missing, lines = unreachable_report(data)
    with capsys.disabled():
        print("\n" + "\n".join(lines))
    assert goal, f"{GOAL_EVENT} not reachable with all items and no tricks"
    # An empty or non-empty list of unreachable locations is not a failure; it only has to be reported.
    assert isinstance(missing, list)


# ---------------------------------------------------------------- 6. no randovania import
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


if __name__ == "__main__":  # python apworld/tools/test_convert_db.py -> print the reachability report only
    sys.path.insert(0, str(TOOLS_DIR))
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _run_converter(Path(tmp), "1")
        print("\n".join(unreachable_report(Data(Path(tmp)))[2]))
