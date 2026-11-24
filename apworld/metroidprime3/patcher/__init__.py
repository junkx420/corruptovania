"""Patch tool for Metroid Prime 3 Archipelago seeds (T05a, docs/AP_PATCH_TOOL.md).

Stdlib only, no Randovania and no Archipelago import, so it also runs outside Archipelago.

- :mod:`.layout`: copy of Randovania's letter table and checksum (layout string for MP3Randomizer)
- :mod:`.patch_data`: the AP patch data format (JSON) and :func:`build_patch_data` for T05b
- :mod:`.seed_id`: seed ID in the DOL build info (write here, read in the client, T18)
- :mod:`.build`: original ISO + patch data -> patched ISO
"""

from .layout import AP_ITEM
from .patch_data import PatchData, PatchDataError, build_patch_data
from .seed_id import DOL_VERSIONS, make_seed_id, read_seed_id, seed_id_from_build_string

__all__ = [
    "AP_ITEM",
    "DOL_VERSIONS",
    "PatchData",
    "PatchDataError",
    "build_patch_data",
    "make_seed_id",
    "read_seed_id",
    "seed_id_from_build_string",
]
