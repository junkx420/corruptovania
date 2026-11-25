"""Original ISO + AP patch data -> patched ISO.

Same steps as Randovania's prime3 exporter (``randovania/games/prime3/exporter/game_exporter.py``): extract with
nodtool, replace the attract videos, stage the paks, run MP3Randomizer, rebuild with wit. Differences: MP3Randomizer
always runs with ``--ap-mode`` (T16), MP3Update/Deflicker are opt-in for NTSC-U, and the seed ID is written into
``main.dol`` (T18 part 1). No Randovania import; the helper programs come from a tools folder
(:func:`.tools.find_tools`: configured folder, ``$MP3AP_TOOLS_DIR``, cache, repo checkout, else downloaded on first
use). Windows only for now.
"""

from __future__ import annotations

import dataclasses
import os
import platform
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from . import seed_id as seed_id_lib
from . import tools as tools_lib
from .patch_data import PatchData
from .tools import TOOLS_ENV, PatchToolError

ProgressCallback = Callable[[str], None]

SUPPORTED_GAME_IDS = ("RM3P01", "RM3E01")
UNTESTED_GAME_IDS = ("RM3J01",)

# Same PAKs as Randovania's prime3 exporter. Deflicker is a separate DOL patch.
MP3_UPDATE_PAKS = (
    "FrontEnd", "InGameAudio", "NoARAM", "Metroid1", "Metroid3", "Metroid4", "Metroid5", "Metroid6", "Metroid7",
    "UniverseArea",
)

RANDOMIZE_ELEMENTS = (
    "FrontEnd.pak",
    "Logbook.pak",
    "Metroid1.pak",
    "Metroid3.pak",
    "Metroid4.pak",
    "Metroid5.pak",
    "Metroid6.pak",
    "Metroid7.pak",
    "Metroid8.pak",
    "MiscData.pak",
    "UniverseArea.pak",
    "Worlds.pak",
    "Standard.ntwk",
)
DUMMY_ATTRACTS = ("attract01.thp", "Attract02.thp")

__all__ = ["TOOLS_ENV", "PatchToolError"]  # re-exported, they used to live here

# Windows status codes of a helper that could not start (nodtool needs the Microsoft Visual C++ 2015-2022 runtime).
_MISSING_DLL_CODES = (0xC0000135, 0xC0000135 - (1 << 32), 0xC000007B, 0xC000007B - (1 << 32))
VC_REDIST_HINT = (
    "The program could not start because a DLL is missing. Install the Microsoft Visual C++ 2015-2022 "
    "Redistributable (x64 and x86): https://aka.ms/vs/17/release/vc_redist.x64.exe and "
    "https://aka.ms/vs/17/release/vc_redist.x86.exe"
)


def default_tools_dir() -> Path:
    """Helper folder without downloading: ``$MP3AP_TOOLS_DIR``, cache, else the repo checkout."""
    try:
        return tools_lib.find_tools(allow_download=False)
    except PatchToolError:
        return tools_lib.checkout_tools_dir()


@dataclasses.dataclass(frozen=True)
class Toolchain:
    randomizer: Path
    nodtool: Path
    wit: Path
    dummy_attract_dir: Path

    @classmethod
    def from_dir(cls, tools_dir: Path) -> Toolchain:
        if platform.system() != "Windows":
            raise PatchToolError("the patch tool currently runs on Windows only (helper programs are .exe)")
        tools_dir = Path(tools_dir)
        toolchain = cls(
            randomizer=tools_dir / "MP3Randomizer.exe",
            nodtool=tools_dir / "nodtool" / "nodtool.exe",
            wit=tools_dir / "wit" / "bin" / "wit.exe",
            dummy_attract_dir=tools_dir / "dummy_attract",
        )
        required = [
            toolchain.randomizer,
            tools_dir / "lzokay" / "lzokay.dll",
            toolchain.nodtool,
            toolchain.wit,
            *(toolchain.dummy_attract_dir / name for name in DUMMY_ATTRACTS),
        ]
        if missing := [str(path) for path in required if not path.is_file()]:
            raise PatchToolError(f"missing helper files in {tools_dir}: {missing}")
        return toolchain


def run_tool(command: list[str]) -> str:
    """Run a helper; on failure raise with its output (both streams, the helpers are inconsistent)."""
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, errors="replace")
    except subprocess.CalledProcessError as error:
        output = "\n".join(part.strip() for part in (error.stdout, error.stderr) if part and part.strip())
        if error.returncode in _MISSING_DLL_CODES:
            output = f"{output}\n{VC_REDIST_HINT}".strip()
        raise PatchToolError(
            f"{Path(command[0]).name} failed (exit code {error.returncode}): {command}\n{output[-12000:]}"
        ) from error
    return result.stdout


def read_game_id(iso: Path) -> str:
    """Game ID = first 6 bytes of the (unencrypted) disc header."""
    with Path(iso).open("rb") as file:
        raw = file.read(6)
    return raw.decode("ascii", errors="replace")


def check_input_game_id(iso: Path, progress: ProgressCallback) -> str:
    game_id = read_game_id(iso)
    if game_id in SUPPORTED_GAME_IDS:
        return game_id
    if game_id in UNTESTED_GAME_IDS:
        progress(f"Warning: {game_id} is untested with the AP patch tool (supported: RM3P01 and RM3E01)")
        return game_id
    raise PatchToolError(
        f"{iso}: game ID {game_id!r} is not Metroid Prime 3: Corruption (Wii standalone RM3P01/RM3E01/RM3J01). "
        "Metroid Prime Trilogy is not supported."
    )


def randomizer_command(toolchain: Toolchain, patch: PatchData, input_path: Path, output_path: Path) -> list[str]:
    """MP3Randomizer command line, as ``game_exporter._build_randomizer_command`` plus ``--ap-mode``."""
    data = patch.randomizer_patch_data()
    return [
        str(toolchain.randomizer),
        "--input-path",
        str(input_path) + os.sep,
        "--output-path",
        str(output_path) + os.sep,
        "--layout",
        data["seed"],
        "--starting-items",
        *data["starting_items"].split(),
        "--starting-location",
        *data["starting_location"].split(),
        "--hyper-hints",
        "--fast-flying",
        "--ap-mode",
    ]


def wit_copy_command(toolchain: Toolchain, data_dir: Path, out: Path) -> list[str]:
    # Same flags as game_exporter._build_wit_command for ISO output.
    return [str(toolchain.wit), "COPY", "-I", "-z", "--trunc", "--auto-split", "--overwrite", str(data_dir), str(out)]


def _optional_patches(tools_dir: Path, data_dir: Path, mp3_update: bool, disable_deflicker: bool) -> list[list[str]]:
    targets = []
    if disable_deflicker:
        targets.append((data_dir / "sys" / "main.dol", "main.hdiff"))
    if mp3_update:
        targets.extend((data_dir / "files" / f"{name}.pak", f"{name}.hdiff") for name in MP3_UPDATE_PAKS)
    if not targets:
        return []

    hpatchz = tools_dir / "hpatchz.exe"
    patches = [(target, tools_dir / "MP3Update" / diff) for target, diff in targets]
    if missing := [path for path in (hpatchz, *(diff for _, diff in patches)) if not path.is_file()]:
        names = ", ".join(str(path.relative_to(tools_dir)) for path in missing)
        raise PatchToolError(f"missing optional NTSC-U patch files in {tools_dir}: {names}. "
                             "Use --tools with a folder that contains MP3Update and hpatchz.")
    return [[str(hpatchz), "-f", str(target), str(diff), str(target)] for target, diff in patches]


def read_seed_id_from_iso(
    iso: Path, tools_dir: Path | None = None, *, allow_download: bool = False, progress: ProgressCallback = print
) -> tuple[seed_id_lib.DolVersion, bytes | None]:
    """Extract only ``sys/main.dol`` from a disc image with wit and read its seed ID.

    Without ``tools_dir`` the tools are looked up (:func:`.tools.find_tools`); downloaded only if ``allow_download``.
    """
    if not tools_dir:
        tools_dir = tools_lib.find_tools(allow_download=allow_download, progress=progress)
    toolchain = Toolchain.from_dir(tools_dir)
    with tempfile.TemporaryDirectory(prefix="mp3ap_dol_") as temp:
        target = Path(temp) / "x"
        run_tool([
            str(toolchain.wit), "EXTRACT", str(iso), str(target),
            "--psel", "data", "--pmode", "none", "--files", "+sys/main.dol", "--files", "-*", "-q",
        ])  # fmt: skip
        dol = target / "sys" / "main.dol"
        if not dol.is_file():
            raise PatchToolError(f"{iso}: wit did not extract sys/main.dol")
        return seed_id_lib.read_seed_id_from_dol_file(dol)


@dataclasses.dataclass(frozen=True)
class PatchResult:
    output: Path
    game_id: str
    dol_version: str
    seed_id: bytes
    layout: str


def patch_iso(
    patch: PatchData,
    iso: Path,
    out: Path,
    tools_dir: Path | None = None,
    temp_dir: Path | None = None,
    progress: ProgressCallback = print,
    verify: bool = True,
    *,
    mp3_update: bool = False,
    disable_deflicker: bool = False,
) -> PatchResult:
    iso, out = Path(iso), Path(out)
    if not iso.is_file():
        raise PatchToolError(f"input ISO not found: {iso}")
    if iso.resolve() == out.resolve():
        raise PatchToolError("output must not overwrite the input ISO")
    if not out.parent.is_dir():
        raise PatchToolError(f"output folder does not exist: {out.parent}")
    game_id = check_input_game_id(iso, progress)
    if game_id != "RM3E01" and (mp3_update or disable_deflicker):
        raise PatchToolError("MP3Update and Disable Deflicker require an NTSC-U RM3E01 ISO")
    # Before extracting: may download the tools ZIP on first use (progress goes to the T23 window).
    tools_dir = Path(tools_dir or tools_lib.find_tools(progress=progress))
    toolchain = Toolchain.from_dir(tools_dir)

    # Fresh folders per run (like the exporter); a failed run leaves nothing behind.
    work = Path(tempfile.mkdtemp(prefix="mp3ap_", dir=temp_dir))
    try:
        extract = work / "extract"
        paks = work / "paks"
        extract.mkdir()
        paks.mkdir()
        files = extract / "DATA" / "files"
        optional_patches = _optional_patches(tools_dir, extract / "DATA", mp3_update, disable_deflicker)

        progress("[1/6] Extracting ISO...")
        run_tool([str(toolchain.nodtool), "extract", str(iso), str(extract)])
        if not files.is_dir() or not (extract / "DATA" / "sys" / "main.dol").is_file():
            raise PatchToolError(f"extraction did not produce DATA/files and DATA/sys/main.dol in {extract}")

        progress("[2/6] Removing attract videos...")
        for name in DUMMY_ATTRACTS:
            shutil.copy(toolchain.dummy_attract_dir / name, files / "Video" / "FrontEnd" / name)

        if optional_patches:
            progress("Applying optional NTSC-U patches...")
            for command in optional_patches:
                run_tool(command)

        progress("[3/6] Copying paks...")
        for name in RANDOMIZE_ELEMENTS:
            shutil.copy(files / name, paks / name)

        progress("[4/6] Randomizing paks (MP3Randomizer --ap-mode)...")
        run_tool(randomizer_command(toolchain, patch, paks, files))

        progress("[5/6] Writing seed ID into main.dol...")
        version = seed_id_lib.write_seed_id_to_dol_file(extract / "DATA" / "sys" / "main.dol", patch.seed_id)
        if version.game_id != game_id:
            raise PatchToolError(f"main.dol is {version.description}, but the disc is {game_id}")

        progress("[6/6] Building ISO...")
        run_tool(wit_copy_command(toolchain, extract / "DATA", out))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if verify:
        out_game_id = read_game_id(out)
        if out_game_id != game_id:
            raise PatchToolError(f"output game ID {out_game_id!r} != input {game_id!r}")
        _, read_back = read_seed_id_from_iso(out, tools_dir)
        if read_back != patch.seed_id:
            raise PatchToolError(f"seed ID in output DOL is {read_back!r}, expected {patch.seed_id.hex()}")

    return PatchResult(
        output=out,
        game_id=game_id,
        dol_version=version.description,
        seed_id=patch.seed_id,
        layout=patch.layout_string(),
    )
