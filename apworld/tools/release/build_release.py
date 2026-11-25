"""Build the release assets of Prime3AP (T28, docs/AP_APWORLD_DEV.md section "Release").

Writes into ``--out`` (default ``build/release``):

- ``metroidprime3.apworld``: the world folder ``apworld/metroidprime3`` packed like Archipelago's "Build APWorlds"
  component (same ignore rules, manifest = ``archipelago.json`` + ``compatible_version``/``version``),
- ``metroidprime3-tools-win.zip``: the patch tool's helper programs with licence texts (deterministic: sorted entries,
  fixed timestamps), its SHA-256 must equal ``patcher/tools.py TOOLS_ZIP_SHA256``,
- ``metroidprime3-example.yaml``: the example YAML from the Prime3AP repo (``--example-yaml``), if found,
- the source archives of the GPL/LGPL programs in the tools ZIP (``source_archives.json``: wit, Cygwin), taken from
  ``--sources-dir`` (default ``build/release-sources``) or, with ``--fetch-sources``, downloaded from their official
  URL; their SHA-256 is pinned in ``source_archives.json`` and checked,
- ``SHA256SUMS.txt`` over all assets.

All inputs are read from a Git commit (``--ref``, default ``HEAD``) of the Corruptovania repo, so uncommitted work of
other workers sharing the working tree never ends up in a release. ``--worktree`` reads the files on disk instead
(development only).

Checks: ``world_version`` in ``archipelago.json`` equals ``--tag`` (without ``v``); the tools ZIP hash equals the
constant in ``tools.py``. ``--allow-version-mismatch`` turns the first check into a warning (draft releases built
before the version bump).

Usage, from the Corruptovania root::

    python apworld/tools/release/build_release.py --tag v0.3.0 --fetch-sources
    python apworld/tools/release/build_release.py --tools-only     # prints the tools ZIP hash
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[3]
WORLD_DIR = "apworld/metroidprime3"
TOOLS_SRC = "randovania/data/gollop_mp3_patcher"
RELEASE_DIR = "apworld/tools/release"
TOOLS_PY = f"{WORLD_DIR}/patcher/tools.py"
SOURCE_ARCHIVES_JSON = f"{RELEASE_DIR}/source_archives.json"
DEFAULT_SOURCES_DIR = REPO_ROOT / "build" / "release-sources"

APWORLD_NAME = "metroidprime3.apworld"
WORLD_FOLDER_NAME = "metroidprime3"
# Archipelago 0.6.8 worlds/Files.py: container_version, APWorldContainer.get_manifest()["compatible_version"].
AP_CONTAINER_VERSION = 7
AP_COMPATIBLE_VERSION = 7
# data/GLOBAL.apignore of Archipelago 0.6.8
IGNORED_NAMES = {"__MACOSX", ".DS_Store", "__pycache__"}
IGNORED_TOP_LEVEL = {"archipelago.json", ".apignore", ".git", ".gitignore"}
IGNORED_SUFFIXES = {".sfc", ".z64", ".n64", ".nes", ".smc", ".sms", ".gb", ".gbc", ".gba", ".nds", ".iso"}

ZIP_DATE = (2026, 1, 1, 0, 0, 0)

# Path in the tools ZIP -> path in the repo. Only what patcher/build.py runs (PAL, no MP3Update/Deflicker, so no
# hpatchz/MP3Update) plus the DLLs wit.exe imports (PE import table: cygwin1, cygcrypto-1.1, cygncursesw-10, cygz).
TOOLS_FILES = {
    "MP3Randomizer.exe": f"{TOOLS_SRC}/MP3Randomizer.exe",
    "lzokay/lzokay.dll": f"{TOOLS_SRC}/lzokay/lzokay.dll",
    "nodtool/nodtool.exe": f"{TOOLS_SRC}/nodtool/nodtool.exe",
    "wit/bin/wit.exe": f"{TOOLS_SRC}/wit/bin/wit.exe",
    "wit/bin/cygwin1.dll": f"{TOOLS_SRC}/wit/bin/cygwin1.dll",
    "wit/bin/cygcrypto-1.1.dll": f"{TOOLS_SRC}/wit/bin/cygcrypto-1.1.dll",
    "wit/bin/cygncursesw-10.dll": f"{TOOLS_SRC}/wit/bin/cygncursesw-10.dll",
    "wit/bin/cygz.dll": f"{TOOLS_SRC}/wit/bin/cygz.dll",
    "dummy_attract/attract01.thp": f"{TOOLS_SRC}/dummy_attract/attract01.thp",
    "dummy_attract/Attract02.thp": f"{TOOLS_SRC}/dummy_attract/Attract02.thp",
    "README.txt": f"{RELEASE_DIR}/README-tools.txt",
    "THIRD-PARTY-NOTICES.txt": f"{RELEASE_DIR}/THIRD-PARTY-NOTICES.txt",
    "licenses/MP3Randomizer-LICENSE.txt": f"{TOOLS_SRC}/LICENSE",
    "licenses/lzokay-LICENSE.txt": f"{TOOLS_SRC}/lzokay/LICENSE",
    "licenses/nodtool-LICENSE.txt": f"{TOOLS_SRC}/nodtool/LICENSE",
    "licenses/wit-GPL-2.0.txt": f"{TOOLS_SRC}/wit/gpl-2.0.txt",
    "licenses/GPL-3.0.txt": f"{RELEASE_DIR}/licenses/GPL-3.0.txt",
    "licenses/LGPL-3.0.txt": f"{RELEASE_DIR}/licenses/LGPL-3.0.txt",
    "licenses/dotnet-runtime-LICENSE.txt": f"{RELEASE_DIR}/licenses/dotnet-runtime-LICENSE.txt",
    "licenses/dotnet-runtime-THIRD-PARTY-NOTICES.txt": f"{RELEASE_DIR}/licenses/dotnet-runtime-THIRD-PARTY-NOTICES.txt",
    "licenses/openssl-1.1.1-LICENSE.txt": f"{RELEASE_DIR}/licenses/openssl-1.1.1-LICENSE.txt",
    "licenses/ncurses-LICENSE.txt": f"{RELEASE_DIR}/licenses/ncurses-LICENSE.txt",
    "licenses/zlib-LICENSE.txt": f"{RELEASE_DIR}/licenses/zlib-LICENSE.txt",
}

DEFAULT_EXAMPLE_YAML = REPO_ROOT.parent / "Prime3AP" / "examples" / "Metroid Prime 3 Corruption.yaml"
# Asset name without spaces: GitHub replaces spaces in asset names by dots, which would break SHA256SUMS.txt.
EXAMPLE_ASSET_NAME = "metroidprime3-example.yaml"

Reader = Callable[[str], bytes]


class ReleaseError(RuntimeError):
    pass


# --- sources ---------------------------------------------------------------------------------------------------------


class GitSource:
    """Files of one commit, read as raw blobs (no line-ending conversion, so the ZIP bytes do not depend on the
    checkout's core.autocrlf)."""

    def __init__(self, ref: str, repo: Path = REPO_ROOT) -> None:
        self.repo = repo
        self.commit = self._git("rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()

    def _git(self, *args: str, data: bytes | None = None) -> bytes:
        result = subprocess.run(["git", "-C", str(self.repo), *args], input=data, capture_output=True, check=False)
        if result.returncode:
            raise ReleaseError(f"git {' '.join(args)} failed: {result.stderr.decode(errors='replace').strip()}")
        return result.stdout

    def list(self, folder: str) -> list[str]:
        out = self._git("ls-tree", "-r", "--name-only", "-z", self.commit, "--", folder)
        return sorted(name for name in out.decode("utf-8").split("\0") if name)

    def read(self, path: str) -> bytes:
        return self._git("cat-file", "blob", f"{self.commit}:{path}")


class WorktreeSource:
    """Files on disk (development only; may contain uncommitted work)."""

    commit = "worktree"

    def __init__(self, repo: Path = REPO_ROOT) -> None:
        self.repo = repo

    def list(self, folder: str) -> list[str]:
        base = self.repo / folder
        return sorted(path.relative_to(self.repo).as_posix() for path in base.rglob("*") if path.is_file())

    def read(self, path: str) -> bytes:
        return (self.repo / path).read_bytes()


# --- helpers ---------------------------------------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 0  # MS-DOS/Windows: no Unix mode bits
    info.external_attr = 0
    return info


def deterministic_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(entries):
            archive.writestr(zip_info(name), entries[name], compresslevel=9)
    return buffer.getvalue()


def is_ignored(relative: str) -> bool:
    """``data/GLOBAL.apignore`` of Archipelago 0.6.8 for a path relative to the world folder."""
    parts = PurePosixPath(relative).parts
    if any(part in IGNORED_NAMES for part in parts):
        return True
    if parts[0] in IGNORED_TOP_LEVEL:
        return True
    return PurePosixPath(relative).suffix.lower() in IGNORED_SUFFIXES


def tag_version(tag: str) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ReleaseError(f"release tag {tag!r} must look like v0.3.0")
    return tag[1:]


def tools_constants(tools_py: bytes) -> dict[str, str]:
    """String constants of patcher/tools.py (read without importing it)."""
    tree = ast.parse(tools_py.decode("utf-8"))
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                constants[node.targets[0].id] = node.value.value
    return constants


# --- builders --------------------------------------------------------------------------------------------------------


def build_tools_zip(source: GitSource | WorktreeSource) -> bytes:
    return deterministic_zip({name: source.read(path) for name, path in TOOLS_FILES.items()})


def build_apworld(source: GitSource | WorktreeSource) -> tuple[bytes, dict]:
    manifest = json.loads(source.read(f"{WORLD_DIR}/archipelago.json"))
    if manifest.get("game") != "Metroid Prime 3: Corruption":
        raise ReleaseError(f"unexpected game in archipelago.json: {manifest.get('game')!r}")
    manifest.update({"compatible_version": AP_COMPATIBLE_VERSION, "version": AP_CONTAINER_VERSION})
    entries = {}
    prefix = WORLD_DIR + "/"
    for path in source.list(WORLD_DIR):
        relative = path[len(prefix):]
        if not is_ignored(relative):
            entries[f"{WORLD_FOLDER_NAME}/{relative}"] = source.read(path)
    entries[f"{WORLD_FOLDER_NAME}/archipelago.json"] = json.dumps(manifest).encode("utf-8")
    if f"{WORLD_FOLDER_NAME}/__init__.py" not in entries:
        raise ReleaseError(f"{WORLD_DIR}/__init__.py missing in {source.commit}")
    return deterministic_zip(entries), manifest


def source_archives(source: GitSource | WorktreeSource) -> list[dict]:
    entries = json.loads(source.read(SOURCE_ARCHIVES_JSON))
    for entry in entries:
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) or " " in entry["asset"]:
            raise ReleaseError(f"bad entry in {SOURCE_ARCHIVES_JSON}: {entry}")
    return entries


def fetch(url: str, target: Path, opener: Callable = urllib.request.urlopen) -> None:
    partial = target.with_name(target.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "metroidprime3-release-build"})
    with opener(request, timeout=120) as response, partial.open("wb") as file:
        shutil.copyfileobj(response, file)
    partial.replace(target)


def provide_source_archives(
    entries: list[dict], sources_dir: Path, out: Path, *, allow_fetch: bool, log: Callable[[str], None],
    opener: Callable | None = None,
) -> list[str]:
    """Copy each archive (checked against its pinned SHA-256) from ``sources_dir`` into ``out``; download missing
    ones from the official URL if ``allow_fetch``."""
    sources_dir = Path(sources_dir)
    names = []
    for entry in entries:
        cached = sources_dir / entry["asset"]
        if not cached.is_file():
            if not allow_fetch:
                raise ReleaseError(f"source archive {cached} missing; use --fetch-sources to download it from "
                                   f"{entry['url']}")
            sources_dir.mkdir(parents=True, exist_ok=True)
            log(f"Downloading {entry['url']}")
            fetch(entry["url"], cached, opener or urllib.request.urlopen)
        found = sha256_file(cached)
        if found != entry["sha256"]:
            raise ReleaseError(f"{cached} has SHA-256 {found}, expected {entry['sha256']} ({SOURCE_ARCHIVES_JSON}); "
                               "delete it and fetch again")
        shutil.copyfile(cached, out / entry["asset"])
        log(f"{entry['asset']}: {cached.stat().st_size:,} bytes, source of {entry['component']}")
        names.append(entry["asset"])
    return names


def write_sums(out: Path, names: list[str]) -> Path:
    sums = out / "SHA256SUMS.txt"
    sums.write_text("".join(f"{sha256_file(out / name)}  {name}\n" for name in sorted(names)), encoding="utf-8",
                    newline="\n")
    return sums


def build_release(
    tag: str | None,
    out: Path,
    source: GitSource | WorktreeSource,
    *,
    example_yaml: Path | None = DEFAULT_EXAMPLE_YAML,
    allow_version_mismatch: bool = False,
    tools_only: bool = False,
    include_sources: bool = True,
    sources_dir: Path = DEFAULT_SOURCES_DIR,
    fetch_sources: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, str]:
    """Build the assets, run the checks, return {asset name: sha256}."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    constants = tools_constants(source.read(TOOLS_PY))
    tools_name = constants["TOOLS_ZIP_NAME"]

    tools_zip = build_tools_zip(source)
    tools_hash = sha256_bytes(tools_zip)
    (out / tools_name).write_bytes(tools_zip)
    log(f"{tools_name}: {len(tools_zip):,} bytes, SHA-256 {tools_hash}")
    if tools_only:
        return {tools_name: tools_hash}
    if tools_hash != constants["TOOLS_ZIP_SHA256"]:
        raise ReleaseError(
            f"tools ZIP SHA-256 {tools_hash} != TOOLS_ZIP_SHA256 {constants['TOOLS_ZIP_SHA256']} in {TOOLS_PY} "
            f"({source.commit}). Set the constant to the new hash, commit, and build again."
        )

    apworld, manifest = build_apworld(source)
    (out / APWORLD_NAME).write_bytes(apworld)
    log(f"{APWORLD_NAME}: {len(apworld):,} bytes, world_version {manifest.get('world_version')}")

    if tag is not None:
        expected = tag_version(tag)
        found = manifest.get("world_version")
        if found != expected:
            message = f"world_version {found} in {WORLD_DIR}/archipelago.json does not match release tag {tag}"
            if not allow_version_mismatch:
                raise ReleaseError(message + " (set world_version first, or --allow-version-mismatch for a draft)")
            log(f"WARNING: {message}; rebuild after the version bump before publishing")
        if constants["TOOLS_RELEASE_TAG"] != tag:
            log(f"Note: the code downloads the tools ZIP from release {constants['TOOLS_RELEASE_TAG']}, not {tag}")

    names = [tools_name, APWORLD_NAME]
    if example_yaml and Path(example_yaml).is_file():
        target = out / EXAMPLE_ASSET_NAME
        target.write_bytes(Path(example_yaml).read_bytes())
        names.append(target.name)
    elif example_yaml:
        log(f"WARNING: example YAML {example_yaml} not found, not included")
    if include_sources:
        names += provide_source_archives(source_archives(source), sources_dir, out, allow_fetch=fetch_sources, log=log)
    else:
        log("WARNING: source archives not included (GPL/LGPL programs in the tools ZIP need them in a release)")
    sums = write_sums(out, names)
    log(f"{sums.name}:\n{sums.read_text(encoding='utf-8')}")
    log(f"Built from {source.commit}")
    return {name: sha256_file(out / name) for name in names}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tag", help="release tag, e.g. v0.3.0 (checked against world_version)")
    parser.add_argument("--ref", default="HEAD", help="Git commit to build from (default: HEAD)")
    parser.add_argument("--worktree", action="store_true", help="read files from disk instead of --ref (dev only)")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "build" / "release")
    parser.add_argument("--example-yaml", type=Path, default=DEFAULT_EXAMPLE_YAML)
    parser.add_argument("--allow-version-mismatch", action="store_true",
                        help="only warn if world_version != --tag (draft before the version bump)")
    parser.add_argument("--tools-only", action="store_true", help="only build the tools ZIP and print its hash")
    parser.add_argument("--sources-dir", type=Path, default=DEFAULT_SOURCES_DIR,
                        help="where the source archives of source_archives.json are cached")
    parser.add_argument("--fetch-sources", action="store_true",
                        help="download missing source archives from their official URL (hash still checked)")
    parser.add_argument("--no-sources", action="store_true", help="do not attach the source archives (dev only)")
    args = parser.parse_args(argv)
    if not args.tag and not args.tools_only:
        parser.error("--tag is required (or --tools-only)")
    try:
        source = WorktreeSource() if args.worktree else GitSource(args.ref)
        build_release(args.tag, args.out, source, example_yaml=args.example_yaml,
                      allow_version_mismatch=args.allow_version_mismatch, tools_only=args.tools_only,
                      include_sources=not args.no_sources, sources_dir=args.sources_dir,
                      fetch_sources=args.fetch_sources)
    except (ReleaseError, OSError, KeyError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
