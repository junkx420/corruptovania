"""Open an ``.apmp3`` from the Archipelago launcher (T05b): build the patched ISO, then start the MP3 client.

Flow (docs/AP_APWORLD_DEV.md, "Launcher"): read the container -> original ISO from host.yaml
(``metroidprime3_options.iso_file``; on first use a file dialog asks and the path is saved) -> patch tool
(``patcher.build.patch_iso``) writes ``<name>.iso`` next to the ``.apmp3`` (or into ``output_folder``); if that ISO
already carries this slot's seed ID it is reused -> Metroid Prime 3 Client with ``--connect <server>`` (if the
container names one) and ``--name <player>``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .patcher import build, patch_data

logger = logging.getLogger("MetroidPrime3Patch")


def split_args(args: tuple[str, ...]) -> tuple[str | None, list[str]]:
    """First ``.apmp3`` argument and the remaining (client) arguments."""
    patch_file = None
    rest: list[str] = []
    for arg in args:
        if patch_file is None and isinstance(arg, str) and arg.lower().endswith(patch_data.CONTAINER_FILE_ENDING):
            patch_file = arg
        else:
            rest.append(arg)
    return patch_file, rest


def client_args(manifest: dict, rest: list[str]) -> list[str]:
    """Client command line: given arguments first, then server/name from the container unless already given."""
    args = list(rest)
    has_url = any(arg.startswith("archipelago://") for arg in args)
    server = manifest.get("server") or ""
    if server and not has_url and "--connect" not in args:
        args += ["--connect", server]
    if manifest.get("player_name") and not has_url and "--name" not in args:
        args += ["--name", manifest["player_name"]]
    return args


def output_path(patch_file: Path, output_folder: str) -> Path:
    folder = Path(output_folder) if output_folder else patch_file.parent
    return folder / (patch_file.stem + ".iso")


def tools_dir(configured: str) -> Path | None:
    """Configured helper folder if it contains MP3Randomizer.exe, else ``None`` (patcher default)."""
    if configured and (Path(configured) / "MP3Randomizer.exe").is_file():
        return Path(configured)
    return None


def is_up_to_date(out: Path, data: patch_data.PatchData, tools: Path | None) -> bool:
    if not out.is_file():
        return False
    try:
        _, found = build.read_seed_id_from_iso(out, tools)
    except (build.PatchToolError, ValueError, OSError) as error:
        logger.info("Existing %s not readable (%s), rebuilding", out, error)
        return False
    return found == data.seed_id


def make_iso(patch_file: Path) -> tuple[Path, dict]:
    """Build (or reuse) the patched ISO for ``patch_file``. Returns (ISO path, container manifest)."""
    import settings as ap_settings

    from . import MP3World
    from .settings import raw_value

    data, manifest = patch_data.read_container(patch_file)
    options = MP3World.settings
    iso = Path(options.iso_file)  # opens a file dialog if missing; validate() checks the game ID
    if ap_settings.get_settings().changed:
        ap_settings.get_settings().save()  # a launcher subprocess ends without atexit, so save now
    tools = tools_dir(str(options.tools_folder))
    out = output_path(patch_file, raw_value(options, "output_folder"))

    if is_up_to_date(out, data, tools):
        logger.info("%s already has seed ID %s, not patching again", out, data.seed_id.hex())
        return out, manifest
    logger.info("Patching %s -> %s (player %s, slot %d, seed %s)", iso, out, data.player_name, data.slot,
                data.seed_name)
    result = build.patch_iso(data, iso, out, tools_dir=tools, progress=logger.info)
    logger.info("Done: %s, game ID %s, seed ID %s", result.output, result.game_id, result.seed_id.hex())
    return out, manifest


def patch_and_launch(*args: str) -> None:
    """Launcher entry for ``.apmp3`` files (runs in the launcher's subprocess when the GUI is open)."""
    import Utils

    Utils.init_logging("MetroidPrime3Patch", exception_logger="Patch")
    patch_file, rest = split_args(args)
    if patch_file is None:
        raise ValueError("no .apmp3 file given")
    try:
        out, manifest = make_iso(Path(patch_file))
    except Exception as error:  # show every failure; the launcher subprocess has no console
        logger.exception("Building the ISO from %s failed", patch_file)
        Utils.messagebox("Metroid Prime 3 – patch failed", f"{patch_file}:\n{error}", error=True)
        return
    logger.info("Load %s in Dolphin/PrimeHack. Starting Metroid Prime 3 Client.", out)

    from .client import launch as client_main
    client_main(*client_args(manifest, rest))
