"""Regional client addresses and optional NTSC-U patching (T33)."""

import asyncio
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from NetUtils import NetworkItem

from ..client import flag_block, inventory
from ..client.memory import GAME_ID_ADDRESS, ConnectStatus, NotConnected
from ..client.seed_check import SeedStatus
from ..items import item_name_to_id
from ..patcher import build, cli, seed_id
from .fake_memory import FakeMemory
from .test_client import BASE_ID, VALHALLA, location_checks, make_context


@pytest.mark.parametrize("game_id", [b"RM3P01", b"RM3E01"])
def test_client_poll_uses_the_running_region(tmp_path, game_id):
    async def poll():
        memory = FakeMemory(game_id)
        block = memory.place_block(0x80A00000, VALHALLA)
        memory.set_ingame(VALHALLA)
        ctx = make_context(memory, str(tmp_path / "learning.jsonl"))

        await ctx.poll_once()
        assert ctx.dolphin_status == f"Connected to Dolphin, game {game_id.decode()} detected."
        assert ctx.seed_check.result.status is SeedStatus.OK
        assert ctx.game_state.ingame and ctx.game_state.inventory_valid
        assert ctx.current_world == VALHALLA
        assert ctx.finder.get(VALHALLA) == [block]

        memory.set_flag(block, 1)
        memory.set_item_percentage(1)
        ctx.items_received.append(NetworkItem(item_name_to_id["Grapple Lasso"], -1, 1))
        for _ in range(4):
            await ctx.poll_once()
        assert location_checks(ctx) == [BASE_ID + 11]
        assert memory.slot(inventory.GRAPPLE_LASSO) == (1, 1)

    asyncio.run(poll())


def test_switch_between_supported_games_disconnects_before_writing():
    memory = FakeMemory(b"RM3P01")
    assert memory.connect().status is ConnectStatus.CONNECTED
    memory.poke(GAME_ID_ADDRESS, b"RM3E01")
    with pytest.raises(NotConnected, match="game ID changed"):
        memory.write(0x80995B74, b"\0\0\0\1")
    assert not memory.connected and not memory.writes
    assert memory.connect().status is ConnectStatus.CONNECTED
    assert memory.version.dol.game_id == "RM3E01"


def test_ntsc_valhalla_rejects_pal_length_and_ntsc_padding():
    memory = FakeMemory(b"RM3E01")
    assert memory.connect().status is ConnectStatus.CONNECTED
    block = memory.place_block(0x80A00000, VALHALLA)
    finder = flag_block.FlagBlockFinder(memory)
    assert finder.validate(block, VALHALLA)
    memory.set_flag(block, 198)  # This index is in the PAL list but beyond the NTSC-U list.
    assert finder.read_flags(VALHALLA) is None
    savw_object = memory.read_u32(block + flag_block.OFF_SAVW_OBJECT)
    memory.poke_u32(savw_object + flag_block.SAVW_OBJECT_LIST1_COUNT, 212)
    assert not finder.validate(block, VALHALLA)


@pytest.mark.parametrize("game_id", ["RM3P01", "RM3E01"])
def test_supported_disc_ids_have_no_warning(tmp_path, game_id):
    disc = tmp_path / "input.iso"
    disc.write_bytes(game_id.encode("ascii"))
    progress = Mock()
    assert build.check_input_game_id(disc, progress) == game_id
    progress.assert_not_called()


def test_optional_patches_reject_pal_before_tool_lookup(tmp_path, monkeypatch):
    disc = tmp_path / "input.iso"
    disc.write_bytes(b"RM3P01")
    lookup = Mock()
    monkeypatch.setattr(build.tools_lib, "find_tools", lookup)
    with pytest.raises(build.PatchToolError, match="require an NTSC-U RM3E01 ISO"):
        build.patch_iso(Mock(), disc, tmp_path / "output.iso", mp3_update=True)
    lookup.assert_not_called()


def test_optional_diffs_require_only_the_requested_files(tmp_path):
    data = tmp_path / "DATA"
    assert build._optional_patches(tmp_path, data, False, False) == []
    with pytest.raises(build.PatchToolError, match="main.hdiff"):
        build._optional_patches(tmp_path, data, False, True)
    exe = tmp_path / "hpatchz.exe"
    exe.touch()
    diffs = tmp_path / "MP3Update"
    diffs.mkdir()
    main = diffs / "main.hdiff"
    main.touch()
    dol = data / "sys" / "main.dol"
    assert build._optional_patches(tmp_path, data, False, True) == [
        [str(exe), "-f", str(dol), str(main), str(dol)],
    ]
    for name in build.MP3_UPDATE_PAKS:
        (diffs / f"{name}.hdiff").touch()
    paks = build._optional_patches(tmp_path, data, True, False)
    assert len(paks) == 10
    assert all(Path(command[2]).parent == data / "files" and command[2] == command[4] for command in paks)


def test_optional_cli_switches_are_off_by_default():
    defaults = cli._parser().parse_args([])
    assert not defaults.mp3_update and not defaults.disable_deflicker
    enabled = cli._parser().parse_args(["--mp3-update", "--disable-deflicker"])
    assert enabled.mp3_update and enabled.disable_deflicker


def test_seed_id_offset_in_real_ntsc_dol():
    if not (root := os.environ.get("MP3_NTSC_EXTRACTED")):
        pytest.skip("MP3_NTSC_EXTRACTED not set (path to the extracted NTSC-U ISO)")
    original = (Path(root) / "DATA" / "sys" / "main.dol").read_bytes()
    version = seed_id.version_for_game_id("RM3E01")
    assert seed_id.read_seed_id(original) == (version, None)
    assert seed_id.dol_offset_for_address(original, version.seed_id_address) == 0x57E396
    dol = bytearray(original)
    marker = seed_id.make_seed_id("T33", 1)
    assert seed_id.write_seed_id(dol, marker) == version
    assert dol == original[:0x57E396] + marker + original[0x57E3A6:]
    assert seed_id.read_seed_id(dol) == (version, marker)
