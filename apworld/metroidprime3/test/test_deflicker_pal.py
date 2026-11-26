"""Tests for the standalone PAL Deflicker DOL patch (T37a)."""

import os
from pathlib import Path

import pytest

from ..patcher.deflicker_pal import apply_deflicker

PAL_OFFSETS = (0x5A46EA, 0x5A4762, 0x5A479E, 0x5A47DA)
ORIGINAL = bytes.fromhex("08 08 0A 0C 0A 08 08")
PATCHED = bytes.fromhex("00 00 15 16 15 00 00")


@pytest.fixture
def main_dol(tmp_path):
    dol = bytearray(b"\xff" * (PAL_OFFSETS[-1] + 0x20))
    for offset in PAL_OFFSETS:
        dol[offset : offset + len(ORIGINAL)] = ORIGINAL
    path = tmp_path / "main.dol"
    path.write_bytes(dol)
    return path


def test_patches_only_the_four_filters(main_dol):
    expected = bytearray(main_dol.read_bytes())
    for offset in PAL_OFFSETS:
        expected[offset : offset + len(PATCHED)] = PATCHED

    apply_deflicker(main_dol)

    assert main_dol.read_bytes() == expected


@pytest.mark.parametrize("problem", ["wrong bytes", "truncated", "partially patched"])
def test_rejects_invalid_dol_before_writing(main_dol, problem):
    dol = bytearray(main_dol.read_bytes())
    offset = PAL_OFFSETS[-1]
    if problem == "wrong bytes":
        dol[offset] = 0xFF
    elif problem == "truncated":
        del dol[offset + 1 :]
    else:
        dol[offset : offset + len(PATCHED)] = PATCHED
    main_dol.write_bytes(dol)

    message = "mix of original and patched filters" if problem == "partially patched" else "0x5A47DA"
    with pytest.raises(ValueError, match=message):
        apply_deflicker(main_dol)

    assert main_dol.read_bytes() == dol


def test_already_patched_is_a_no_op(main_dol, monkeypatch):
    dol = bytearray(main_dol.read_bytes())
    for offset in PAL_OFFSETS:
        dol[offset : offset + len(PATCHED)] = PATCHED
    main_dol.write_bytes(dol)

    def unexpected_write(*args):
        pytest.fail("Already patched DOL should not be written")

    monkeypatch.setattr(Path, "write_bytes", unexpected_write)
    apply_deflicker(main_dol)

    assert main_dol.read_bytes() == dol


def test_real_pal_extract(tmp_path):
    if not (root := os.environ.get("MP3_PAL_EXTRACTED")):
        pytest.skip("MP3_PAL_EXTRACTED not set (path to the extracted PAL ISO)")
    source = Path(root) / "DATA" / "sys" / "main.dol"
    original = source.read_bytes()
    local_dol = tmp_path / "main.dol"
    local_dol.write_bytes(original)
    expected = bytearray(original)
    for offset in PAL_OFFSETS:
        assert expected[offset : offset + len(ORIGINAL)] == ORIGINAL
        expected[offset : offset + len(PATCHED)] = PATCHED

    apply_deflicker(local_dol)

    assert local_dol.read_bytes() == expected
