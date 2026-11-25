"""Tests for apworld/tools/release/build_release.py (T28). Run from the repo root:

    python -m pytest -q apworld/tools/release
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

import build_release as br

TOOLS_PY_TEMPLATE = '''
TOOLS_RELEASE_TAG = "v0.3.0"
TOOLS_ZIP_NAME = "metroidprime3-tools-win.zip"
TOOLS_ZIP_SHA256 = "{sha}"
'''


def fake_repo(root: Path, world_version: str = "0.3.0", sha: str = "0" * 64) -> Path:
    for name, source in br.TOOLS_FILES.items():
        path = root / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
    world = root / br.WORLD_DIR
    (world / "patcher").mkdir(parents=True, exist_ok=True)
    (world / "__init__.py").write_bytes(b"# world\n")
    (world / "__pycache__").mkdir()
    (world / "__pycache__" / "x.pyc").write_bytes(b"pyc")
    (world / "out.iso").write_bytes(b"iso")
    (world / "test").mkdir()
    (world / "test" / "test_x.py").write_text("")
    (world / "archipelago.json").write_text(json.dumps(
        {"game": "Metroid Prime 3: Corruption", "minimum_ap_version": "0.6.8", "world_version": world_version}))
    (world / "patcher" / "tools.py").write_text(TOOLS_PY_TEMPLATE.format(sha=sha))
    return root


def set_tools_sha(root: Path, sha: str) -> None:
    (root / br.TOOLS_PY).write_text(TOOLS_PY_TEMPLATE.format(sha=sha))


def tools_sha(root: Path) -> str:
    return br.sha256_bytes(br.build_tools_zip(br.WorktreeSource(root)))


def test_tools_zip_is_deterministic(tmp_path: Path) -> None:
    root = fake_repo(tmp_path)
    first = br.build_tools_zip(br.WorktreeSource(root))
    assert first == br.build_tools_zip(br.WorktreeSource(root))
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        names = archive.namelist()
        assert names == sorted(br.TOOLS_FILES)
        assert {info.date_time for info in archive.infolist()} == {br.ZIP_DATE}
        assert archive.read("wit/bin/wit.exe") == b"wit/bin/wit.exe"


def test_tools_zip_has_what_the_patcher_needs_and_no_mp3update() -> None:
    tools_py = (br.REPO_ROOT / br.TOOLS_PY).read_text(encoding="utf-8")
    required = next(
        ast.literal_eval(node.value) for node in ast.parse(tools_py).body
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "REQUIRED_FILES"
    )
    assert set(required) <= set(br.TOOLS_FILES)
    assert not any("MP3Update" in name or "hpatchz" in name for name in br.TOOLS_FILES)
    assert all(name.startswith("licenses/") for name in br.TOOLS_FILES if "LICENSE" in name or "GPL" in name)
    for source in br.TOOLS_FILES.values():  # every source is in the real repo
        assert (br.REPO_ROOT / source).is_file(), source


def test_apworld_like_build_apworlds(tmp_path: Path) -> None:
    root = fake_repo(tmp_path)
    data, manifest = br.build_apworld(br.WorktreeSource(root))
    assert manifest == {"game": "Metroid Prime 3: Corruption", "minimum_ap_version": "0.6.8",
                        "world_version": "0.3.0", "compatible_version": 7, "version": 7}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        assert json.loads(archive.read("metroidprime3/archipelago.json")) == manifest
    assert names == {"metroidprime3/__init__.py", "metroidprime3/archipelago.json", "metroidprime3/patcher/tools.py",
                     "metroidprime3/test/test_x.py"}


@pytest.mark.parametrize(("path", "ignored"), [
    ("__pycache__/a.pyc", True), ("client/__pycache__/a.pyc", True), ("x.ISO", True), ("archipelago.json", True),
    (".gitignore", True), ("data/archipelago.json", False), ("data/logic.py", False), ("test/test_x.py", False),
])
def test_ignore_rules(path: str, ignored: bool) -> None:
    assert br.is_ignored(path) is ignored


def test_full_build_and_checks(tmp_path: Path) -> None:
    root = fake_repo(tmp_path / "repo")
    set_tools_sha(root, tools_sha(root))
    yaml = tmp_path / "Example.yaml"
    yaml.write_text("game: Metroid Prime 3: Corruption\n")
    out = tmp_path / "out"
    sources = fake_sources(root, tmp_path / "sources")
    logs: list[str] = []
    result = br.build_release("v0.3.0", out, br.WorktreeSource(root), example_yaml=yaml, sources_dir=sources,
                              log=logs.append)
    assert set(result) == {"metroidprime3-tools-win.zip", "metroidprime3.apworld", "metroidprime3-example.yaml",
                           "wit-src.tar.gz", "cygwin-src.tar.xz"}
    assert (out / "wit-src.tar.gz").read_bytes() == b"wit source"
    assert not any(" " in name for name in result)  # GitHub renames assets with spaces
    sums = (out / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    # sha256sum format, one line per asset, sorted by file name
    assert sums == [f"{hashlib.sha256((out / n).read_bytes()).hexdigest()}  {n}" for n in sorted(result)]
    assert all(result[n] == hashlib.sha256((out / n).read_bytes()).hexdigest() for n in result)

    with pytest.raises(br.ReleaseError, match="does not match release tag v0.4.0"):
        br.build_release("v0.4.0", out, br.WorktreeSource(root), example_yaml=None, include_sources=False,
                         log=logs.append)
    br.build_release("v0.4.0", out, br.WorktreeSource(root), example_yaml=None, allow_version_mismatch=True,
                     include_sources=False, log=logs.append)
    assert any("source archives not included" in line for line in logs)
    assert any(line.startswith("WARNING: world_version 0.3.0") for line in logs)
    assert any("downloads the tools ZIP from release v0.3.0, not v0.4.0" in line for line in logs)


def test_tools_hash_mismatch(tmp_path: Path) -> None:
    root = fake_repo(tmp_path / "repo")
    with pytest.raises(br.ReleaseError, match="Set the constant to the new hash"):
        br.build_release("v0.3.0", tmp_path / "out", br.WorktreeSource(root), example_yaml=None, log=print)
    result = br.build_release(None, tmp_path / "out", br.WorktreeSource(root), tools_only=True, log=print)
    assert result == {"metroidprime3-tools-win.zip": tools_sha(root)}


def fake_sources(root: Path, sources_dir: Path) -> Path:
    archives = {"wit-src.tar.gz": b"wit source", "cygwin-src.tar.xz": b"cygwin source"}
    entries = [{"asset": name, "component": name, "url": f"https://example.invalid/{name}", "origin": "test",
                "sha256": hashlib.sha256(data).hexdigest()} for name, data in archives.items()]
    (root / br.SOURCE_ARCHIVES_JSON).parent.mkdir(parents=True, exist_ok=True)
    (root / br.SOURCE_ARCHIVES_JSON).write_text(json.dumps(entries))
    sources_dir.mkdir(parents=True, exist_ok=True)
    for name, data in archives.items():
        (sources_dir / name).write_bytes(data)
    return sources_dir


def test_source_archive_missing_wrong_hash_and_fetch(tmp_path: Path) -> None:
    root = fake_repo(tmp_path / "repo")
    sources = fake_sources(root, tmp_path / "sources")
    entries = br.source_archives(br.WorktreeSource(root))
    out = tmp_path / "out"
    out.mkdir()

    (sources / "wit-src.tar.gz").unlink()
    with pytest.raises(br.ReleaseError, match="use --fetch-sources"):
        br.provide_source_archives(entries, sources, out, allow_fetch=False, log=print)

    requests = []

    def opener(request, timeout):
        requests.append(request.full_url)
        return io.BytesIO(b"wit source")

    names = br.provide_source_archives(entries, sources, out, allow_fetch=True, log=print, opener=opener)
    assert names == ["wit-src.tar.gz", "cygwin-src.tar.xz"]
    assert requests == ["https://example.invalid/wit-src.tar.gz"]  # the cached one is not fetched again
    assert (sources / "wit-src.tar.gz").read_bytes() == b"wit source"

    (sources / "cygwin-src.tar.xz").write_bytes(b"tampered")
    with pytest.raises(br.ReleaseError, match="delete it and fetch again"):
        br.provide_source_archives(entries, sources, out, allow_fetch=True, log=print, opener=opener)


def test_real_source_archives_manifest() -> None:
    entries = json.loads((br.REPO_ROOT / br.SOURCE_ARCHIVES_JSON).read_text(encoding="utf-8"))
    assert {e["asset"] for e in entries} == {"wiimms-iso-tools-r8638-src.tar.gz", "cygwin-3.1.7-1-src.tar.xz"}
    notices = (br.REPO_ROOT / br.RELEASE_DIR / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
    for entry in entries:
        assert entry["url"].startswith(("https://github.com/Wiimm/", "https://sourceware.org/pub/cygwin"))
        assert entry["asset"] in notices and entry["sha256"] in notices


def test_bad_tag() -> None:
    with pytest.raises(br.ReleaseError):
        br.tag_version("0.3.0")
    assert br.tag_version("v0.3.0") == "0.3.0"


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_source_reads_committed_blobs_only(tmp_path: Path) -> None:
    root = fake_repo(tmp_path)

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    git("init", "-q")
    git("config", "core.autocrlf", "false")
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "fake")
    (root / br.WORLD_DIR / "__init__.py").write_bytes(b"# uncommitted work of another worker\n")
    (root / br.WORLD_DIR / "wip.py").write_text("")
    source = br.GitSource("HEAD", repo=root)
    assert source.read(f"{br.WORLD_DIR}/__init__.py") == b"# world\n"
    assert f"{br.WORLD_DIR}/wip.py" not in source.list(br.WORLD_DIR)
    assert br.build_tools_zip(source) == br.build_tools_zip(br.WorktreeSource(root))
