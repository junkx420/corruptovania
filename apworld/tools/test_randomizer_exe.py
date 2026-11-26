"""Run the shipped Windows patcher against private game extracts."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from savw_parser import Pak


REPO = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(sys.platform != "win32", reason="requires the Windows MP3Randomizer.exe")
@pytest.mark.parametrize(("extract_var", "game_id"), [
    ("MP3_PAL_EXTRACTED", b"RM3P01"),
    ("MP3_NTSC_EXTRACTED", b"RM3E01"),
])
def test_removed_starting_items_patch_as_own_pickups(extract_var, game_id, tmp_path, monkeypatch):
    if not (extract := os.environ.get(extract_var)):
        pytest.skip(f"{extract_var} not set")
    data_dir = Path(extract) / "DATA"
    assert (data_dir / "sys" / "boot.bin").read_bytes()[:6] == game_id

    monkeypatch.syspath_prepend(str(REPO / "apworld" / "metroidprime3"))
    from patcher import build, patch_data

    items = ("Morph Ball Bombs", "Charge Beam", "Space Jump Boots", "Morph Ball")
    placements = {
        "Metroid1.pak": (4, 5, 6, 11),
        "Metroid3.pak": (20, 25, 26, 29),
    }
    pickups = dict.fromkeys(range(1, 100), "Archipelago Item")
    for locations in placements.values():
        pickups.update(zip(locations, items, strict=True))
    data = patch_data.build_patch_data(
        "T40OwnPickups", 1, "Samus", pickups,
        starting_items=patch_data.starting_items_string({"Power Beam", "Combat Visor", "Scan Visor"}),
    )
    patch_path = tmp_path / "patch.json"
    patch_data.dump(data, patch_path)

    staged = tmp_path / "paks"
    output = tmp_path / "output"
    staged.mkdir()
    output.mkdir()
    for filename in build.RANDOMIZE_ELEMENTS:
        shutil.copyfile(data_dir / "files" / filename, staged / filename)
    shutil.copyfile(staged / "Standard.ntwk", output / "Standard.ntwk")
    tools = build.Toolchain.from_dir(REPO / "randovania" / "data" / "gollop_mp3_patcher")
    command = build.randomizer_command(tools, patch_data.load(patch_path), staged, output)
    build.run_tool(command)

    expected = {
        0x5EC0A71D941A7307: "SCAN",  # Morph Ball Bombs
        0x252BB5F55E8B1EF6: "SCAN",  # Charge Beam
        0x5AF3172B47063541: "SCAN",  # Space Jump Boots
        0xE1B1C984765407DB: "SCAN",  # Morph Ball
        0xF0C94C57DF6C679E: "CHAR",  # Morph Ball Bombs, animated pickup
        0xF0E00E2A0B4E39AE: "STRG",  # Morph Ball Bombs scan text
        0x8535E6856636FCBE: "TXTR",
        0x1153AC25599D7FAB: "TXTR",
        0x7A474E0EBC7A47D4: "TXTR",
    }
    for filename in placements:
        pak = Pak(str(output / filename))
        for asset, kind in expected.items():
            assert asset in pak.resources, f"{filename} is missing {kind} {asset:016X}"
            assert pak.resources[asset].type == kind
