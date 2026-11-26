"""Patch tool (T05a): letter table/checksum copy, patch data -> layout string, seed ID in main.dol.

The comparison with Randovania reads ``randovania/games/prime3/patcher/*.py`` of this repo as source (``ast``), without
importing randovania (SPEC 3a, ``TestNoRandovania``). Without a repo checkout next to the World those tests are skipped.
Real-DOL tests need ``MP3_PAL_EXTRACTED`` (extracted PAL ISO, as in apworld/tools/test_savw_parser.py) or
``MP3_PAL_DOL`` (path to main.dol); otherwise they are skipped.
"""

from __future__ import annotations

import ast
import hashlib
import itertools
import json
import os
import random
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from ..data import items as item_data
from ..patcher import build, layout, patch_data, seed_id

REPO = Path(__file__).resolve().parents[3]
GOLLOP_SOURCE = REPO / "randovania" / "games" / "prime3" / "patcher" / "gollop_corruption_patcher.py"
ITEMS_SOURCE = REPO / "randovania" / "games" / "prime3" / "patcher" / "corruption_items.py"
PATCHER_DIR = Path(__file__).resolve().parents[1] / "patcher"
EXAMPLE = PATCHER_DIR / "example_patch.json"

# Seed IVG2J7OR (Starter Preset, docs/AP_DEV_SETUP.md 4): Randovania's pickup names for index 0-99 and the layout
# string Randovania's patch data factory produced for it (build/seed/t01.patcher.json, same value as the T16 test in
# test/games/prime3/patcher/test_gollop_corruption_patcher.py).
IVG2J7OR_NAMES = [
    "Energy Tank", "Energy Tank", "Missile Expansion", "Missile Expansion", "Screw Attack", "Missile Expansion",
    "Missile Expansion", "Boost Ball", "Energy Cell 7", "Energy Tank", "Grapple Voltage", "Missile Expansion",
    "Missile Expansion", "Energy Cell 6", "Command Visor", "Energy Tank", "Missile Expansion", "Missile Expansion",
    "Missile Expansion", "Hyper Ball", "Energy Tank", "Energy Cell 2", "Progressive Missile", "Missile Expansion",
    "Energy Cell 5", "Energy Tank", "Ship Missile", "Missile Expansion", "Missile Expansion", "Progressive Beam",
    "Progressive Missile", "Missile Expansion", "Hyper Grapple", "Missile Expansion", "Missile Expansion",
    "Grapple Lasso", "Hazard Shield", "Missile Expansion", "Missile Expansion", "Missile Expansion",
    "Missile Expansion", "Missile Expansion", "Missile Expansion", "Missile Expansion", "Missile Expansion",
    "Missile Expansion", "Missile Expansion", "Grapple Swing", "Energy Cell 8", "Spider Ball", "Missile Expansion",
    "Missile Expansion", "Energy Cell 9", "Energy Tank", "Missile Expansion", "Ship Missile Expansion", "Energy Tank",
    "Missile Expansion", "Missile Expansion", "Missile Expansion", "Missile Expansion", "Ship Missile Expansion",
    "Ship Missile Expansion", "Missile Expansion", "Missile Expansion", "Ship Missile Expansion",
    "Ship Missile Expansion", "Energy Cell 3", "Missile Expansion", "Energy Cell 4", "Energy Tank",
    "Missile Expansion", "Missile Expansion", "Missile Expansion", "Hyper Missile", "Missile Expansion",
    "Missile Expansion", "Missile Expansion", "Energy Tank", "Hypermode", "Ship Missile Expansion",
    "Ship Missile Expansion", "Progressive Beam", "Missile Expansion", "Missile Expansion", "X-Ray Visor",
    "Missile Launcher", "Ship Missile Expansion", "Missile Expansion", "Energy Tank", "Energy Tank",
    "Missile Expansion", "Missile Expansion", "Ship Grapple", "Missile Expansion", "Energy Tank", "Missile Expansion",
    "Energy Cell 1", "Missile Expansion", "Energy Tank",
]  # fmt: skip
IVG2J7OR_LAYOUT = (
    "00kk44g44xtk944sdk444Cko{4rk^44}{4D447h44444444448uy44vk4Ik4444II44IIp4qk444B444kzII}44e#I4kk44H4k4n4kc602b"
)
# Randovania patch data of the same seed (Starter Preset).
IVG2J7OR_STARTING_ITEMS = "custom 0000000010010000000001100100100000000010000"
IVG2J7OR_STARTING_LOCATION = "custom c133f919c108bdf9 d8cf355d3e9e3741"


def _assignments(path: Path) -> dict[str, ast.AST]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            result[node.targets[0].id] = node
        elif isinstance(node, ast.FunctionDef):
            result[node.name] = node
    return result


def load_randovania_original() -> dict | None:
    """Letter table, checksum function and AP_ITEM from Randovania's source, executed without its imports."""
    if not GOLLOP_SOURCE.is_file() or not ITEMS_SOURCE.is_file():
        return None
    items_nodes = _assignments(ITEMS_SOURCE)
    gollop_nodes = _assignments(GOLLOP_SOURCE)
    namespace: dict = {"hashlib": hashlib, "AP_ITEM": ast.literal_eval(items_nodes["AP_ITEM"].value)}
    names = ["LAYOUT_LETTERS", "LETTER_TO_ITEM_MAPPING", "ITEM_NAME_TO_LETTER_MAPPING", "layout_string_for_items"]
    module = ast.Module(body=[gollop_nodes[name] for name in names], type_ignores=[])
    exec(compile(module, str(GOLLOP_SOURCE), "exec"), namespace)  # noqa: S102 - own repo source, no imports
    namespace["STARTING_ITEMS_ORDER"] = ast.literal_eval(gollop_nodes["STARTING_ITEMS_ORDER"].value)
    namespace["_function_ast"] = gollop_nodes["layout_string_for_items"]
    return namespace


ORIGINAL = load_randovania_original()
needs_randovania_source = unittest.skipIf(ORIGINAL is None, "Randovania source not found (no repo checkout)")


@needs_randovania_source
class TestLayoutCopy(unittest.TestCase):
    def test_tables_identical(self) -> None:
        self.assertEqual(layout.AP_ITEM, ORIGINAL["AP_ITEM"])
        self.assertEqual(layout.LAYOUT_LETTERS, ORIGINAL["LAYOUT_LETTERS"])
        self.assertEqual(layout.LETTER_TO_ITEM_MAPPING, ORIGINAL["LETTER_TO_ITEM_MAPPING"])
        self.assertEqual(list(layout.LETTER_TO_ITEM_MAPPING), list(ORIGINAL["LETTER_TO_ITEM_MAPPING"]))
        self.assertEqual(layout.ITEM_NAME_TO_LETTER_MAPPING, ORIGINAL["ITEM_NAME_TO_LETTER_MAPPING"])

    def test_checksum_function_identical(self) -> None:
        copy_ast = _assignments(PATCHER_DIR / "layout.py")["layout_string_for_items"]
        self.assertEqual(ast.dump(copy_ast), ast.dump(ORIGINAL["_function_ast"]))

    def test_same_output_for_random_placements(self) -> None:
        rng = random.Random(5)
        names = sorted(layout.ITEM_NAME_TO_LETTER_MAPPING)
        for _ in range(50):
            items = [rng.choice(names) for _ in range(layout.PICKUP_COUNT)]
            self.assertEqual(layout.layout_string_for_items(items), ORIGINAL["layout_string_for_items"](items))


class TestRandovaniaSeed(unittest.TestCase):
    def test_ivg2j7or_layout_matches_randovania(self) -> None:
        pickups = {index: IVG2J7OR_NAMES[index] for index in range(1, 100)}
        result = layout.layout_string_for_pickups(pickups, location_0_item=IVG2J7OR_NAMES[0])
        self.assertEqual(result, IVG2J7OR_LAYOUT)

    def test_ivg2j7or_via_patch_data(self) -> None:
        """Patch data -> MP3Randomizer data: same pickups as Randovania; only index 0 (never patched) and checksum differ."""
        pickups = {index: IVG2J7OR_NAMES[index] for index in range(1, 100)}
        data = patch_data.build_patch_data("seed", 1, "Samus", pickups)
        rando = data.randomizer_patch_data()
        self.assertEqual(rando["seed"][3:-5], IVG2J7OR_LAYOUT[3:-5])
        self.assertEqual(rando["seed"][:2], "00")
        self.assertEqual(rando["seed"][2], layout.ITEM_NAME_TO_LETTER_MAPPING[layout.LOCATION_0_ITEM])
        self.assertEqual(rando["starting_items"], IVG2J7OR_STARTING_ITEMS)
        self.assertEqual(rando["starting_location"], IVG2J7OR_STARTING_LOCATION)
        self.assertFalse(rando["mp3_update"] or rando["disable_deflicker"] or rando["missile_required_mains"])

    @needs_randovania_source
    def test_mixed_placement_matches_randovania(self) -> None:
        data = patch_data.load(EXAMPLE)
        names = [layout.LOCATION_0_ITEM] + [data.pickups[index] for index in range(1, 100)]
        self.assertEqual(data.layout_string(), ORIGINAL["layout_string_for_items"](names))
        self.assertIn("A", data.layout_string()[2:-5])


class TestPatchData(unittest.TestCase):
    def _valid(self) -> dict:
        return json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_example(self) -> None:
        data = patch_data.load(EXAMPLE)
        own = [name for name in data.pickups.values() if name != layout.AP_ITEM]
        self.assertEqual(len(data.pickups), 99)
        self.assertEqual(data.pickups[11], "Screw Attack")
        self.assertEqual(sum(name == layout.AP_ITEM for name in data.pickups.values()), 33)
        self.assertEqual(len(own), 66)
        self.assertEqual(data.seed_id, seed_id.make_seed_id("T05aExample", 1))

    def test_roundtrip(self) -> None:
        data = patch_data.load(EXAMPLE)
        self.assertEqual(patch_data.from_json(json.loads(json.dumps(data.to_json()))), data)

    def test_optional_fields_default_to_standard_preset(self) -> None:
        raw = self._valid()
        for key in ("seed_id", "starting_items", "starting_location"):
            del raw[key]
        data = patch_data.from_json(raw)
        self.assertEqual(data.starting_items, patch_data.STANDARD_STARTING_ITEMS)
        self.assertEqual(data.starting_location, patch_data.STANDARD_STARTING_LOCATION)
        self.assertEqual(data.seed_id, seed_id.make_seed_id(raw["seed_name"], raw["slot"]))

    def test_rejects_invalid(self) -> None:
        cases = {
            "missing index": lambda r: r["pickups"].pop("50"),
            "index 0": lambda r: r["pickups"].update({"0": "Missile Expansion"}),
            "index 100": lambda r: r["pickups"].update({"100": "Missile Expansion"}),
            "unknown item": lambda r: r["pickups"].update({"5": "Varia Suit"}),
            "multi-item letter only": lambda r: r["pickups"].update({"5": "Temporary Missile"}),
            "undecodable Power Beam": lambda r: r["pickups"].update({"5": "Power Beam"}),
            "undecodable CannonBall": lambda r: r["pickups"].update({"5": "CannonBall"}),
            "wrong seed id": lambda r: r.update({"seed_id": "00" * 16}),
            "unknown key": lambda r: r.update({"mp3_update": True}),
            "wrong format": lambda r: r.update({"format": "something"}),
            "newer version": lambda r: r.update({"version": 2}),
            "bad starting items": lambda r: r.update({"starting_items": "custom 00"}),
            "slot as string": lambda r: r.update({"slot": "1"}),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                raw = self._valid()
                mutate(raw)
                with self.assertRaises(patch_data.PatchDataError):
                    patch_data.from_json(raw)

    def test_comment_keys_allowed(self) -> None:
        raw = self._valid()
        raw["_generator"] = "test"
        patch_data.from_json(raw)

    def test_every_pool_item_is_displayable(self) -> None:
        for item in item_data.ITEMS:
            self.assertIn(item["name"], layout.DISPLAYABLE_ITEMS, item["name"])
        self.assertIn(layout.AP_ITEM, layout.DISPLAYABLE_ITEMS)

    @needs_randovania_source
    def test_standard_starting_items_are_the_data_starting_items(self) -> None:
        """Decode the start-item string with Randovania's order; it must give exactly data.items.STARTING_ITEMS."""
        order = ORIGINAL["STARTING_ITEMS_ORDER"]
        digits = patch_data.STANDARD_STARTING_ITEMS.split()[1]
        values, pos = {}, 0
        for name in order:
            width = 2 if name in ("MissileAmount", "MissileCapacity") else 1
            values[name] = int(digits[pos : pos + width], 16)
            pos += width
        self.assertEqual(pos, len(digits))
        given = {name for name, value in values.items() if value}
        short_names = {
            "Power Beam": "PowerBeam", "Charge Beam": "ChargeUpgrade", "Morph Ball Bombs": "Bomb",
            "Scan Visor": "ScanVisor", "Morph Ball": "MorphBall", "Space Jump Boots": "DoubleJump",
            "Combat Visor": None,  # always in the game's inventory, not part of the string
        }  # fmt: skip
        expected = {short_names[item["name"]] for item in item_data.STARTING_ITEMS} - {None}
        self.assertEqual(given, expected | {"HyperModeOriginal"})  # 1 = start without corrupted hypermode

    @needs_randovania_source
    def test_starting_items_string_matches_randovania_order(self) -> None:
        """T31: every subset of the starting items gives the string Randovania's starting_items_for would build."""
        order = ORIGINAL["STARTING_ITEMS_ORDER"]
        short_names = {"Power Beam": "PowerBeam", "Charge Beam": "ChargeUpgrade", "Morph Ball Bombs": "Bomb",
                       "Scan Visor": "ScanVisor", "Morph Ball": "MorphBall", "Space Jump Boots": "DoubleJump"}
        names = [item["name"] for item in item_data.STARTING_ITEMS]
        for size in range(len(names) + 1):
            for subset in itertools.combinations(names, size):
                values = {short_names[n]: 1 for n in subset if n in short_names} | {"HyperModeOriginal": 1}
                expected = "custom " + "".join(f"{values.get(name, 0):02x}" if name in ("MissileAmount",
                                                                                         "MissileCapacity")
                                               else f"{values.get(name, 0):x}" for name in order)
                self.assertEqual(patch_data.starting_items_string(subset), expected, subset)
                self.assertEqual(set(patch_data.starting_item_names(expected)), set(subset) - {"Combat Visor"})
        self.assertEqual(patch_data.starting_items_string(names), patch_data.STANDARD_STARTING_ITEMS)
        with self.assertRaises(patch_data.PatchDataError):
            patch_data.starting_items_string(["Screw Attack"])


class TestRandomizerCommand(unittest.TestCase):
    def test_ap_mode_and_no_optional_flags(self) -> None:
        toolchain = build.Toolchain(Path("r.exe"), Path("n.exe"), Path("w.exe"), Path("d"))
        data = patch_data.load(EXAMPLE)
        command = build.randomizer_command(toolchain, data, Path("in"), Path("out"))
        self.assertEqual(command[command.index("--layout") + 1], data.layout_string())
        self.assertIn("--ap-mode", command)
        for flag in ("--require-launcher", "--require-ship-missile", "--phaaze-skip", "--random-door-colors",
                     "--random-welding-colors"):
            self.assertNotIn(flag, command)
        self.assertEqual(command[command.index("--starting-items") + 1 : command.index("--starting-items") + 3],
                         patch_data.STANDARD_STARTING_ITEMS.split())

    def test_patcher_uses_stdlib_only(self) -> None:
        """The patch tool must run without Archipelago and Randovania (relative imports + stdlib only)."""
        allowed = set(sys.stdlib_module_names) | {"__future__", "patcher"}
        for path in PATCHER_DIR.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    modules = [node.module]
                else:
                    continue
                for module in modules:
                    self.assertIn(module.split(".")[0], allowed, f"{path.name}: {module}")


# --- Seed ID ------------------------------------------------------------------------------------------------------

PAL = seed_id.version_for_game_id("RM3P01")


def fake_dol(version: seed_id.DolVersion, build_string: bytes | None = None) -> bytearray:
    """Minimal DOL: one text section and one data section that contains the build string at its address."""
    header = bytearray(0x100)
    text_offset, text_address, text_size = 0x100, 0x80004000, 0x20
    data_offset, data_address, data_size = 0x120, version.build_string_address - 0x40, 0x100
    struct.pack_into(">I", header, 0x00, text_offset)
    struct.pack_into(">I", header, 0x48, text_address)
    struct.pack_into(">I", header, 0x90, text_size)
    struct.pack_into(">I", header, 0x1C, data_offset)  # data section 0 = section index 7
    struct.pack_into(">I", header, 0x64, data_address)
    struct.pack_into(">I", header, 0xAC, data_size)
    body = bytearray(text_size + data_size)
    raw = build_string if build_string is not None else version.build_string
    start = text_size + 0x40
    body[start : start + len(raw)] = raw
    return header + body


class TestSeedId(unittest.TestCase):
    def test_make_seed_id(self) -> None:
        a = seed_id.make_seed_id("12345", 1)
        self.assertEqual(len(a), 16)
        self.assertEqual(a, seed_id.make_seed_id("12345", 1))
        self.assertNotEqual(a, seed_id.make_seed_id("12345", 2))
        self.assertNotEqual(a, seed_id.make_seed_id("12346", 1))

    def test_write_read_fake_dol_all_versions(self) -> None:
        for version in seed_id.DOL_VERSIONS:
            with self.subTest(version.description):
                dol = fake_dol(version)
                self.assertEqual(seed_id.read_seed_id(bytes(dol)), (version, None))
                original = bytes(dol)
                new_id = seed_id.make_seed_id("seed", 3)
                self.assertEqual(seed_id.write_seed_id(dol, new_id), version)
                self.assertEqual(seed_id.read_seed_id(bytes(dol)), (version, new_id))
                changed = [i for i in range(len(dol)) if dol[i] != original[i]]
                self.assertTrue(changed)
                offset = seed_id.dol_offset_for_address(dol, version.seed_id_address)
                self.assertTrue(all(offset <= i < offset + 16 for i in changed))
                # Overwriting an older ID works.
                seed_id.write_seed_id(dol, seed_id.make_seed_id("seed", 4))
                self.assertEqual(seed_id.read_seed_id(bytes(dol))[1], seed_id.make_seed_id("seed", 4))

    def test_from_memory(self) -> None:
        new_id = bytes(range(16))
        raw = PAL.build_string[:6] + new_id + PAL.build_string[22:]
        self.assertEqual(seed_id.seed_id_from_build_string(raw, PAL), new_id)
        self.assertIsNone(seed_id.seed_id_from_build_string(PAL.build_string, PAL))
        with self.assertRaises(ValueError):
            seed_id.seed_id_from_build_string(seed_id.version_for_game_id("RM3E01").build_string, PAL)
        with self.assertRaises(ValueError):
            seed_id.seed_id_from_build_string(b"\0" * len(PAL.build_string), PAL)

    def test_rejects_bad_input(self) -> None:
        with self.assertRaises(ValueError):
            seed_id.write_seed_id(fake_dol(PAL), b"short")
        with self.assertRaises(ValueError):
            seed_id.write_seed_id(fake_dol(PAL), seed_id.ORIGINAL_SEED_ID_BYTES)
        with self.assertRaises(ValueError):
            seed_id.read_seed_id(bytes(fake_dol(PAL, b"!#$MetroidBuildInfo!#$1999/01/01 00:00 Build v0.000 (xxx)")))


def _real_dol() -> Path | None:
    if dol := os.environ.get("MP3_PAL_DOL"):
        return Path(dol)
    if extracted := os.environ.get("MP3_PAL_EXTRACTED"):
        for candidate in (Path(extracted) / "DATA" / "sys" / "main.dol", Path(extracted) / "sys" / "main.dol"):
            if candidate.is_file():
                return candidate
    return None


REAL_DOL = _real_dol()


@unittest.skipIf(REAL_DOL is None, "MP3_PAL_EXTRACTED / MP3_PAL_DOL not set (needs the PAL main.dol)")
class TestSeedIdRealDol(unittest.TestCase):
    def test_write_read_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            copy = Path(temp) / "main.dol"
            shutil.copy(REAL_DOL, copy)
            original = copy.read_bytes()
            self.assertEqual(seed_id.read_seed_id_from_dol_file(copy), (PAL, None))
            self.assertEqual(seed_id.dol_offset_for_address(original, PAL.build_string_address), 0x580488)

            new_id = seed_id.make_seed_id("T05aExample", 1)
            self.assertEqual(seed_id.write_seed_id_to_dol_file(copy, new_id), PAL)
            patched = copy.read_bytes()
            self.assertEqual(seed_id.read_seed_id_from_dol_file(copy), (PAL, new_id))
            self.assertEqual(len(patched), len(original))
            diff = [i for i in range(len(original)) if original[i] != patched[i]]
            self.assertTrue(diff)
            self.assertTrue(all(0x580488 + 6 <= i < 0x580488 + 22 for i in diff))
        self.assertEqual(REAL_DOL.read_bytes(), original)  # the source DOL is untouched


if __name__ == "__main__":
    unittest.main()
