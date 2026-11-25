"""Finding and downloading the patch helper programs (T28, ``patcher/tools.py``). No network: urlopen is mocked."""

import hashlib
import io
import os
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from worlds.metroidprime3.patcher import build, cli, tools


def tools_zip(extra: dict[str, bytes] | None = None, skip: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in tools.REQUIRED_FILES:
            if name != skip:
                archive.writestr(name, b"exe:" + name.encode())
        archive.writestr("licenses/README.txt", b"licences")
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}


class ToolsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.cache = self.temp / "metroidprime3_tools"
        self.zip_bytes = tools_zip()
        self.sha = hashlib.sha256(self.zip_bytes).hexdigest()
        self.enterContext(patch.object(tools, "TOOLS_ZIP_SHA256", self.sha))
        env = {k: v for k, v in os.environ.items() if k not in (tools.TOOLS_ENV, tools.TOOLS_URL_ENV)}
        self.enterContext(patch.dict(os.environ, env, clear=True))
        # No developer checkout: the repo's gollop_mp3_patcher must not be found.
        self.enterContext(patch.object(tools, "checkout_tools_dir", return_value=self.temp / "no_checkout"))
        self.urlopen = self.enterContext(patch.object(tools.urllib.request, "urlopen"))
        self.serve(self.zip_bytes)
        self.messages: list[str] = []

    def serve(self, data: bytes) -> None:
        self.urlopen.side_effect = lambda *args, **kwargs: FakeResponse(data)

    def find(self, **kwargs) -> Path:
        return tools.find_tools(cache_dir=self.cache, progress=self.messages.append, **kwargs)


class TestDownload(ToolsTestCase):
    def test_download_success(self) -> None:
        folder = self.find()
        self.assertEqual(folder, tools.extracted_dir(self.cache))
        self.assertTrue(tools.is_tools_dir(folder))
        self.assertEqual((folder / "MP3Randomizer.exe").read_bytes(), b"exe:MP3Randomizer.exe")
        self.assertEqual((folder / tools.MARKER_NAME).read_text().strip(), self.sha)
        request = self.urlopen.call_args.args[0]
        self.assertEqual(request.full_url, tools.TOOLS_URL)
        self.assertFalse((self.cache / tools.TOOLS_ZIP_NAME).exists())  # only the extracted folder is kept
        self.assertFalse(list(self.cache.glob("*.part")))
        self.assertTrue(any(m.startswith("Downloading patch tools") for m in self.messages), self.messages)
        self.assertIn("Extracting patch tools...", self.messages)

    def test_wrong_hash(self) -> None:
        self.serve(tools_zip(extra={"evil.txt": b"x"}))
        with self.assertRaises(tools.PatchToolError) as context:
            self.find()
        message = str(context.exception)
        self.assertIn("SHA-256", message)
        self.assertIn(self.sha, message)
        self.assertIn(tools.RELEASE_PAGE, message)
        self.assertIsNone(tools.cached_tools_dir(self.cache))
        self.assertEqual([p.name for p in self.cache.iterdir()], [])  # nothing left behind

    def test_offline(self) -> None:
        self.urlopen.side_effect = urllib.error.URLError("[Errno 11001] getaddrinfo failed")
        with self.assertRaises(tools.PatchToolError) as context:
            self.find()
        message = str(context.exception)
        self.assertIn("Could not download the patch tools", message)
        self.assertIn("getaddrinfo failed", message)
        self.assertIn(tools.RELEASE_PAGE, message)
        self.assertIn(str(self.cache), message)
        self.assertIn("tools_folder", message)
        self.assertFalse((self.cache / tools.TOOLS_ZIP_NAME).exists())

    def test_http_error_is_reported_like_offline(self) -> None:
        self.urlopen.side_effect = urllib.error.HTTPError(tools.TOOLS_URL, 404, "Not Found", {}, None)
        with self.assertRaisesRegex(tools.PatchToolError, "Not Found"):
            self.find()

    def test_existing_cache_is_used_without_download(self) -> None:
        first = self.find()
        self.urlopen.reset_mock()
        self.messages.clear()
        self.assertEqual(self.find(), first)
        self.urlopen.assert_not_called()
        self.assertEqual(self.messages, [])

    def test_cache_of_other_version_is_ignored(self) -> None:
        old = tools.extracted_dir(self.cache, "f" * 64)
        old.mkdir(parents=True)
        for name in tools.REQUIRED_FILES:
            (old / name).parent.mkdir(parents=True, exist_ok=True)
            (old / name).write_bytes(b"old")
        (old / tools.MARKER_NAME).write_text("f" * 64)
        self.assertEqual(self.find(), tools.extracted_dir(self.cache))
        self.urlopen.assert_called_once()

    def test_incomplete_cache_is_replaced(self) -> None:
        folder = self.find()
        (folder / "nodtool" / "nodtool.exe").unlink()
        self.assertIsNone(tools.cached_tools_dir(self.cache))
        self.assertEqual(self.find(), folder)
        self.assertTrue((folder / "nodtool" / "nodtool.exe").is_file())

    def test_no_download_when_not_allowed(self) -> None:
        with self.assertRaisesRegex(tools.PatchToolError, "patch tools not found"):
            self.find(allow_download=False)
        self.urlopen.assert_not_called()

    def test_url_override(self) -> None:
        with patch.dict(os.environ, {tools.TOOLS_URL_ENV: "http://127.0.0.1:1/tools.zip"}):
            self.find()
        self.assertEqual(self.urlopen.call_args.args[0].full_url, "http://127.0.0.1:1/tools.zip")


class TestLookupOrder(ToolsTestCase):
    def test_configured_folder_wins(self) -> None:
        self.assertEqual(self.find(configured=self.temp / "mine"), self.temp / "mine")
        self.urlopen.assert_not_called()

    def test_environment_variable(self) -> None:
        with patch.dict(os.environ, {tools.TOOLS_ENV: str(self.temp / "env")}):
            self.assertEqual(self.find(), self.temp / "env")
        self.urlopen.assert_not_called()

    def test_checkout_fallback_before_download(self) -> None:
        checkout = self.temp / "checkout"
        for name in tools.REQUIRED_FILES:
            (checkout / name).parent.mkdir(parents=True, exist_ok=True)
            (checkout / name).write_bytes(b"")
        with patch.object(tools, "checkout_tools_dir", return_value=checkout):
            self.assertEqual(self.find(), checkout)
            self.urlopen.assert_not_called()
            # The cache comes before the checkout.
            tools.install_zip(self._local_zip(), self.cache, progress=self.messages.append)
            self.assertEqual(self.find(), tools.extracted_dir(self.cache))

    def _local_zip(self) -> Path:
        path = self.temp / tools.TOOLS_ZIP_NAME
        path.write_bytes(self.zip_bytes)
        return path

    def test_manually_placed_zip(self) -> None:
        self.cache.mkdir()
        (self.cache / tools.TOOLS_ZIP_NAME).write_bytes(self.zip_bytes)
        self.assertEqual(self.find(), tools.extracted_dir(self.cache))
        self.urlopen.assert_not_called()
        self.assertTrue((self.cache / tools.TOOLS_ZIP_NAME).is_file())  # the user's file is kept

    def test_manually_placed_zip_with_wrong_hash(self) -> None:
        self.cache.mkdir()
        (self.cache / tools.TOOLS_ZIP_NAME).write_bytes(b"not the tools")
        with self.assertRaisesRegex(tools.PatchToolError, "Delete it and download it again"):
            self.find()
        self.urlopen.assert_not_called()

    def test_zip_without_required_file(self) -> None:
        data = tools_zip(skip="wit/bin/wit.exe")
        with patch.object(tools, "TOOLS_ZIP_SHA256", hashlib.sha256(data).hexdigest()):
            self.serve(data)
            with self.assertRaisesRegex(tools.PatchToolError, "wit.exe"):
                self.find()
            self.assertIsNone(tools.cached_tools_dir(self.cache))

    def test_unsafe_zip_paths_are_rejected(self) -> None:
        for name in ("../escape.txt", "/abs.txt", "C:/x.txt"):
            with self.subTest(name=name):
                data = tools_zip(extra={name: b"x"})
                with patch.object(tools, "TOOLS_ZIP_SHA256", hashlib.sha256(data).hexdigest()):
                    self.serve(data)
                    with self.assertRaisesRegex(tools.PatchToolError, "unsafe path"):
                        self.find()
                self.assertFalse((self.temp / "escape.txt").exists())


class TestConstants(unittest.TestCase):
    def test_release_url(self) -> None:
        self.assertRegex(tools.TOOLS_ZIP_SHA256, r"^[0-9a-f]{64}$")
        self.assertRegex(tools.TOOLS_RELEASE_TAG, r"^v\d+\.\d+\.\d+$")
        self.assertEqual(tools.TOOLS_URL, f"https://github.com/junkx420/Prime3AP/releases/download/"
                                          f"{tools.TOOLS_RELEASE_TAG}/{tools.TOOLS_ZIP_NAME}")

    def test_default_cache_is_next_to_archipelago(self) -> None:
        import Utils

        self.assertEqual(tools.default_cache_dir(), Path(Utils.user_path("metroidprime3_tools")))

    def test_build_reexports(self) -> None:
        self.assertIs(build.PatchToolError, tools.PatchToolError)
        self.assertEqual(build.TOOLS_ENV, "MP3AP_TOOLS_DIR")


class TestCallers(unittest.TestCase):
    def test_patch_iso_looks_up_tools_with_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            iso = Path(temp, "in.iso")
            iso.write_bytes(b"RM3P01" + bytes(10))
            progress = Mock()
            error = tools.PatchToolError("offline")
            with patch.object(tools, "find_tools", side_effect=error) as find:
                with self.assertRaisesRegex(tools.PatchToolError, "offline"):
                    build.patch_iso(Mock(), iso, Path(temp, "out.iso"), progress=progress)
            find.assert_called_once_with(progress=progress)

    def test_read_seed_id_does_not_download_by_default(self) -> None:
        with patch.object(tools, "find_tools", side_effect=tools.PatchToolError("x")) as find:
            with self.assertRaises(tools.PatchToolError):
                build.read_seed_id_from_iso(Path("x.iso"))
        self.assertFalse(find.call_args.kwargs["allow_download"])

    def test_cli_tools_cache(self) -> None:
        with patch.object(tools, "find_tools", return_value=Path("cached")) as find, \
                patch.object(build, "read_seed_id_from_iso", return_value=(Mock(description="d", game_id="g"), None)) \
                as read:
            self.assertEqual(cli.main(["--read-seed-id", "x.iso", "--tools-cache", "c"]), 0)
        find.assert_called_once_with(cache_dir=Path("c"))
        read.assert_called_once_with(Path("x.iso"), Path("cached"), allow_download=True)


if __name__ == "__main__":
    unittest.main()
