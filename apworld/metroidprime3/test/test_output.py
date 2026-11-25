"""T05b: patch file ``.apmp3`` (generate_output), ``.apmp3`` input of the patch tool, launcher helpers, manifest."""

from __future__ import annotations

import importlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from BaseClasses import MultiWorld
from Fill import balance_multiworld_progression, distribute_items_restrictive
from test.general import gen_steps, setup_multiworld
from worlds.AutoWorld import AutoWorldRegister, call_all

from .. import MP3World, open_patch
from ..items import BASE_ID, GAME_NAME
from ..output import MP3Container, write_patch_file
from ..patcher import cli, layout, patch_data, seed_id
from ..settings import MP3Settings

WORLD_DIR = Path(__file__).resolve().parents[1]


def checksfinder_world() -> type:
    """ChecksFinder as second game (as in T04). AP_TEST_WORLDS=metroidprime3 does not auto-load it, so import it."""
    if "ChecksFinder" not in AutoWorldRegister.world_types:
        importlib.import_module("worlds.checksfinder")
    return AutoWorldRegister.world_types["ChecksFinder"]


CHECKSFINDER = checksfinder_world()


def generate(worlds: list, seed: int) -> MultiWorld:
    """Archipelago's generation steps up to progression balancing (like Main.py, without output)."""
    multiworld = setup_multiworld(worlds, gen_steps, seed)
    distribute_items_restrictive(multiworld)
    call_all(multiworld, "post_fill")
    balance_multiworld_progression(multiworld)
    return multiworld


def expected_pickups(multiworld: MultiWorld, player: int) -> dict[int, str]:
    expected = {}
    for location in multiworld.get_locations(player):
        if location.address is not None:
            item = location.item
            own = item.player == player and item.game == GAME_NAME
            expected[location.address - BASE_ID] = item.name if own else layout.AP_ITEM
    return expected


class PatchFileMixin(unittest.TestCase):
    def check_patch_file(self, multiworld: MultiWorld, player: int, path: Path) -> patch_data.PatchData:
        self.assertEqual(path.suffix, ".apmp3")
        self.assertTrue(path.name.startswith(multiworld.get_out_file_name_base(player)))

        # read with the patch tool (stdlib only) ...
        data, manifest = patch_data.read_container(path)
        self.assertEqual(sorted(data.pickups), list(range(1, 100)))  # 99 locations, no location 0
        self.assertEqual(data.pickups, expected_pickups(multiworld, player))
        self.assertEqual(data.seed_name, multiworld.seed_name)
        self.assertEqual(data.slot, player)
        self.assertEqual(data.player_name, multiworld.player_name[player])
        self.assertEqual(data.seed_id, seed_id.make_seed_id(multiworld.seed_name, player))
        self.assertEqual(manifest["game"], GAME_NAME)
        self.assertEqual(manifest["player"], player)
        self.assertEqual(manifest["player_name"], multiworld.player_name[player])
        self.assertEqual(manifest["patch_file_ending"], ".apmp3")
        self.assertEqual(manifest["procedure"], "custom")
        self.assertEqual(patch_data.load(path), data)  # load() detects the container

        # ... and with Archipelago's container class
        container = MP3Container(str(path))
        container.read()
        self.assertEqual(container.data, data)
        self.assertEqual(container.player, player)
        self.assertEqual(container.player_name, multiworld.player_name[player])
        return data


class TestPatchFileSolo(PatchFileMixin):
    def test_solo(self) -> None:
        multiworld = generate([MP3World], seed=5)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(write_patch_file(multiworld, 1, temp))
            data = self.check_patch_file(multiworld, 1, path)
        self.assertNotIn(layout.AP_ITEM, data.pickups.values())  # solo: every item is our own, shown for real
        for location in multiworld.get_locations(1):
            if location.address is not None:
                self.assertEqual(data.pickups[location.address - BASE_ID], location.item.name)


class TestPatchFileMultiworld(PatchFileMixin):
    def test_two_players_mp3_and_checksfinder(self) -> None:
        self._check([MP3World, CHECKSFINDER], seed=7, mp3_players=[1])

    def test_two_mp3_slots_and_checksfinder(self) -> None:
        # MP3 items of the other MP3 slot are foreign too (item.game is MP3, but another player)
        self._check([MP3World, CHECKSFINDER, MP3World], seed=11, mp3_players=[1, 3])

    def _check(self, worlds: list, seed: int, mp3_players: list[int]) -> None:
        multiworld = generate(worlds, seed)
        with tempfile.TemporaryDirectory() as temp:
            call_all(multiworld, "generate_output", temp)
            files = sorted(Path(temp).glob("*.apmp3"))
            self.assertEqual(len(files), len(mp3_players))  # exactly one per MP3 slot, none for ChecksFinder
            for player in mp3_players:
                path = Path(temp, f"{multiworld.get_out_file_name_base(player)}.apmp3")
                self.assertIn(path, files)
                data = self.check_patch_file(multiworld, player, path)
                foreign = [i for i, name in data.pickups.items() if name == layout.AP_ITEM]
                self.assertGreater(len(foreign), 0, "a multiworld seed should place foreign items in MP3")
                self.assertLess(len(foreign), 99)
                for location in multiworld.get_locations(player):
                    if location.address is None:
                        continue
                    name = data.pickups[location.address - BASE_ID]
                    if location.item.player != player:
                        self.assertEqual(name, layout.AP_ITEM)
                    else:
                        self.assertEqual(name, location.item.name)


def write_container(path: Path, manifest: dict | None, raw: dict | None) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        if manifest is not None:
            archive.writestr("archipelago.json", json.dumps(manifest))
        if raw is not None:
            archive.writestr("patch_data.json", json.dumps(raw))


class TestPatchToolContainerInput(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.raw = json.loads((WORLD_DIR / "patcher" / "example_patch.json").read_text(encoding="utf-8"))
        self.manifest = {"game": GAME_NAME, "player": self.raw["slot"], "player_name": self.raw["player_name"],
                         "server": "", "compatible_version": 6, "version": 7}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_container_constants(self) -> None:
        self.assertEqual(patch_data.CONTAINER_GAME, GAME_NAME)
        self.assertEqual(MP3Container.patch_file_ending, patch_data.CONTAINER_FILE_ENDING)
        self.assertEqual(MP3Container.game, GAME_NAME)

    def test_same_data_as_json(self) -> None:
        path = self.dir / "x.apmp3"
        write_container(path, self.manifest, self.raw)
        self.assertEqual(patch_data.load(path), patch_data.load(WORLD_DIR / "patcher" / "example_patch.json"))

    def test_rejects_bad_containers(self) -> None:
        cases = {
            "other game": ({**self.manifest, "game": "ChecksFinder"}, self.raw),
            "player mismatch": ({**self.manifest, "player": 2}, self.raw),
            "no manifest": (None, self.raw),
            "no patch data": (self.manifest, None),
            "bad patch data": (self.manifest, {**self.raw, "version": 2}),
            "wrong seed id": (self.manifest, {**self.raw, "seed_id": "00" * 16}),
        }
        for name, (manifest, raw) in cases.items():
            with self.subTest(name):
                path = self.dir / f"{name}.apmp3"
                write_container(path, manifest, raw)
                with self.assertRaises(patch_data.PatchDataError):
                    patch_data.load(path)
        not_zip = self.dir / "broken.apmp3"
        not_zip.write_bytes(b"PK\x03\x04 not really a zip")
        with self.assertRaises(patch_data.PatchDataError):
            patch_data.read_container(not_zip)

    def test_cli_dry_run_reads_apmp3(self) -> None:
        import contextlib
        import io

        path = self.dir / "x.apmp3"
        write_container(path, self.manifest, self.raw)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["--patch", str(path), "--dry-run"]), 0)
        self.assertIn(f"seed_id: {self.raw['seed_id']}", out.getvalue())


class TestLauncherHelpers(unittest.TestCase):
    def test_split_args(self) -> None:
        self.assertEqual(open_patch.split_args(("C:/x/AP_1_P1_Samus.apmp3", "--nogui")),
                         ("C:/x/AP_1_P1_Samus.apmp3", ["--nogui"]))
        self.assertEqual(open_patch.split_args(("--nogui",)), (None, ["--nogui"]))
        self.assertEqual(open_patch.split_args(("X.APMP3",))[0], "X.APMP3")

    def test_client_args(self) -> None:
        manifest = {"server": "archipelago.gg:12345", "player_name": "Samus"}
        self.assertEqual(open_patch.client_args(manifest, []),
                         ["--connect", "archipelago.gg:12345", "--name", "Samus"])
        self.assertEqual(open_patch.client_args({"server": "", "player_name": "Samus"}, ["--nogui"]),
                         ["--nogui", "--name", "Samus"])
        self.assertEqual(open_patch.client_args(manifest, ["--connect", "localhost:1", "--name", "B"]),
                         ["--connect", "localhost:1", "--name", "B"])
        self.assertEqual(open_patch.client_args(manifest, ["archipelago://B:pw@host:1"]),
                         ["archipelago://B:pw@host:1"])

    def test_output_path_and_tools(self) -> None:
        patch = Path("C:/seeds/AP_1_P1_Samus.apmp3")
        self.assertEqual(open_patch.output_path(patch, ""), Path("C:/seeds/AP_1_P1_Samus.iso"))
        self.assertEqual(open_patch.output_path(patch, "D:/isos"), Path("D:/isos/AP_1_P1_Samus.iso"))
        with tempfile.TemporaryDirectory() as temp:
            self.assertIsNone(open_patch.tools_dir(""))
            self.assertIsNone(open_patch.tools_dir(temp))  # no MP3Randomizer.exe -> patcher default
            Path(temp, "MP3Randomizer.exe").write_bytes(b"")
            self.assertEqual(open_patch.tools_dir(temp), Path(temp))

    def test_component_handles_apmp3(self) -> None:
        from worlds.LauncherComponents import components, identify

        component = next(c for c in components if c.display_name == "Metroid Prime 3 Client")
        self.assertTrue(component.handles_file("C:/x/AP_1_P1_Samus.apmp3"))
        self.assertFalse(component.handles_file("C:/x/AP_1.zip"))
        self.assertIs(identify("C:/x/AP_1_P1_Samus.apmp3")[1], component)
        self.assertEqual(component.game_name, GAME_NAME)


class TestSettings(unittest.TestCase):
    def test_iso_validation_checks_game_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            good = Path(temp, "good.iso")
            good.write_bytes(b"RM3P01" + bytes(64))
            MP3Settings.IsoFile.validate(str(good))
            bad = Path(temp, "bad.iso")
            bad.write_bytes(b"R3ME01" + bytes(64))  # Metroid Prime Trilogy
            with self.assertRaises(ValueError):
                MP3Settings.IsoFile.validate(str(bad))

    def test_world_settings_group(self) -> None:
        self.assertEqual(MP3World.settings_key, "metroidprime3_options")
        group = MP3Settings()
        self.assertEqual({"iso_file", "tools_folder", "output_folder"}, set(group))


class TestManifest(unittest.TestCase):
    def test_archipelago_json(self) -> None:
        manifest = json.loads((WORLD_DIR / "archipelago.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["game"], GAME_NAME)
        self.assertEqual(manifest["minimum_ap_version"], "0.6.8")
        self.assertRegex(manifest["world_version"], r"^\d+\.\d+\.\d+$")

    def test_packed_apworld_contents(self) -> None:
        """Same file selection and manifest as the launcher's "Build APWorlds" (LauncherComponents._build_apworlds)."""
        from Utils import local_path, read_apignore
        from worlds.Files import APWorldContainer

        ignores = read_apignore(local_path("data", "GLOBAL.apignore"))
        files = sorted(Path(f).as_posix() for f in ignores.match_tree_files(str(WORLD_DIR), negate=True))
        for needed in ("__init__.py", "output.py", "open_patch.py", "settings.py", "requirements.txt",
                       "data/logic.py", "patcher/patch_data.py", "client/context.py", "location_flags.py"):
            self.assertIn(needed, files)
        self.assertNotIn("archipelago.json", files)  # written separately with the full manifest
        self.assertFalse([f for f in files if "__pycache__" in f or f.endswith(".iso")])

        container = APWorldContainer("x.apworld")
        container.game = GAME_NAME
        manifest = json.loads((WORLD_DIR / "archipelago.json").read_text(encoding="utf-8"))
        manifest.update(container.get_manifest())
        self.assertEqual(manifest["game"], GAME_NAME)
        self.assertEqual(manifest["compatible_version"], 7)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp, "metroidprime3.apworld")
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("metroidprime3/archipelago.json", json.dumps(manifest))
            loaded = APWorldContainer(str(path))
            loaded.read()  # what Archipelago does before loading a packed world
            self.assertEqual(loaded.game, GAME_NAME)
            self.assertEqual(loaded.minimum_ap_version.as_simple_string(), "0.6.8")

    def test_requirements(self) -> None:
        lines = (WORLD_DIR / "requirements.txt").read_text(encoding="utf-8").split()
        self.assertEqual(lines, ["dolphin-memory-engine>=1.3.0"])
