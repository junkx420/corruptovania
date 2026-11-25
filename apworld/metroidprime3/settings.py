"""host.yaml settings of the World (section ``metroidprime3_options``), used when opening an ``.apmp3`` (T05b).

``import settings`` below is Archipelago's top-level ``settings`` module (absolute import), not this file.
"""

from __future__ import annotations

import settings

ACCEPTED_GAME_IDS = ("RM3P01", "RM3E01", "RM3J01")  # patcher/build.py: PAL tested, NTSC-U/J with a warning


class MP3Settings(settings.Group):
    class IsoFile(settings.UserFilePath):
        """Unmodified Metroid Prime 3: Corruption disc image (Wii PAL RM3P01). Opening an .apmp3 builds the
        patched ISO from it. Asked for on the first .apmp3 and remembered here."""

        description = "Metroid Prime 3: Corruption ISO (Wii PAL RM3P01, unmodified)"

        @classmethod
        def validate(cls, path: str) -> None:
            # Only the game ID (first 6 bytes). A hash over 4.7 GB would run on every access of the setting.
            with open(path, "rb") as file:
                game_id = file.read(6).decode("ascii", errors="replace")
            if game_id not in ACCEPTED_GAME_IDS:
                raise ValueError(f"{path} is not a Metroid Prime 3: Corruption Wii disc image (game ID {game_id!r}, "
                                 f"expected RM3P01)")

    class ToolsFolder(settings.OptionalUserFolderPath):
        """Folder with MP3Randomizer.exe, nodtool, wit and dummy_attract (patch tool helpers). Leave empty: the patch
        tools are downloaded on the first patch into metroidprime3_tools in the Archipelago folder. Set it only for an
        offline install (extracted metroidprime3-tools-win.zip)."""

    class OutputFolder(settings.OptionalUserFolderPath):
        """Where the patched ISO is written. Empty: next to the .apmp3 file."""

    iso_file: IsoFile = IsoFile("Metroid Prime 3 Corruption (PAL).iso")
    tools_folder: ToolsFolder = ToolsFolder("")
    output_folder: OutputFolder = OutputFolder("")
    mp3update: bool = True  # Apply MP3Update and Deflicker to NTSC-U builds.


def raw_value(group: settings.Group, key: str) -> str:
    """The value as written in host.yaml. ``Group`` resolves paths on access, so ``""`` would become the AP folder."""
    return str(object.__getattribute__(group, key))
