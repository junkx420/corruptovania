# AP dev setup: Corruptovania on Windows (T01)

As of 2026-11-23. Tested on Windows 11 Home (x64) with Git Bash and PowerShell 5.1.
Goal: in about 15 minutes from an empty machine to an exported, bootable MP3 ISO.

> **Most important result up front:** testing was done with a **PAL** ISO (`RM3P01`), because only this one
> was available. With the default options (starter preset) the export works for PAL and the ISO
> boots up to Olympus. The optional patches "MP3Update" and "Disable Deflicker" work
> **only with NTSC-U (`RM3E01`)** and fail on PAL (details in section 8).

Contents:

1. Requirements
2. Python venv and requirements
3. .NET 8 SDK and building the patcher `MP3Randomizer`
4. Generating a seed
5. Exporting the ISO
6. Boot test in Dolphin
7. Supported game version (with evidence in the code)
8. Failed steps and error messages
9. Pitfalls and notes for the next tasks

Conventions:

- `REPO` = repo root `corruptovania` (e.g. `C:\Projekte\corruptovania`).
- The original ISO and all outputs are **outside** the repo (`..\mp3.iso`, `..\out\`).
  **Never put an ISO into the repo.**
- All build artifacts go to `build/`, which is ignored via `.gitignore` (line 8).
- Commands are written for Git Bash. Where a PowerShell equivalent is needed, it is given alongside.

---

## 1. Requirements

| Tool | Version (tested) | Installation |
|---|---|---|
| Git | 2.56.0.windows.4 | https://git-scm.com |
| Python | 3.12.10, 64-bit (`py -3.12`) | python.org installer, tick "py launcher" |
| .NET SDK | 8.0.428 | `winget install --id Microsoft.DotNet.SDK.8 -e` |
| Dolphin | 2609b (portable) | https://dolphin-emu.org/download/ (the winget package `DolphinEmulator.Dolphin` is outdated, version 5.0 from 2016) |
| Original ISO | Metroid Prime 3: Corruption, Wii standalone | your own dump (see section 7) |

Check:

```bash
py -0p
```
```
 -V:3.12 *        C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe
```

```bash
"/c/Program Files/dotnet/dotnet.exe" --list-sdks
```
```
8.0.428 [C:\Program Files\dotnet\sdk]
```

> If `dotnet --list-sdks` is empty ("No SDKs were found"): only the runtime is installed.
> Then install the SDK (command in the table above). Before, this machine was in exactly this state
> (only runtimes 8.0.23 and 10.0.14).

Output of the winget installation:
```
Downloading https://download.microsoft.com/download/.../dotnet-sdk-8.0.428-win-x64.exe
Successfully verified installer hash
Starting package install...
Successfully installed
```

In the current Git Bash session `dotnet` is often not in `PATH` yet afterwards. Either open a new terminal or:

```bash
export PATH="/c/Program Files/dotnet:$PATH"
```

## 2. Python venv and requirements

```bash
cd REPO
py -3.12 tools/check_py_version.py
```
```
Using Python 3.12 (64-bit)
```

```bash
py -3.12 -m venv venv
venv/Scripts/python.exe --version
```
```
Python 3.12.10
```

```bash
venv/Scripts/python.exe -m pip install --upgrade -r requirements-setuptools.txt
venv/Scripts/python.exe -m pip install -e ".[gui]" -c requirements.txt
venv/Scripts/python.exe -m pip install -r requirements.txt
```
Output (shortened, end of the 2nd command):
```
Successfully installed PySide6-Essentials-6.8.2.1 ... dolphin-memory-engine-1.3.0 ... nod-1.9.4 ... randovania-1.9.0.dev87 ...
```

**Important:** the third command (`requirements.txt`) is mandatory. Only it installs e.g.
`open-prime-rando==0.15.1`, which the Dolphin connector needs for MP3. Without it:
```
ModuleNotFoundError: No module named 'open_prime_rando'
```

Check:
```bash
venv/Scripts/python.exe -m randovania --version
```
```
Randovania 1.9.0.dev87 from ...\corruptovania\randovania
```

Note: `tools/prepare_virtual_env.bat` does essentially the same, but additionally calls
`pre-commit install` (writes Git hooks). For T01 this was left out on purpose.

## 3. .NET 8 SDK and building the patcher `MP3Randomizer`

The patcher source code is in `tools/prime3_patcher/MP3Randomizer` (`net8.0`, see `MP3Randomizer.csproj`).

**The patcher must be built as x86 (32-bit).** The bundled native library
`randovania/data/gollop_mp3_patcher/lzokay/lzokay.dll` is 32-bit (PE machine `0x14c`), just like the
bundled `MP3Randomizer.exe`. An x64 build crashes at the first compressed area (section 8, F2).
No x86 .NET runtime is installed on the machine, so the patcher is published self-contained.

```bash
cd REPO
export PATH="/c/Program Files/dotnet:$PATH" DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
dotnet publish tools/prime3_patcher/MP3Randomizer/MP3Randomizer.csproj \
  -c Release -r win-x86 --self-contained true \
  --artifacts-path build/mp3r -o build/mp3r/publish
mkdir -p build/mp3r/publish/lzokay
cp randovania/data/gollop_mp3_patcher/lzokay/lzokay.dll build/mp3r/publish/lzokay/
```
```
  Restored ...\tools\prime3_patcher\MP3Randomizer\MP3Randomizer.csproj (in 2.69 sec).
  MP3Randomizer -> ...\build\mp3r\bin\MP3Randomizer\release_win-x86\MP3Randomizer.dll
  MP3Randomizer -> ...\build\mp3r\publish\
```

`--artifacts-path` makes `bin/` and `obj/` end up under `build/` and not as untracked
folders in `tools/prime3_patcher/MP3Randomizer/` (no `.gitignore` applies there).

Unit tests of the patcher:
```bash
dotnet test tools/prime3_patcher/MP3Randomizer.Tests/MP3Randomizer.Tests.csproj --artifacts-path build/mp3r-tests
```
```
Passed!  - Failed:     0, Passed:     2, Skipped:     0, Total:     2, Duration: 2 ms - MP3Randomizer.Tests.dll (net8.0)
```

Quick test:
```bash
build/mp3r/publish/MP3Randomizer.exe --help
```
```
USAGE
MP3Randomizer.exe [FLAGS]

REQUIRED FLAGS
--input-path "INPUT_PATH"           Folder containing the pak files
--output-path "OUTPUT_PATH"         Folder to save the randomized paks to
--layout "LAYOUT"                   The item layout/seed
...
```

### Which patcher is used for the export?

On Windows the exporter does **not** call the self-built patcher, but the checked-in
`randovania/data/gollop_mp3_patcher/MP3Randomizer.exe`
(`randovania/games/prime3/exporter/toolchain.py:82-94`, path in line 86).

Equivalence checked: both patchers were applied with the same seed and the same flags to the 13 input files
of the PAL ISO. Result: **all 13 output files are byte-identical (SHA-256)**:
FrontEnd, Logbook, Metroid1/3/4/5/6/7/8, MiscData, UniverseArea, Worlds, Standard.ntwk.
Logbook.pak and MiscData.pak stay unchanged in the process.

Anyone who wants to use their own build in the exporter for T05 has to put `MP3Randomizer.exe` plus runtime files into
`randovania/data/gollop_mp3_patcher/`. That is a change to checked-in files and belongs in a
task of its own.

## 4. Generating a seed

There is exactly one preset for MP3: `randovania/games/prime3/presets/starter_preset.rdvpreset` ("Starter Preset").

```bash
cd REPO
mkdir -p build/seed
venv/Scripts/python.exe -m randovania layout generate-from-presets \
  --name "prime3/Starter Preset" --seed-number 1000 build/seed/t01.rdvgame
```
```
Permalink: DQUaavDSCSsKDyO7HiYpa-sH
Took 6.873 seconds. Hash: IVG2J7OR
```

Output the patch data (the JSON the exporter passes to the patcher):
```bash
venv/Scripts/python.exe -m randovania layout patcher-data \
  --layout-file build/seed/t01.rdvgame --output build/seed/t01.patcher.json
```
Content (shortened):
```
seed: 00kk44g44xtk944sdk444Cko{4rk^44}...
starting_items: custom 0000000010010000000001100100100000000010000
starting_location: custom c133f919c108bdf9 d8cf355d3e9e3741
random_door_colors: False, random_welding_colors: False
missile_required_mains: True, ship_missile_required_mains: True
phaaze_skip: False, mp3_update: False, disable_deflicker: False
```

In the starter preset `mp3_update` and `disable_deflicker` are off. That is why it also works with PAL.

## 5. Exporting the ISO

```bash
cd REPO
mkdir -p ../out
venv/Scripts/python.exe -m randovania layout export-game \
  --patcher-data build/seed/t01.patcher.json prime3 \
  --input-path "../mp3.iso" --output-path "../out/t01_IVG2J7OR.iso" --output-format iso
```
```
          [5.2274 INFO nod] Success!
[ 10%] Extracting ISO...
[ 20%] Removing attract videos...
[ 50%] Copying Paks...
[ 60%] Randomizing Paks...
[ 70%] Exporting to ISO...

real	0m54.902s
```
Result: `..\out\t01_IVG2J7OR.iso`, 4 519 067 648 bytes. The exporter creates temporary folders under `%TEMP%`
and cleans them up itself (checked). Free space: about 3 × ISO size, i.e. roughly 15 GB.

Check with DolphinTool (see section 6 for Dolphin):
```bash
DolphinTool.exe header -i "..\out\t01_IVG2J7OR.iso"
```
```
Internal Name: Metroid Prime 3: Corruption
Revision: 0
Game ID: RM3P01
Title ID: 00010000524d3350
Region: PAL
Country: Europe
```

Note: the CLI flag `--mp3-update` of `export-game prime3` has no effect. It ends up in
`CorruptionGameExportParams.mp3_update` (`game_exporter.py:29`), but the exporter reads
`patch_data["mp3_update"]` (`game_exporter.py:100`). That comes from the preset
(`corruption_configuration.py:17`, `patch_data_factory.py:50,118`).

## 6. Boot test in Dolphin

Put a portable Dolphin next to the repo (not into the repo):

```bash
cd "REPO/.."
mkdir -p tools/dl tools/dolphin
curl -sSL -o tools/dl/dolphin-2609b-x64.7z https://dl.dolphin-emu.org/releases/2609b/dolphin-2609b-x64.7z
/c/Windows/System32/tar.exe -xf tools/dl/dolphin-2609b-x64.7z -C tools/dolphin
touch tools/dolphin/Dolphin-x64/portable.txt
```

Control via keyboard and mouse. Create this file as `tools/dolphin/Dolphin-x64/User/Config/WiimoteNew.ini`.
MP3 requires a Nunchuk, and the pointer must be bound to the mouse. If the pointer is bound to keys,
it jumps back to the centre when released, and menus cannot be operated that way.

```ini
[Wiimote1]
Device = DInput/0/Keyboard Mouse
Source = 1
Extension = Nunchuk
Buttons/A = F
Buttons/B = SPACE
Buttons/1 = `1`
Buttons/2 = `2`
Buttons/- = Q
Buttons/+ = E
Buttons/Home = H
D-Pad/Up = UP
D-Pad/Down = DOWN
D-Pad/Left = LEFT
D-Pad/Right = RIGHT
IR/Up = `Cursor Y-`
IR/Down = `Cursor Y+`
IR/Left = `Cursor X-`
IR/Right = `Cursor X+`
IR/Auto-Hide = False
Nunchuk/Buttons/C = C
Nunchuk/Buttons/Z = Z
Nunchuk/Stick/Up = W
Nunchuk/Stick/Down = S
Nunchuk/Stick/Left = A
Nunchuk/Stick/Right = D
[Wiimote2]
Source = 0
[Wiimote3]
Source = 0
[Wiimote4]
Source = 0
[BalanceBoard]
Source = 0
```

Optional `User/Config/Dolphin.ini` (analytics prompt off, game in the main window):
```ini
[Analytics]
PermissionAsked = True
Enabled = False
[Interface]
ConfirmStop = False
[Display]
RenderToMain = True
```

Start:
```bash
tools/dolphin/Dolphin-x64/Dolphin.exe -b -e "C:\...\MP3 Archi\out\t01_IVG2J7OR.iso"
```

Sequence and observation (2026-11-23, Dolphin 2609b, JIT64, Direct3D 11, HLE):

1. Window title: `Metroid Prime 3: Corruption (RM3P01)`. The Nintendo/Retro intro plays, skip with A (`F`).
2. Title screen "PRESS (A) TO START" → A.
3. "Game Select": pointer with the mouse on `[ New Game ]` → A, then choose a Mii → A, then `Game Start` → A.
4. "Main Menu" → `[ Play Game ]` → A. "Select Difficulty" → `[ Normal ]` → A.
5. Life support text in cryo sleep, then the game starts on the **G.F.S. Olympus**.
   The HUD is visible (energy 99, "Objective Completed").
6. With `W` (Nunchuk stick) Samus walks forward. **The level is playable.**

Proof screenshot: `..\out\t01_boot_olympus.jpg` (outside the repo).

Tip: hold keys for at least about 0.3 s. The game sometimes does not detect very short key presses.

## 7. Supported game version (with evidence in the code)

### Summary

| Version | Game ID | Default export (starter preset) | With `MP3Update`/`disable_deflicker` | Dolphin connector |
|---|---|---|---|---|
| Wii standalone NTSC-U | **RM3E01** | expected yes (target of the original scripts, not tested here: no ISO available) | **yes**, the only version the hdiffs are built for | yes ("Wii NTSC") |
| Wii standalone PAL | **RM3P01** (Rev 0) | **yes, tested**: export ok, boots up to Olympus, playable | **no**, hpatchz aborts (section 8, F3) | yes ("Wii PAL"), check memory addresses in T02 |
| Wii standalone NTSC-J | RM3J01 | untested | certainly not (the hdiffs only fit NTSC-U) | yes ("Wii NTSC-J") |
| Metroid Prime Trilogy (R3ME01/R3MP01) | R3M* | **not supported**: no code path, no reference | no | no (no Trilogy DOL version) |

**For the MVP (E2):** the target version is **Wii standalone NTSC-U `RM3E01`**. Only with it are all patcher options
available. PAL `RM3P01` works without MP3Update/Deflicker and is usable for development.

### Evidence

1. **There is no active check of game ID or hash.** Neither the exporter
   (`randovania/games/prime3/exporter/game_exporter.py`, `toolchain.py`) nor the patcher
   (`tools/prime3_patcher/MP3Randomizer/MP3Randomizer/*.cs`) reads the game ID or checks an ISO hash.
   Searching for `RM3`, `R3M`, `game_id`, `sha1`/`md5` across `randovania/games/prime3`, `tools/prime3_patcher` and
   the connector finds nothing on this. The export dialog only checks whether the file exists and ends in `.iso`
   (`randovania/games/prime3/gui/dialog/game_export_dialog.py:73-77, 91-92`).
   The patcher works with fixed package file names and asset IDs
   (`tools/prime3_patcher/MP3Randomizer/MP3Randomizer/MP3Randomizer.cs:51-66`).
2. **NTSC-U is the implicit target version of the patcher data:**
   - `randovania/data/gollop_mp3_patcher/CreateWBFS.bat:1-2` hard-codes
     `Metroid Prime 3 - Corruption [RM3E01]/RM3E01.wbfs`.
   - The hdiff patches in `randovania/data/gollop_mp3_patcher/MP3Update/*.hdiff` store the expected
     size of the original file. For all 11 files it does not match PAL. Example `main.dol`:
     expected 6 045 952 bytes, PAL has 6 055 776 bytes. The patches are applied in
     `game_exporter.py:89-98` (Deflicker → `main.hdiff`) and `game_exporter.py:100-122` (MP3Update → 10 paks).
3. **The Dolphin connector knows three Wii standalone DOLs, but no Trilogy version:**
   `randovania/game_connection/builder/prime_connector_builder.py:40,64` loads
   `open_prime_rando.dol_patching.corruption.dol_versions.ALL_VERSIONS` (open-prime-rando 0.15.1, `dol_versions.py:9,33,50`):
   - "Wii NTSC": `!#$MetroidBuildInfo!#$2007/07/27 13:13 Build v3.436 (MP3)`
   - "Wii PAL": `!#$MetroidBuildInfo!#$2007/08/24 16:52 Build v3.453 (mp3)`
   - "Wii NTSC-J": `!#$MetroidBuildInfo!#$2007/11/12 14:15 Build v3.495 (jpn)`
4. **Trilogy:** there is no Trilogy reference at all in the prime3 code. "Trilogy" only occurs for the teleporters of
   Prime 1 and 2. The package names in `MP3Randomizer.cs:51-52` (`Metroid1.pak` … `Worlds.pak`) match the
   standalone layout. On the Trilogy disc the games are in subfolders per game.
5. **Texts:** the patcher replaces strings only in English
   (`tools/prime3_patcher/MP3Randomizer/MP3Randomizer/STRGModificationData.cs:10ff`, `Language.English`).
   For PAL with a system language other than English, pickup texts are therefore probably not adjusted, or mixed.
   Untested.

Test ISO used: `RM3P01`, revision 0, MD5 `f4c734a1e191c45e9ac037d92e14485d` (according to `DolphinTool verify`),
4 699 979 776 bytes.

## 8. Failed steps and error messages

**F1: patcher built as x64** (`dotnet publish -r win-x64 --self-contained false`). The build works,
but running it gives:
```
Unhandled exception. System.DllNotFoundException: Unable to load DLL 'lzokay' or one of its dependencies: The specified module could not be found. (0x8007007E)
   at MP3Randomizer.Compression.decompress(...)
   at MP3Randomizer.Compression.decompress_mrea_block(Byte[] compressed_b) in ...\Compression.cs:line 79
```
Without `lzokay.dll` next to the EXE the file is missing. With the DLL it still fails, because the DLL is 32-bit.
Search paths: `Compression.cs:33-39` (`<exe-dir>\lzokay.dll` or `<exe-dir>\lzokay\lzokay.dll`).
**Solution:** `-r win-x86 --self-contained true` and copy the DLL to `publish/lzokay/` (section 3).

**F2: `tools/prime3_patcher/compare_randomizer_outputs.py` cannot run like this.**
```
Unhandled Exception: System.IO.FileNotFoundException: Could not find file '...\old-output\Standard.ntwk'.
   at MP3Randomizer.NTWK.modify_ntwk(String orig_tweak_location, String dest_tweak_location)
RuntimeError: Randomizer process failed with exit code 3762504530.
```
The script creates an empty output folder. The patcher however expects `Standard.ntwk` to exist there already,
which is always the case in the real export (output = extracted `DATA/files`). In addition the script passes
`--starting-items` as a single argument, which does not fit `custom <bits>`.
**Workaround:** run both patchers by hand with pre-filled output folders and compare SHA-256
(result in section 3: identical).

**F3: export with `mp3_update = true` on PAL.** Tested with a copy of the patch JSON in which `mp3_update` is set to `true`:
```
[ 10%] Extracting ISO...
[ 20%] Removing attract videos...
[ 40%] Applying Update...
RuntimeError: Prime 3 helper failed (hpatchz.exe, exit code 6): ('...\hpatchz.exe', '-f', '...\DATA\files\FrontEnd.pak', '...\MP3Update\FrontEnd.hdiff', '...\DATA\files\FrontEnd.pak')
Helper output:
input oldFile oldDataSize 27923392 != diffFile saved oldDataSize 27951744 ERROR!
```
Checked individually, all 11 hdiffs fail against PAL with exit code 6:

| File | PAL size | expected by the hdiff |
|---|---|---|
| main.dol | 6 055 776 | 6 045 952 |
| FrontEnd.pak | 27 923 392 | 27 951 744 |
| InGameAudio.pak | 4 404 224 | 4 433 536 |
| NoARAM.pak | 16 658 752 | 16 181 824 |
| Metroid1.pak | 773 174 208 | 772 462 336 |
| Metroid3.pak | 698 251 328 | 695 588 608 |
| Metroid4.pak | 738 060 992 | 736 660 224 |
| Metroid5.pak | 577 712 320 | 576 161 856 |
| Metroid6.pak | 126 914 560 | 126 891 392 |
| Metroid7.pak | 158 443 456 | 157 911 168 |
| UniverseArea.pak | 15 069 440 | 15 059 840 |

The same applies to `disable_deflicker` (`main.hdiff`). Here only hpatchz was tested directly, not a whole export.

**F4: `winget install DolphinEmu.Dolphin`** → `No package found matching input criteria.` The correct ID is
`DolphinEmulator.Dolphin`, but that is only version 5.0 (2016). That is why the portable release 2609b is used.

**F5: Dolphin pointer bound to keys (I/J/K/L).** The pointer jumps back to the centre when released, and menu items
cannot be selected. Solution: bind the pointer to the mouse (`Cursor X±/Y±`, section 6).

## 9. Pitfalls and notes for the next tasks

- **Option `--phaaze-skip`:** the patcher's help names `--skip-phaaze`
  (`tools/prime3_patcher/MP3Randomizer/MP3Randomizer/Configuration.cs:162`). The parser however only accepts
  `--phaaze-skip`/`-phaaze-skip` (`Configuration.cs:85`), and that is also what the exporter sends. Only the help text is wrong.
- **Bundled EXE:** `randovania/data/gollop_mp3_patcher/MP3Randomizer.exe` is a 32-bit .NET Framework build
  (recognisable by the stack trace style `System.IO.__Error.WinIOError`). It runs without an installed .NET 8 runtime.
- **T02 (memory mapping):** the connector supports PAL via the build identifier. Whether the PAL addresses in
  open-prime-rando are right is not checked yet. That is a candidate for T02.
- **T05 (patch path):** the patcher gets the seed only as a `--layout` string (Gollop's permalink format), not as
  JSON (`game_exporter.py:224-255`). For AP placeholder items either this format or the patcher has to be extended.
- **An NTSC-U ISO (`RM3E01`) is needed** to test MP3Update/Deflicker and the actual MVP target version.
