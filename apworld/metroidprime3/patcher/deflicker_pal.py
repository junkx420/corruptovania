# PAL adaptation of MP3Update v7.2's Disable Deflicker patch.
# Copyright © 2026 MrMiguel211
# SPDX-License-Identifier: MIT
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the “Software”), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Disable the vertical deflicker filter in the standalone Wii PAL DOL (RM3P01 Rev 0)."""

from pathlib import Path

# Seven-byte GXRenderModeObj.vfilter fields, in DOL file offsets (T35).
_FILTER_OFFSETS = (0x5A46EA, 0x5A4762, 0x5A479E, 0x5A47DA)
_ORIGINAL_FILTER = bytes.fromhex("08 08 0A 0C 0A 08 08")
_PATCHED_FILTER = bytes.fromhex("00 00 15 16 15 00 00")


def apply_deflicker(main_dol: Path) -> None:
    """Patch an extracted main.dol in place, or raise ValueError for unexpected filter data."""
    dol = bytearray(main_dol.read_bytes())
    unpatched_offsets = []
    for offset in _FILTER_OFFSETS:
        current = dol[offset : offset + len(_ORIGINAL_FILTER)]
        if current == _ORIGINAL_FILTER:
            unpatched_offsets.append(offset)
        elif current != _PATCHED_FILTER:
            actual = current.hex(" ").upper() or "end of file"
            raise ValueError(
                f"PAL Deflicker: unexpected filter bytes at DOL offset 0x{offset:06X} "
                f"(found {actual}, expected {_ORIGINAL_FILTER.hex(' ').upper()} "
                f"or {_PATCHED_FILTER.hex(' ').upper()}). Expected a standalone RM3P01 Rev 0 main.dol."
            )

    if not unpatched_offsets:
        return
    if len(unpatched_offsets) != len(_FILTER_OFFSETS):
        raise ValueError("PAL Deflicker: main.dol contains a mix of original and patched filters.")

    for offset in unpatched_offsets:
        dol[offset : offset + len(_PATCHED_FILTER)] = _PATCHED_FILTER
    main_dol.write_bytes(dol)
