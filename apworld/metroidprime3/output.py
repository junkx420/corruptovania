"""Patch file ``.apmp3`` (T05b): one per MP3 slot, written by ``MP3World.generate_output``.

Container choice (Archipelago 0.6.8, ``worlds/Files.py``): :class:`MP3Container` is an ``APPatch``
(= ``APPlayerContainer`` with ``procedure: "custom"``), like The Wind Waker's ``.aptww`` (an ``APPlayerContainer``).
``APProcedurePatch`` does not fit: it applies byte procedures to the base file in memory (``get_source_data`` reads
the whole source), while MP3 needs a 4.7 GB ISO and external tools (nodtool, MP3Randomizer, wit). The patch is applied
by our own patch tool (``patcher/``), started from the launcher (``open_patch.py``).

Content: Archipelago's ``archipelago.json`` (game, player, player_name, server, patch_file_ending, ...) plus
``patch_data.json`` = AP patch data v1 (docs/AP_PATCH_TOOL.md 2). File and member names come from
``patcher.patch_data`` so that the patch tool (stdlib only) reads exactly what is written here.
"""

from __future__ import annotations

import json
import logging
import os
import zipfile
from typing import TYPE_CHECKING, Any

from worlds.Files import APPatch

from .items import BASE_ID, GAME_NAME
from .patcher import layout, patch_data

if TYPE_CHECKING:
    from BaseClasses import MultiWorld

logger = logging.getLogger("MetroidPrime3")


class MP3Container(APPatch):
    game = GAME_NAME
    patch_file_ending = patch_data.CONTAINER_FILE_ENDING

    def __init__(self, *args: Any, data: patch_data.PatchData | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.data = data

    def write_contents(self, opened_zipfile: zipfile.ZipFile) -> None:
        super().write_contents(opened_zipfile)
        if self.data is None:
            raise ValueError("MP3Container needs patch data to be written")
        opened_zipfile.writestr(patch_data.CONTAINER_MEMBER,
                                json.dumps(self.data.to_json(), indent=2, ensure_ascii=False) + "\n")

    def read_contents(self, opened_zipfile: zipfile.ZipFile) -> dict[str, Any]:
        manifest = super().read_contents(opened_zipfile)
        self.data = patch_data.from_json(json.loads(opened_zipfile.read(patch_data.CONTAINER_MEMBER)))
        return manifest


def displayed_pickups(multiworld: MultiWorld, player: int) -> dict[int, str]:
    """Pickup index 1-99 -> displayed item name (SPEC E14).

    Own item -> its name; item of another world (also item-link groups) -> ``Archipelago Item``. An own item the
    patcher cannot show (only possible via plando of a starting item such as Power Beam) also becomes
    ``Archipelago Item`` with a warning; the client gives every item from the server anyway (E10).
    """
    pickups: dict[int, str] = {}
    for location in multiworld.get_locations(player):
        if location.address is None:
            continue  # event location
        index = location.address - BASE_ID
        item = location.item
        name = layout.AP_ITEM
        if item is not None and item.player == player and item.game == GAME_NAME:
            if item.name in layout.DISPLAYABLE_ITEMS:
                name = item.name
            else:
                logger.warning("Metroid Prime 3 (player %d): own item %r at pickup %d cannot be shown, "
                               "showing %r", player, item.name, index, layout.AP_ITEM)
        pickups[index] = name
    return pickups


def build_patch_data(multiworld: MultiWorld, player: int) -> patch_data.PatchData:
    """AP patch data v1 of one slot. Seed ID = ``patcher.seed_id.make_seed_id`` (via ``build_patch_data``)."""
    return patch_data.build_patch_data(
        seed_name=multiworld.seed_name,
        slot=player,
        player_name=multiworld.player_name[player],
        pickups=displayed_pickups(multiworld, player),
        # T31: the slot's starting items (E23); removed ones are not in the game at the start
        starting_items=patch_data.starting_items_string(multiworld.worlds[player].starting_item_names),
    )


def write_patch_file(multiworld: MultiWorld, player: int, output_directory: str) -> str:
    """Write ``<out_file_name_base>.apmp3`` into the output directory; returns its path."""
    path = os.path.join(output_directory,
                        f"{multiworld.get_out_file_name_base(player)}{MP3Container.patch_file_ending}")
    container = MP3Container(path=path, player=player, player_name=multiworld.player_name[player],
                             data=build_patch_data(multiworld, player))
    container.write()
    return path
