"""Find the patch tool's helper programs, or download them on first use (T28, docs/AP_PATCH_TOOL.md section 3).

The packed ``.apworld`` does not contain MP3Randomizer, nodtool and wit. They ship as a separate ZIP release asset on
``junkx420/Prime3AP`` (built by ``apworld/tools/release/build_release.py``). Lookup order of :func:`find_tools`:

1. an explicitly configured folder (``--tools``, ``metroidprime3_options.tools_folder`` in host.yaml),
2. ``$MP3AP_TOOLS_DIR``,
3. the cache folder (``<Archipelago>/metroidprime3_tools``) with the tools ZIP of this version already extracted,
4. ``randovania/data/gollop_mp3_patcher`` of a Corruptovania checkout (developers),
5. the tools ZIP placed into the cache folder by hand (offline install), else
6. download the ZIP from the fixed release URL, check its SHA-256, extract it into the cache folder.

Standard library only (no Archipelago import): the cache folder comes from Archipelago's ``Utils.user_path`` only if
Archipelago has already imported it.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

ProgressCallback = Callable[[str], None]


class PatchToolError(RuntimeError):
    pass


TOOLS_ENV = "MP3AP_TOOLS_DIR"
# Download from another URL (a mirror or a local test server). The SHA-256 below is enforced all the same.
TOOLS_URL_ENV = "MP3AP_TOOLS_URL"

RELEASE_REPO = "junkx420/Prime3AP"
# Release whose assets contain the tools ZIP this code expects. Tools change rarely, so later releases may keep
# pointing here. build_release.py rebuilds the ZIP and refuses to continue if its hash differs from TOOLS_ZIP_SHA256.
TOOLS_RELEASE_TAG = "v0.4.0"
TOOLS_ZIP_NAME = "metroidprime3-tools-win.zip"
TOOLS_ZIP_SHA256 = "2867aa6288c2e25eef176d36a22e2f4dfed0009a6aa73e42cda96ba16dd3b9c9"
TOOLS_URL = f"https://github.com/{RELEASE_REPO}/releases/download/{TOOLS_RELEASE_TAG}/{TOOLS_ZIP_NAME}"
RELEASE_PAGE = f"https://github.com/{RELEASE_REPO}/releases/tag/{TOOLS_RELEASE_TAG}"

CACHE_DIR_NAME = "metroidprime3_tools"
MARKER_NAME = "metroidprime3_tools.sha256"  # written after a verified extraction, holds TOOLS_ZIP_SHA256

# Base helpers for all regions. The NTSC-U diffs and hpatchz are validated by build when requested.
REQUIRED_FILES = (
    "MP3Randomizer.exe",
    "lzokay/lzokay.dll",
    "nodtool/nodtool.exe",
    "wit/bin/wit.exe",
    "dummy_attract/attract01.thp",
    "dummy_attract/Attract02.thp",
)

_CHUNK = 1 << 20
_PROGRESS_INTERVAL = 0.25  # seconds between download progress messages


def missing_files(folder: Path) -> list[str]:
    return [name for name in REQUIRED_FILES if not (Path(folder) / name).is_file()]


def is_tools_dir(folder: Path | None) -> bool:
    return folder is not None and Path(folder).is_dir() and not missing_files(Path(folder))


def checkout_tools_dir() -> Path:
    """``randovania/data/gollop_mp3_patcher`` of the repo this file lives in (developer fallback)."""
    # tools.py -> patcher -> metroidprime3 -> apworld -> repo root. resolve() follows the junction from worlds/.
    return Path(__file__).resolve().parents[3] / "randovania" / "data" / "gollop_mp3_patcher"


def default_cache_dir() -> Path:
    """``<Archipelago>/metroidprime3_tools`` when running inside Archipelago, else a per-user folder."""
    utils = sys.modules.get("Utils")
    if utils is not None and hasattr(utils, "user_path"):
        return Path(utils.user_path(CACHE_DIR_NAME))
    base = os.environ.get("LOCALAPPDATA") or os.path.join(Path.home(), ".cache")
    return Path(base) / CACHE_DIR_NAME


def extracted_dir(cache_dir: Path, sha256: str | None = None) -> Path:
    return Path(cache_dir) / f"tools-{(sha256 or TOOLS_ZIP_SHA256)[:12]}"


def cached_tools_dir(cache_dir: Path, sha256: str | None = None) -> Path | None:
    """The extracted tools of this version in ``cache_dir``, if complete."""
    sha256 = sha256 or TOOLS_ZIP_SHA256
    folder = extracted_dir(cache_dir, sha256)
    marker = folder / MARKER_NAME
    try:
        if marker.read_text(encoding="ascii").strip() != sha256:
            return None
    except OSError:
        return None
    return folder if is_tools_dir(folder) else None


def manual_instructions(cache_dir: Path) -> str:
    return (
        f"Download {TOOLS_ZIP_NAME} by hand from {RELEASE_PAGE} and put the ZIP file (not extracted) into "
        f"{cache_dir}, then open the .apmp3 again. Or extract it to any folder and set "
        "metroidprime3_options.tools_folder in host.yaml to that folder."
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        while chunk := file.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _megabytes(size: int) -> str:
    return f"{size / 1_000_000:.1f} MB"


def download(
    url: str,
    target: Path,
    sha256: str | None = None,
    progress: ProgressCallback = print,
    opener: Callable[..., Any] | None = None,
    timeout: float = 60,
) -> Path:
    """Download ``url`` to ``target`` and check its SHA-256. Nothing is left at ``target`` on failure."""
    sha256 = sha256 or TOOLS_ZIP_SHA256
    opener = opener or urllib.request.urlopen
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "metroidprime3-apworld"})
        with opener(request, timeout=timeout) as response, partial.open("wb") as file:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            last = 0.0
            while chunk := response.read(_CHUNK):
                file.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                now = time.monotonic()
                if now - last >= _PROGRESS_INTERVAL:
                    last = now
                    of_total = f" of {_megabytes(total)}" if total else ""
                    progress(f"Downloading patch tools (first use only): {_megabytes(done)}{of_total}...")
    except (urllib.error.URLError, OSError, ValueError) as error:
        partial.unlink(missing_ok=True)
        raise PatchToolError(
            f"Could not download the patch tools from {url}: {str(getattr(error, 'reason', error)).rstrip('.')}.\n"
            + manual_instructions(target.parent)
        ) from error
    found = digest.hexdigest()
    if found != sha256:
        partial.unlink(missing_ok=True)
        raise PatchToolError(
            f"The downloaded patch tools from {url} have SHA-256 {found}, expected {sha256}. The file was deleted.\n"
            + manual_instructions(target.parent)
        )
    os.replace(partial, target)
    return target


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    for info in members:
        path = PurePosixPath(info.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or ":" in info.filename:
            raise PatchToolError(f"unsafe path in tools ZIP: {info.filename!r}")
    return members


def install_zip(zip_path: Path, cache_dir: Path, sha256: str | None = None,
                progress: ProgressCallback = print) -> Path:
    """Check ``zip_path`` against ``sha256`` and extract it into the cache. Returns the tools folder."""
    sha256 = sha256 or TOOLS_ZIP_SHA256
    zip_path, cache_dir = Path(zip_path), Path(cache_dir)
    progress("Checking patch tools...")
    found = file_sha256(zip_path)
    if found != sha256:
        raise PatchToolError(
            f"{zip_path} has SHA-256 {found}, expected {sha256} ({TOOLS_ZIP_NAME} of {TOOLS_RELEASE_TAG}). "
            "Delete it and download it again.\n" + manual_instructions(cache_dir)
        )
    progress("Extracting patch tools...")
    final = extracted_dir(cache_dir, sha256)
    cache_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="extract-", dir=cache_dir))
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(staging, members=_safe_members(archive))
        if missing := missing_files(staging):
            raise PatchToolError(f"{zip_path} does not contain {missing}")
        (staging / MARKER_NAME).write_text(sha256 + "\n", encoding="ascii")
        if final.exists():
            shutil.rmtree(final)  # incomplete earlier extraction
        os.replace(staging, final)
    except zipfile.BadZipFile as error:
        raise PatchToolError(f"{zip_path} is not a valid ZIP file: {error}") from error
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return final


def find_tools(
    configured: Path | str | None = None,
    *,
    cache_dir: Path | None = None,
    progress: ProgressCallback = print,
    allow_download: bool = True,
    use_checkout: bool = True,
) -> Path:
    """Folder with the helper programs, in the order of the module docstring. Raises :class:`PatchToolError`."""
    if configured:
        return Path(configured)  # explicit choice: Toolchain.from_dir reports missing files
    if env := os.environ.get(TOOLS_ENV):
        return Path(env)
    cache_dir = (Path(cache_dir) if cache_dir else default_cache_dir()).absolute()  # absolute for the messages
    if cached := cached_tools_dir(cache_dir):
        return cached
    if use_checkout and is_tools_dir(checkout_tools_dir()):
        return checkout_tools_dir()
    local_zip = cache_dir / TOOLS_ZIP_NAME
    if local_zip.is_file():
        return install_zip(local_zip, cache_dir, progress=progress)
    if not allow_download:
        raise PatchToolError(f"patch tools not found (looked in {cache_dir}). " + manual_instructions(cache_dir))
    url = os.environ.get(TOOLS_URL_ENV) or TOOLS_URL
    progress("Downloading patch tools (first use only)...")
    download(url, local_zip, progress=progress)
    try:
        return install_zip(local_zip, cache_dir, progress=progress)
    finally:
        local_zip.unlink(missing_ok=True)  # the extracted folder is the cache
