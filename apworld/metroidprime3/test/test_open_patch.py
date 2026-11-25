import sys
import unittest
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import settings
import Utils
from worlds import metroidprime3
from worlds.metroidprime3 import client, open_patch
from worlds.metroidprime3.settings import MP3Settings


class TestOpenPatch(unittest.TestCase):
    def setUp(self) -> None:
        self.patch_file = Path("seed.apmp3")
        self.output = self.patch_file.with_suffix(".iso")
        self.data = SimpleNamespace(player_name="Samus", slot=1, seed_name="Seed", seed_id=bytes(16))
        self.result = SimpleNamespace(output=self.output, game_id="RM3P01", seed_id=self.data.seed_id)
        manifest = {"player_name": "Samus", "server": "localhost:1234"}
        self.options = SimpleNamespace(iso_file="original.iso", tools_folder="", output_folder="")
        self.enterContext(patch.object(metroidprime3, "MP3World", SimpleNamespace(settings=self.options)))
        self.enterContext(patch.object(settings, "get_settings", return_value=SimpleNamespace(changed=False)))
        self.enterContext(patch.object(open_patch.patch_data, "read_container", return_value=(self.data, manifest)))
        self.enterContext(patch.object(Utils, "init_logging"))
        self.enterContext(patch.object(Utils, "gui_enabled", True))
        self.messagebox = self.enterContext(patch.object(Utils, "messagebox"))
        self.launch_client = self.enterContext(patch.object(client, "launch"))
        self.read_seed = self.enterContext(patch.object(open_patch.build, "read_seed_id_from_iso"))
        self.output_exists = self.enterContext(patch.object(Path, "is_file", return_value=False))
        self.patch_iso = self.enterContext(patch.object(open_patch.build, "patch_iso"))

    def mock_window(self) -> tuple[Mock, Mock]:
        root = Mock()
        label = Mock()
        callbacks = Queue()
        root.after.side_effect = lambda delay, callback: callbacks.put(callback)

        def mainloop() -> None:
            while not root.quit.called:
                callbacks.get(timeout=5)()

        root.mainloop.side_effect = mainloop
        tk = SimpleNamespace(TclError=RuntimeError, Tk=Mock(return_value=root),
                             ttk=SimpleNamespace(Label=Mock(return_value=label)))
        self.enterContext(patch.dict(sys.modules, {"tkinter": tk}))
        return root, label

    def test_all_patch_steps_reach_window_before_client_starts(self) -> None:
        root, label = self.mock_window()
        steps = ["[1/6] Extracting ISO...", "[2/6] Removing attract videos...", "[3/6] Copying paks...",
                 "[4/6] Randomizing paks (MP3Randomizer --ap-mode)...", "[5/6] Writing seed ID into main.dol...",
                 "[6/6] Building ISO..."]

        def patch_iso(data, iso, out, *, tools_dir, progress):
            for step in steps:
                progress(step)
            return self.result

        self.patch_iso.side_effect = patch_iso
        self.launch_client.side_effect = lambda *args: root.destroy.assert_called_once()

        with self.assertLogs(open_patch.logger, level="INFO") as logs:
            open_patch.patch_and_launch(str(self.patch_file))

        self.assertEqual(label.configure.call_args_list, [call(text=step) for step in steps] + [
            call(text="Done. Starting the Metroid Prime 3 Client...")])
        self.assertEqual([line for line in logs.output if line.startswith("INFO:MetroidPrime3Patch:[")],
                         [f"INFO:MetroidPrime3Patch:{step}" for step in steps])
        self.launch_client.assert_called_once_with("--connect", "localhost:1234", "--name", "Samus")
        self.messagebox.assert_not_called()

    def test_patch_error_shows_message_and_skips_client(self) -> None:
        root, label = self.mock_window()
        self.patch_iso.side_effect = open_patch.build.PatchToolError("Extraction failed")
        self.messagebox.side_effect = lambda *args, **kwargs: root.destroy.assert_called_once()

        with self.assertLogs(open_patch.logger, level="ERROR"):
            open_patch.patch_and_launch(str(self.patch_file))

        label.configure.assert_not_called()
        self.messagebox.assert_called_once_with("Metroid Prime 3 – patch failed", "seed.apmp3:\nExtraction failed",
                                                error=True)
        self.launch_client.assert_not_called()

    def test_nogui_logs_patch_error(self) -> None:
        self.patch_iso.side_effect = open_patch.build.PatchToolError("Extraction failed")
        with patch.object(open_patch, "_patch_with_window") as window:
            with self.assertLogs(open_patch.logger, level="ERROR") as logs:
                open_patch.patch_and_launch(str(self.patch_file), "--nogui")

        self.assertIn("Extraction failed", logs.output[0])
        self.patch_iso.assert_called_once_with(self.data, Path(self.options.iso_file), self.output, tools_dir=None,
                                               progress=open_patch.logger.info)
        window.assert_not_called()
        self.messagebox.assert_not_called()
        self.launch_client.assert_not_called()

    def test_nogui_skips_missing_iso_dialog(self) -> None:
        metroidprime3.MP3World.settings = MP3Settings()
        with patch.object(MP3Settings.IsoFile, "exists", return_value=False):
            with patch.object(MP3Settings.IsoFile, "browse") as browse:
                with self.assertLogs(open_patch.logger, level="ERROR") as logs:
                    open_patch.patch_and_launch(str(self.patch_file), "--nogui")

        self.assertIn("MP3Settings.iso_file is required", logs.output[0])
        browse.assert_not_called()
        self.messagebox.assert_not_called()
        self.patch_iso.assert_not_called()
        self.launch_client.assert_not_called()

    def test_matching_seed_reuses_iso_without_window(self) -> None:
        self.output_exists.return_value = True
        self.read_seed.return_value = ("RM3P01", self.data.seed_id)

        with patch.object(open_patch, "_patch_with_window") as window:
            open_patch.patch_and_launch(str(self.patch_file))

        self.read_seed.assert_called_once_with(self.output, None)
        window.assert_not_called()
        self.patch_iso.assert_not_called()
        self.launch_client.assert_called_once_with("--connect", "localhost:1234", "--name", "Samus")
