"""Command line: ``python -m worlds.metroidprime3.patcher --patch <x.apmp3|x.json> --iso <orig.iso> --out <x.iso>``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import build, patch_data, seed_id, tools


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m worlds.metroidprime3.patcher",
        description="Metroid Prime 3 Archipelago patch tool (PAL RM3P01, NTSC-U RM3E01).",
        epilog="NTSC-U defaults to both MP3Update and Deflicker. Use the two patch flags to select either or both.",
    )
    parser.add_argument("--patch", type=Path,
                        help="AP patch data: .apmp3 from Archipelago or JSON (docs/AP_PATCH_TOOL.md)")
    parser.add_argument("--iso", type=Path, help="original, unmodified ISO (RM3P01 or RM3E01)")
    parser.add_argument("--out", type=Path, help="patched ISO to write (overwritten if it exists)")
    parser.add_argument("--tools", type=Path, default=None, help=f"helper folder (default: ${build.TOOLS_ENV}, the "
                        "cache folder, a Corruptovania checkout, else download the tools ZIP on first use)")
    parser.add_argument("--tools-cache", type=Path, default=None,
                        help="cache folder for the downloaded tools (default: <Archipelago>/metroidprime3_tools)")
    parser.add_argument("--temp-dir", type=Path, default=None, help="where to extract (needs ~2x ISO size free)")
    parser.add_argument("--no-verify", action="store_true", help="skip reading back game ID and seed ID")
    update = parser.add_mutually_exclusive_group()
    update.add_argument("--no-mp3-update", action="store_true", help="skip both MP3Update and Deflicker")
    update.add_argument("--mp3-update", action="store_true", help="select the MP3Update PAK patches (NTSC-U only)")
    parser.add_argument("--disable-deflicker", action="store_true", help="select the Deflicker DOL patch (NTSC-U only)")
    parser.add_argument("--dry-run", action="store_true", help="only validate --patch and print the MP3Randomizer data")
    parser.add_argument("--read-seed-id", type=Path, metavar="ISO_OR_DOL",
                        help="print the seed ID of a patched ISO or main.dol and exit")
    return parser


def _tools(args: argparse.Namespace) -> Path | None:
    """``--tools`` as given; with ``--tools-cache`` the lookup (and a download) happens here, else in ``build``."""
    if args.tools or not args.tools_cache:
        return args.tools
    return tools.find_tools(cache_dir=args.tools_cache)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    try:
        if args.read_seed_id:
            path: Path = args.read_seed_id
            if path.suffix.lower() == ".dol":
                version, found = seed_id.read_seed_id_from_dol_file(path)
            else:
                version, found = build.read_seed_id_from_iso(path, _tools(args), allow_download=True)
            print(f"{version.description} ({version.game_id}): " + (found.hex() if found else "no seed ID (unpatched)"))
            return 0

        if not args.patch:
            parser.error("--patch is required")
        data = patch_data.load(args.patch)
        if args.dry_run:
            print(json.dumps(data.randomizer_patch_data(), indent=2))
            print(f"seed_id: {data.seed_id.hex()}")
            return 0
        if not args.iso or not args.out:
            parser.error("--iso and --out are required")
        if args.no_mp3_update and args.disable_deflicker:
            parser.error("--no-mp3-update cannot be used with --disable-deflicker")

        result = build.patch_iso(
            data, args.iso, args.out, tools_dir=_tools(args), temp_dir=args.temp_dir, verify=not args.no_verify,
            mp3_update=False if args.no_mp3_update else args.mp3_update or None,
            disable_deflicker=args.disable_deflicker or None,
        )
    except (patch_data.PatchDataError, build.PatchToolError, ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"Done: {result.output}")
    print(f"  game ID   {result.game_id} ({result.dol_version})")
    print(f"  seed ID   {result.seed_id.hex()}" + ("" if args.no_verify else " (read back from the ISO)"))
    print(f"  player    {data.player_name} (slot {data.slot}, seed {data.seed_name})")
    return 0
