"""Regional patch options in Open Patch and the standalone CLI."""

import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
import settings

from worlds import metroidprime3

from .. import open_patch
from ..patcher import build, cli, patch_data, seed_id, tools
from ..settings import MP3Settings

PAL_FILTER_OFFSETS = (0x5A46EA, 0x5A4762, 0x5A479E, 0x5A47DA)


@pytest.fixture
def open_patch_build(tmp_path, monkeypatch):
    original = tmp_path / "original.iso"
    container = tmp_path / "seed.apmp3"
    tool_folder = tmp_path / "tools"
    for name in (*tools.REQUIRED_FILES, "hpatchz.exe", "MP3Update/main.hdiff",
                 *(f"MP3Update/{name}.hdiff" for name in build.MP3_UPDATE_PAKS)):
        helper = tool_folder / name
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.touch()

    options = MP3Settings()
    options.update({"iso_file": str(original), "tools_folder": str(tool_folder)})
    data = patch_data.load(Path(build.__file__).with_name("example_patch.json"))
    monkeypatch.setattr(metroidprime3, "MP3World", SimpleNamespace(settings=options))
    monkeypatch.setattr(settings, "get_settings", lambda: SimpleNamespace(changed=False))
    monkeypatch.setattr(patch_data, "read_container", lambda _: (data, {}))
    monkeypatch.setattr(build.platform, "system", lambda: "Windows")
    monkeypatch.setattr(build.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(
        build, "read_seed_id_from_iso", lambda iso, _: seed_id.read_seed_id(iso.read_bytes()[6:518])
    )
    commands = []
    steps = []
    monkeypatch.setattr(open_patch, "_patch_with_window", lambda patch: patch(steps.append))

    def run_tool(command):
        commands.append(command)
        program = Path(command[0]).name
        game_id = build.read_game_id(original)
        if program == "nodtool.exe":
            extract = Path(command[-1]) / "DATA"
            files = extract / "files"
            (files / "Video" / "FrontEnd").mkdir(parents=True)
            for name in {*build.RANDOMIZE_ELEMENTS, *(f"{name}.pak" for name in build.MP3_UPDATE_PAKS)}:
                (files / name).write_bytes(name.encode())
            version = seed_id.version_for_game_id(game_id)
            (extract / "sys").mkdir()
            dol = bytearray(PAL_FILTER_OFFSETS[-1] + 7 if game_id == "RM3P01" else 512)
            for offset, value in ((0x00, 256), (0x48, version.build_string_address), (0x90, 256)):
                struct.pack_into(">I", dol, offset, value)
            dol[256 : 256 + len(version.build_string)] = version.build_string
            if game_id == "RM3P01":
                for offset in PAL_FILTER_OFFSETS:
                    dol[offset : offset + 7] = bytes.fromhex("08 08 0A 0C 0A 08 08")
            (extract / "sys" / "main.dol").write_bytes(dol)
        elif program == "hpatchz.exe":
            target = Path(command[2])
            target.write_bytes(target.read_bytes()[:-1] + b"!")
        elif program == "wit.exe":
            extract = Path(command[-2])
            paks = b"".join((extract / "files" / f"{name}.pak").read_bytes() for name in build.MP3_UPDATE_PAKS)
            Path(command[-1]).write_bytes(game_id.encode() + (extract / "sys" / "main.dol").read_bytes() + paks)

    monkeypatch.setattr(build, "run_tool", run_tool)
    return SimpleNamespace(original=original, container=container, tool_folder=tool_folder, options=options,
                           commands=commands, steps=steps)


@pytest.mark.parametrize("enabled", [None, True, False])
def test_ntsc_open_patch_applies_both_unless_disabled(open_patch_build, enabled):
    test = open_patch_build
    test.original.write_bytes(b"RM3E01")
    if enabled is not None:
        test.options.update({"mp3update": enabled})

    output, _ = open_patch.make_iso(test.container)

    patches = [Path(cmd[3]).name for cmd in test.commands if Path(cmd[0]).name == "hpatchz.exe"]
    if enabled is False:
        assert patches == []
        assert test.steps[2] == "[3/6] Copying paks..."
    else:
        assert patches == ["main.hdiff", *(f"{name}.hdiff" for name in build.MP3_UPDATE_PAKS)]
        assert test.steps[2] == "[3/7] Applying MP3Update and Deflicker..."
        assert test.steps[-1] == "[7/7] Building ISO..."

    first_build = output.read_bytes()
    test.commands.clear()
    open_patch.make_iso(test.container)
    assert test.commands == []

    test.options.update({"mp3update": enabled is False})
    open_patch.make_iso(test.container)
    assert test.commands
    assert output.read_bytes() != first_build


def test_pal_open_patch_only_changes_the_four_filters(open_patch_build):
    test = open_patch_build
    test.original.write_bytes(b"RM3P01")
    (test.tool_folder / "hpatchz.exe").unlink()
    (test.tool_folder / "MP3Update" / "main.hdiff").unlink()
    output, _ = open_patch.make_iso(test.container)
    pal_default = output.read_bytes()
    assert test.steps[2] == "[3/7] Applying Deflicker..."
    assert test.steps[-1] == "[7/7] Building ISO..."

    test.commands.clear()
    open_patch.make_iso(test.container)
    assert not test.commands

    test.steps.clear()
    test.options.update({"mp3update": False})
    open_patch.make_iso(test.container)
    assert test.steps[2] == "[3/6] Copying paks..."
    assert test.steps[-1] == "[6/6] Building ISO..."
    expected = bytearray(output.read_bytes())
    for offset in PAL_FILTER_OFFSETS:
        start = 6 + offset  # Disc header prepended by the fake ISO builder.
        assert expected[start : start + 7] == bytes.fromhex("08 08 0A 0C 0A 08 08")
        expected[start : start + 7] = bytes.fromhex("00 00 15 16 15 00 00")
    assert pal_default == expected
    assert all(Path(cmd[0]).name != "hpatchz.exe" for cmd in test.commands)

    test.options.update({"mp3update": True})
    open_patch.make_iso(test.container)
    assert output.read_bytes() == pal_default

    output.with_suffix(".iso.mp3update").unlink()  # An ISO built before PAL stamps were introduced.
    test.commands.clear()
    open_patch.make_iso(test.container)
    assert test.commands
    assert output.read_bytes() == pal_default


@pytest.mark.parametrize("flag, enabled", [("--disable-deflicker", True), ("--no-mp3-update", False)])
def test_pal_cli_patch_flags(open_patch_build, flag, enabled):
    test = open_patch_build
    test.original.write_bytes(b"RM3P01")
    example = Path(build.__file__).with_name("example_patch.json")
    output = test.container.with_suffix(".iso")
    assert cli.main(["--patch", str(example), "--iso", str(test.original), "--out", str(output),
                     "--tools", str(test.tool_folder), flag]) == 0
    expected = bytes.fromhex("00 00 15 16 15 00 00" if enabled else "08 08 0A 0C 0A 08 08")
    contents = output.read_bytes()
    for offset in PAL_FILTER_OFFSETS:
        assert contents[6 + offset : 13 + offset] == expected
    assert all(Path(cmd[0]).name != "hpatchz.exe" for cmd in test.commands)


def test_switching_iso_region_rebuilds_the_same_seed(open_patch_build):
    test = open_patch_build
    test.original.write_bytes(b"RM3P01")
    output, _ = open_patch.make_iso(test.container)
    assert output.read_bytes().startswith(b"RM3P01")

    test.original.write_bytes(b"RM3E01")
    open_patch.make_iso(test.container)
    assert output.read_bytes().startswith(b"RM3E01")
    assert "[3/7] Applying MP3Update and Deflicker..." in test.steps


def test_ntsc_open_patch_lists_missing_files_before_extraction(open_patch_build):
    test = open_patch_build
    test.original.write_bytes(b"RM3E01")
    (test.tool_folder / "hpatchz.exe").unlink()
    (test.tool_folder / "MP3Update" / "main.hdiff").unlink()
    with pytest.raises(build.PatchToolError, match="Missing NTSC-U MP3Update/Deflicker files") as error:
        open_patch.make_iso(test.container)

    message = str(error.value)
    assert "hpatchz.exe" in message and "main.hdiff" in message
    assert "metroidprime3_options.tools_folder" in message and "metroidprime3_options.mp3update" in message
    assert test.commands == []
