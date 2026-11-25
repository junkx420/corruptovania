"""Tests for apworld/tools/savw_parser.py and build_location_flags.py (T12).

Usage from the repo root directory:

    venv/Scripts/python.exe -m pytest apworld/tools/test_savw_parser.py -v

The tests against the game data need an extracted PAL ISO (RM3P01), e.g. with
``DolphinTool extract -i mp3.iso -o <folder> -g``. The folder (which contains ``DATA/files``)
is given by the environment variable ``MP3_PAL_EXTRACTED``. Without it these tests are
skipped. Patched ISOs (Corruptovania patcher) yield the same table.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import struct
import sys
from pathlib import Path
from types import ModuleType

import pytest

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parents[1]
COMMITTED_TABLE = REPO_ROOT / "apworld" / "metroidprime3" / "location_flags.py"
GAME_DIR = os.environ.get("MP3_PAL_EXTRACTED")

needs_game = pytest.mark.skipif(
    not GAME_DIR, reason="MP3_PAL_EXTRACTED not set (path to the extracted PAL ISO)"
)

VALHALLA = 0xC133F919C108BDF9
NORION = 0x6FB8EF2A9523C343

# Measured live (docs/AP_LIVE_TESTS.md, test D): location -> (world, byte, full instance ID)
MEASURED = {
    11: (VALHALLA, 1, 0x00020032),
    3: (NORION, 7, 0x0002046B),
    4: (NORION, 8, 0x40020474),
}
SPECIAL_FUNCTION_LOCATIONS = {9, 34, 42, 43, 62, 70, 73, 79, 89, 93}


def _load(name: str) -> ModuleType:
    sys.path.insert(0, str(TOOLS_DIR))
    spec = importlib.util.spec_from_file_location(name, TOOLS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sp = _load("savw_parser")
blf = _load("build_location_flags")


def _committed() -> dict:
    ns: dict = {}
    exec(compile(COMMITTED_TABLE.read_text(encoding="utf-8"), str(COMMITTED_TABLE), "exec"), ns)
    return ns


# --------------------------------------------------------------------------- #
# Without game data
# --------------------------------------------------------------------------- #


def _entry(guid_byte: int, iid: int) -> bytes:
    return bytes([guid_byte]) * 16 + struct.pack(">I", iid)


def _synthetic_savw() -> bytes:
    d = struct.pack(">III", 0xC001D00D, 6, 3)
    d += struct.pack(">I", 1) + _entry(0xAA, 0x0001_0001)  # list 0 (CINE)
    d += struct.pack(">I", 3) + bytes(20) + _entry(0xBB, 0x0002_0005) + _entry(0xBC, 0x0802_0006)  # list 1 (MRLY)
    d += struct.pack(">I", 0)  # list 2 (DOOR)
    d += struct.pack(">I", 1) + struct.pack(">QI", 0x1122334455667788, 2)  # Scans
    d += struct.pack(">I", 0)  # unknown
    d += struct.pack(">I", 1) + b"LandingSite_X\0" + struct.pack(">III", 0, 1, 0)  # variables
    d += struct.pack(">I", 1) + _entry(0xCC, 0x0002_0010)  # list 3 (objects)
    return d + b"\xff" * (-len(d) % 64)


def test_parse_synthetic_savw():
    s = sp.parse_savw(_synthetic_savw())
    assert (s.version, s.area_count) == (6, 3)
    assert [len(x) for x in s.lists] == [1, 3, 0]
    assert s.lists[1][0].empty and not s.lists[1][1].empty
    # byte index = position in list 1, empty slots count too
    assert [e.instance_id for e in s.lists[1]] == [0, 0x0002_0005, 0x0802_0006]
    assert s.scans == (sp.SavwScan(0x1122334455667788, 2),)
    assert s.variables == (sp.SavwVariable("LandingSite_X", (0, 1, 0)),)
    assert [e.instance_id for e in s.objects] == [0x0002_0010]


def test_parse_savw_rejects_garbage():
    with pytest.raises(ValueError):
        sp.parse_savw(b"\0" * 64)
    with pytest.raises(ValueError):
        sp.parse_savw(_synthetic_savw()[:-1] + b"\x00")  # padding must be 0xFF


def test_lzo_fallback_literal_stream():
    stream = bytes([17 + 5]) + b"hello" + bytes([0x11, 0, 0])
    assert sp._lzo1x_decompress_py(stream, 5) == b"hello"
    try:
        import lzokay  # type: ignore[import-not-found]
    except ImportError:
        return
    data = bytes(range(256)) * 40 + b"abc" * 500
    assert sp._lzo1x_decompress_py(lzokay.compress(data), len(data)) == data


def test_pickup_locations_source():
    locs = blf.read_pickup_locations(blf.DEFAULT_LOCATIONS)
    assert [p.index for p in locs] == list(range(100))
    assert {p.index for p in locs if p.type == "SpecialFunction"} == SPECIAL_FUNCTION_LOCATIONS | {0}
    by_index = {p.index: p for p in locs}
    assert (by_index[11].layer, by_index[11].local_id) == (0, 0x0032)
    assert (by_index[3].layer, by_index[3].local_id) == (0, 0x046B)
    assert (by_index[4].layer, by_index[4].local_id) == (16, 0x0474)


def test_committed_table_shape():
    src = COMMITTED_TABLE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    assert not [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))], "no imports"
    ns = _committed()
    flags, details = ns["LOCATION_FLAGS"], ns["LOCATION_DETAILS"]
    assert sorted(flags) == list(range(1, 100)), "all 99 locations, location 0 is dropped"
    assert sorted(details) == sorted(flags)
    for idx, (mlvl, byte, obj) in flags.items():
        d = details[idx]
        assert mlvl in ns["WORLD_NAMES"]
        assert 0 <= byte < ns["FLAG_BLOCK_SIZE"], idx
        assert (d["area_index"], d["layer"]) == ((obj >> 16) & 0x3FF, obj >> 26), idx
        assert d["status"] in ("certain", "probable", "uncertain")
        assert d["reason"], idx
        # For SpecialFunction the second PCKP is in the SAVW, otherwise the PCKP itself
        assert d["savw_object"][0] == "PCKP"
        assert (d["type"] == "SpecialFunction") == (idx in SPECIAL_FUNCTION_LOCATIONS)
        if d["type"] == "Pickup":
            assert d["savw_object"][1] == obj
    seen = {}
    for idx, (mlvl, byte, _obj) in flags.items():
        assert (mlvl, byte) not in seen, f"locations {idx} and {seen.get((mlvl, byte))} share a byte"
        seen[(mlvl, byte)] = idx


def test_committed_table_measured_points():
    flags = _committed()["LOCATION_FLAGS"]
    for idx, expected in MEASURED.items():
        assert flags[idx] == expected, idx


# --------------------------------------------------------------------------- #
# With game data (MP3_PAL_EXTRACTED)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def game():
    return sp.GameFiles(GAME_DIR)


@pytest.fixture(scope="module")
def results(game):
    return {r.index: r for r in blf.analyse(game, blf.read_pickup_locations(blf.DEFAULT_LOCATIONS))}


@needs_game
def test_measured_points_from_game_data(results):
    for idx, (mlvl, byte, obj) in MEASURED.items():
        r = results[idx]
        assert (r.mlvl_id, r.byte_index, r.object_id) == (mlvl, byte, obj), idx
        assert r.status == "certain"


@needs_game
def test_flag_block_is_memory_relay_list(game):
    """Byte i = entry i of SAVW list 1, and this list contains only Memory Relays."""
    for idx, (mlvl_id, byte, _obj) in MEASURED.items():
        mlvl = sp.parse_mlvl(game.read(mlvl_id, "MLVL"), mlvl_id)
        savw = sp.parse_savw(game.read(mlvl.savw_id, "SAVW"), mlvl.savw_id)
        relay = savw.lists[1][byte]
        area = mlvl.areas[(relay.instance_id >> 16) & 0x3FF]
        mrea = sp.parse_mrea(game.read(area.mrea_id, "MREA"), area.mrea_id)
        types = {o.instance_id: o.type for _l, o in mrea.objects()}
        assert types[relay.instance_id] == "MRLY", idx


@needs_game
def test_special_function_savw_object(results):
    for idx in SPECIAL_FUNCTION_LOCATIONS:
        r = results[idx]
        assert r.type == "SpecialFunction"
        assert r.savw_object_type == "PCKP" and r.savw_object_id != r.object_id
        assert r.byte_index is not None


@needs_game
def test_all_savw_parse(game):
    n = 0
    for pak, res in game.iter_type("SAVW"):
        s = sp.parse_savw(pak.read(res.asset_id), res.asset_id)
        assert s.version == 6 and len(s.lists[1]) <= 1024
        n += 1
    assert n == 19  # 16 from Worlds.pak, plus 2 from FrontEnd.pak and 1 from UniverseArea.pak


@needs_game
def test_committed_table_is_up_to_date(results):
    text = blf.render([results[i] for i in sorted(results)])
    assert COMMITTED_TABLE.read_text(encoding="utf-8") == text, (
        "location_flags.py out of date: run build_location_flags.py again"
    )
