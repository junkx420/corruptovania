Metroid Prime 3: Corruption for Archipelago - patch tools (Windows)

You normally do not need to do anything with this ZIP: the Metroid Prime 3 patch tool downloads it by itself the
first time you open an .apmp3 file in the Archipelago Launcher.

Offline install, choose one:
- Put this ZIP file (not extracted) into the folder "metroidprime3_tools" inside your Archipelago folder (create it
  if needed) and open the .apmp3 again. The patch tool checks the SHA-256 and extracts it there.
- Or extract it to any folder and set "tools_folder" under "metroidprime3_options" in Archipelago's host.yaml to
  that folder.

Requirement: the Microsoft Visual C++ 2015-2022 Redistributable (nodtool needs it; Dolphin needs it too).

For NTSC-U discs (RM3E01), Open Patch applies MP3Update and Deflicker by default. Set mp3update: false under
metroidprime3_options in host.yaml to skip both.

Contents and licences: THIRD-PARTY-NOTICES.txt and the folder "licenses".
Project: https://github.com/junkx420/Prime3AP
