"""Open an ``.apmp3`` from the Archipelago launcher (T05b): build the patched ISO, then start the MP3 client.

Flow (docs/AP_APWORLD_DEV.md, "Launcher"): read the container -> original ISO from host.yaml
(``metroidprime3_options.iso_file``; on first use a file dialog asks and the path is saved) -> patch tool
(``patcher.build.patch_iso``) writes ``<name>.iso`` next to the ``.apmp3`` (or into ``output_folder``); if that ISO
already matches this slot's seed and patch settings it is reused -> Metroid Prime 3 Client with ``--connect <server>`` (if the
container names one) and ``--name <player>``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, SimpleQueue

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
    """Configured helper folder if it contains MP3Randomizer.exe, else ``None``: the patcher then looks for the tools
    itself (``$MP3AP_TOOLS_DIR``, ``<Archipelago>/metroidprime3_tools``, repo checkout) and downloads them on first use
    (``patcher.tools.find_tools``; download progress goes to the patch window)."""
    if configured and (Path(configured) / "MP3Randomizer.exe").is_file():
        return Path(configured)
    if configured:
        logger.warning("tools_folder %s has no MP3Randomizer.exe, ignoring it", configured)
    return None


def _update_stamp(out: Path, mp3update: bool) -> str:
    # Also detect an ISO replaced outside Open Patch, such as a CLI rebuild of the same seed.
    stat = out.stat()
    return f"{mp3update} {stat.st_size} {stat.st_mtime_ns}\n"


def is_up_to_date(out: Path, data: patch_data.PatchData, tools: Path | None, iso: Path, mp3update: bool) -> bool:
    if not out.is_file():
        return False
    try:
        version, found = build.read_seed_id_from_iso(out, tools)
        if found != data.seed_id:
            return False
        if iso.exists() and build.read_game_id(iso) != version.game_id:
            return False
        if version.game_id in build.SUPPORTED_GAME_IDS:
            stamp = out.with_suffix(".iso.mp3update")
            return stamp.read_text(encoding="ascii") == _update_stamp(out, mp3update)
    except (build.PatchToolError, ValueError, OSError) as error:
        logger.info("Existing %s not readable (%s), rebuilding", out, error)
        return False
    return True


def _patch_with_window(patch: Callable[[build.ProgressCallback], build.PatchResult]) -> build.PatchResult:
    try:
        from tkinter import TclError, Tk, ttk
    except ImportError as error:
        logger.warning("Patch progress window unavailable: %s", error)
        return patch(logger.info)
    try:
        root = Tk()
    except TclError as error:
        logger.warning("Patch progress window unavailable: %s", error)
        return patch(logger.info)

    messages: SimpleQueue[str] = SimpleQueue()

    def report(message: str) -> None:
        logger.info(message)
        messages.put(message)

    try:
        root.title("Metroid Prime 3 Patch")
        root.resizable(False, False)
        # Keep the window open while the patcher is writing the ISO.
        root.protocol("WM_DELETE_WINDOW", root.bell)
        status = ttk.Label(root, text="Preparing to patch...", width=62, wraplength=440, padding=20)
        status.pack()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(patch, report)

            def refresh() -> None:
                finished = future.done()
                try:
                    while True:
                        status.configure(text=messages.get_nowait())
                except Empty:
                    pass
                if not finished:
                    root.after(50, refresh)
                elif future.exception() is not None:
                    root.quit()
                else:
                    status.configure(text="Done. Starting the Metroid Prime 3 Client...")
                    root.after(1200, root.quit)

            root.after(0, refresh)
            root.mainloop()
            return future.result()
    finally:
        root.destroy()


def make_iso(patch_file: Path, *, gui: bool = True) -> tuple[Path, dict]:
    """Build (or reuse) the patched ISO for ``patch_file``. Returns (ISO path, container manifest)."""
    import settings as ap_settings

    from . import MP3World
    from .settings import raw_value

    data, manifest = patch_data.read_container(patch_file)
    options = MP3World.settings
    no_gui = ap_settings.no_gui
    ap_settings.no_gui = no_gui or not gui
    try:
        iso = Path(options.iso_file)  # opens a file dialog if missing and GUI is enabled
    finally:
        ap_settings.no_gui = no_gui
    if ap_settings.get_settings().changed:
        ap_settings.get_settings().save()  # a launcher subprocess ends without atexit, so save now
    # Group resolves "" to the Archipelago folder, so only use the resolved path if host.yaml names one.
    tools = tools_dir(str(options.tools_folder) if raw_value(options, "tools_folder") else "")
    out = output_path(patch_file, raw_value(options, "output_folder"))
    mp3update = getattr(options, "mp3update", True)
    if not isinstance(mp3update, bool):
        raise build.PatchToolError("metroidprime3_options.mp3update in host.yaml must be true or false.")

    if is_up_to_date(out, data, tools, iso, mp3update):
        logger.info("%s already has seed ID %s, not patching again", out, data.seed_id.hex())
        return out, manifest
    logger.info("Patching %s -> %s (player %s, slot %d, seed %s)", iso, out, data.player_name, data.slot,
                data.seed_name)

    def patch(progress: build.ProgressCallback) -> build.PatchResult:
        if mp3update:
            return build.patch_iso(data, iso, out, tools_dir=tools, progress=progress)
        return build.patch_iso(data, iso, out, tools_dir=tools, progress=progress, mp3_update=False)

    result = _patch_with_window(patch) if gui else patch(logger.info)
    if result.game_id in build.SUPPORTED_GAME_IDS:
        try:
            out.with_suffix(".iso.mp3update").write_text(_update_stamp(out, mp3update), encoding="ascii", newline="\n")
        except OSError as error:
            logger.warning("Could not save the MP3Update/Deflicker setting for %s: %s", out, error)
    logger.info("Done: %s, game ID %s, seed ID %s", result.output, result.game_id, result.seed_id.hex())
    return out, manifest


def patch_and_launch(*args: str) -> None:
    """Launcher entry for ``.apmp3`` files (runs in the launcher's subprocess when the GUI is open)."""
    import Utils

    Utils.init_logging("MetroidPrime3Patch", exception_logger="Patch")
    patch_file, rest = split_args(args)
    if patch_file is None:
        raise ValueError("no .apmp3 file given")
    gui = Utils.gui_enabled and "--nogui" not in rest
    try:
        out, manifest = make_iso(Path(patch_file), gui=gui)
    except Exception as error:
        logger.exception("Building the ISO from %s failed", patch_file)
        if gui:
            try:
                Utils.messagebox("Metroid Prime 3 – patch failed", f"{patch_file}:\n{error}", error=True)
            except Exception:
                logger.exception("Patch error dialog unavailable")
        return
    logger.info("Load %s in Dolphin/PrimeHack. Starting Metroid Prime 3 Client.", out)

    from .client import launch as client_main
    client_main(*client_args(manifest, rest))
