# AP patch tool: AP patch data + original ISO → patched ISO (T05a, `.apmp3` T05b)

As of 2026-11-25. Code: `apworld/metroidprime3/patcher/`, tests: `apworld/metroidprime3/test/test_patcher.py`,
`test_tools_download.py` (T28).
Basis: `AP_PATCHER_CHANGES.md` (T16, `--ap-mode`, APItem), `AP_PATCHER_NOTES.md` (T09), `AP_DEV_SETUP.md` (T01).

> **Summary**
> - Input: the patch file `.apmp3` from Archipelago (T05b, section 2.3) **or** a JSON file "AP patch data"
>   (section 2), and an unmodified Wii standalone PAL `RM3P01` or NTSC-U `RM3E01` ISO.
> - Same sequence as the Corruptovania exporter (extract, replace attract videos, patch paks, build ISO), but
>   MP3Randomizer always runs with `--ap-mode` and the seed ID goes into the version-specific build info of `main.dol`
>   (T18). NTSC-U builds apply MP3Update and the Deflicker patch by default (T34).
> - Standard library only: no runtime dependency on Randovania or Archipelago. The letter table and the
>   checksum are copies of our own; a test compares them with the Randovania original.
> - The checked-in `randovania/data/gollop_mp3_patcher/MP3Randomizer.exe` is now the T16 state (win-x86, one file).

## 1. Usage

In the Archipelago clone (APWorld linked in via junction, `AP_APWORLD_DEV.md` section 1):

```powershell
.venv\Scripts\python.exe -m worlds.metroidprime3.patcher --patch <file.apmp3> --iso <original.iso> --out <target.iso>
.venv\Scripts\python.exe -m worlds.metroidprime3.patcher --patch <file.json> --iso <original.iso> --out <target.iso>
```

Whether `.apmp3` or JSON, the tool recognises by the content (ZIP or not), not by the extension. More convenient for players:
open the `.apmp3` in the Archipelago launcher (`AP_APWORLD_DEV.md` section 6); the launcher calls exactly this tool.
Open Patch reuses an existing ISO with a matching seed ID, region and NTSC-U patch setting. To keep builds of the
same seed side by side, use separate output folders or distinct CLI `--out` paths.

Without Archipelago (any Python ≥ 3.10, e.g. the repo venv), from the repo root:

```powershell
venv\Scripts\python.exe apworld\metroidprime3\patcher --patch <file.json> --iso <original.iso> --out <target.iso>
```

(`python -m metroidprime3.patcher` does not work outside Archipelago, because it would load `metroidprime3/__init__.py`,
which needs Archipelago. The folder call only loads the package `patcher`.)

| Option | Meaning |
|---|---|
| `--patch` | `.apmp3` (section 2.3) or AP patch data as JSON (section 2) |
| `--iso` | Original unmodified ISO (`RM3P01` or `RM3E01`). `RM3J01` remains experimental and emits a warning. |
| `--out` | target ISO (is overwritten). Must not be the input ISO |
| `--tools` | folder with the helper programs (default: lookup order of section 3.1, downloads the tools ZIP on first use) |
| `--tools-cache` | cache folder for the downloaded tools (default: `<Archipelago>/metroidprime3_tools`, outside Archipelago `%LOCALAPPDATA%\metroidprime3_tools`) |
| `--temp-dir` | place for the extraction (default: `%TEMP%`; needs about 2 × ISO size free) |
| `--no-verify` | do not read back game ID and seed ID in the target ISO |
| `--no-mp3-update` | skip both MP3Update and Deflicker |
| `--mp3-update` | explicitly select the ten MP3Update PAK patches before randomizing (NTSC-U only) |
| `--disable-deflicker` | explicitly select the Deflicker patch to `main.dol` before writing the seed ID (NTSC-U only) |
| `--dry-run` | only check `--patch` and print the data for MP3Randomizer |
| `--read-seed-id <iso\|dol>` | print the seed ID of an ISO or a `main.dol` and exit |

Example (example data set from the repo, output shortened):

```
.venv\Scripts\python.exe -m worlds.metroidprime3.patcher --patch worlds/metroidprime3/patcher/example_patch.json --iso ..\mp3.iso --out ..\out\t05a_example.iso
[1/6] Extracting ISO...
[2/6] Removing attract videos...
[3/6] Copying paks...
[4/6] Randomizing paks (MP3Randomizer --ap-mode)...
[5/6] Writing seed ID into main.dol...
[6/6] Building ISO...
Done: ..\out\t05a_example.iso
  game ID   RM3P01 (Wii PAL)
  seed ID   fab57b6dbb249239b0a72671053cdd40 (read back from the ISO)
  player    Samus (slot 1, seed T05aExample)
```

Exit code 0 = success, 1 = error (message on stderr: invalid patch data, wrong game, missing helper file,
error of a helper program with its output). Temporary folders are deleted in any case.

From Python (e.g. for a later launcher entry):

```python
from worlds.metroidprime3.patcher import build, patch_data
data = patch_data.load("x.apmp3")        # or "x.json"; read_container() also returns the manifest
build.patch_iso(data, iso, out)          # -> PatchResult(output, game_id, dol_version, seed_id, layout)
```

## 2. Format "AP patch data" (version 1)

One data set per MP3 slot. `generate_output` (T05b, `output.py`) creates it with
`patcher.patch_data.build_patch_data(seed_name, slot, player_name, pickups)` and puts it as `patch_data.json` into the
`.apmp3` (section 2.3). As a loose JSON file (`patch_data.dump(data, path)`) it still works.

```json
{
  "format": "metroidprime3-ap-patch",
  "version": 1,
  "seed_name": "T05aExample",
  "slot": 1,
  "player_name": "Samus",
  "seed_id": "fab57b6dbb249239b0a72671053cdd40",
  "pickups": {
    "1": "Archipelago Item",
    "2": "Missile Expansion",
    "11": "Screw Attack",
    "...": "...",
    "99": "Energy Tank"
  },
  "starting_items": "custom 0000000010010000000001100100100000000010000",
  "starting_location": "custom c133f919c108bdf9 d8cf355d3e9e3741"
}
```

| Field | Required | Content |
|---|---|---|
| `format` | yes | always `"metroidprime3-ap-patch"` |
| `version` | yes | `1`. Other values are rejected |
| `seed_name` | yes | Archipelago's seed name (`multiworld.seed_name`), not empty |
| `slot` | yes | slot number (integer ≥ 1) |
| `player_name` | yes | player name of the slot (information/output only) |
| `seed_id` | no | 32 hex digits (16 bytes). **Must** be `make_seed_id(seed_name, slot)` (otherwise error); if missing, it is computed from that |
| `pickups` | yes | exactly the keys `"1"` … `"99"` (pickup index = AP location ID − base, SPEC E13). Value = name of the **displayed** item: own item → its item name (as in `data/items.py`, e.g. `"Progressive Beam"`, `"Energy Cell 3"`), item of another world → `"Archipelago Item"` (letter `A`, T16) |
| `starting_items` | no | starting inventory in patcher format `custom <43 hex digits>`. Default = starter preset (see below) |
| `starting_location` | no | starting location `custom <world asset ID> <room asset ID>` (hex). Default = G.F.S. Valhalla, Docking Bay 5 |
| `_…` | no | keys starting with `_` are comments and are ignored. All other unknown keys → error |

Allowed item names: every name that has exactly one letter in the letter table (`layout.DISPLAYABLE_ITEMS`),
except `Power Beam` and `CannonBall` (the C# decoder does not know `0` and `L`, `AP_PATCHER_NOTES.md` 1.5). All pool items
of the APWorld are allowed (test). Location 0 is not in the patch data (E13/E17); the tool puts its vanilla item
Hypermode there, the patcher never touches location 0 anyway.

The patch tool uses the default suit and door/welding colours, skips the Phaaze shortcut and sets
`--hyper-hints --fast-flying` as in the exporter. AP mode disables the missile and ship-missile requirements
(E3/E7/E15). MP3Update and Deflicker are local build options outside the patch data format. The launcher reads
`metroidprime3_options.mp3update` from `host.yaml` (default `true`). On NTSC-U, `false` skips both patches.
On PAL the setting has no effect. In the CLI, omitting the patch flags uses the regional default. The two explicit
patch flags can select either patch independently. From Python, leaving both keyword arguments unset uses the
regional default. An explicit `True` or `False` for either argument selects only the patches explicitly enabled.

**Defaults = starter preset**, as Randovania's `patch_data_factory` created them for seed IVG2J7OR
(`build/seed/t01.patcher.json`): `starting_items` gives Power Beam, Charge Beam, Morph Ball Bombs, Scan Visor, Morph Ball,
Space Jump Boots and `HyperModeOriginal = 1` (no corrupted Hypermode). The game always has the Combat Visor; it is
not in the string. A test decodes the string with Randovania's `STARTING_ITEMS_ORDER` and compares it with
`data/items.py STARTING_ITEMS`.

**Slot starting items (T31, E23).** Since v0.4.0 `generate_output` writes the slot's own starting items
(`patch_data.starting_items_string`, YAML option `starting_items`, `docs/AP_OPTIONS.md`). MP3Randomizer puts the
values into the SPWN object of the starting room, so a new game starts without the removed items; the client never
takes items away (E11), so this is the only place where they can be left out. Digits used: Power Beam 8, Charge Beam
(ChargeUpgrade) 11, Morph Ball Bombs (Bomb) 21, Scan Visor 22, Morph Ball 25, Space Jump Boots (DoubleJump) 28,
`HyperModeOriginal` 38 = 1 (offsets in the string after `custom `; a test checks every subset against Randovania's
`starting_items_for` order). With all seven the string is exactly the starter preset string above. The patch tool
prints the decoded starting items in its summary (`start …`).

### 2.1 Translation for MP3Randomizer

`PatchData.randomizer_patch_data()` returns the same keys as Randovania's patch JSON (`layout patcher-data`), with
fixed AP values and additionally `"ap_mode": true`:

| Key | Value |
|---|---|
| `seed` | layout string: `"00"` + 100 letters (index 0 = Hypermode `z`, 1–99 from `pickups`) + 5 hex characters SHA-256 |
| `starting_items`, `starting_location` | from the patch data |
| `random_door_colors`, `random_welding_colors`, `missile_required_mains`, `ship_missile_required_mains`, `phaaze_skip`, `mp3_update`, `disable_deflicker` | `false` |

Command line (`build.randomizer_command`), the same as `game_exporter._build_randomizer_command` plus `--ap-mode`:

```
MP3Randomizer.exe --input-path <paks>\ --output-path <DATA\files>\ --layout <seed> --starting-items custom <hex>
  --starting-location custom <world> <room> --hyper-hints --fast-flying --ap-mode
```

### 2.2 Seed ID (T18)

There is exactly **one** function for it: `patcher.seed_id.make_seed_id`. Patch tool (`validate`), `generate_output`
(via `build_patch_data`) and later the client (T18 part 2) call it; a test checks that the ID in every
generated `.apmp3` equals `make_seed_id(seed_name, slot)`.


- Value: `make_seed_id(seed_name, slot)` = the first 16 bytes of `SHA-256("metroidprime3-ap\0<seed_name>\0<slot>")`.
  Deterministic, so that the client can recompute it from `seed_name` (RoomInfo) and its slot, without `slot_data`.
- Place: build string of `main.dol`, bytes 6–22 (originally `roidBuildInfo!#$`), like the layout UUID in Randovania
  (`AP_MEMORY_MAP.md`, row "Layout UUID"). Pure data, no code reads the string.
- Addresses (own copy from open-prime-rando `dol_versions.py`, `patcher/seed_id.py`):

| Version | Game ID | Build string address | Seed ID in RAM | DOL file offsets |
|---|---|---|---|---|
| Wii NTSC-U | RM3E01 | `0x805822B0` | `0x805822B6`–`0x805822C5` | build string `0x57E390`, ID `0x57E396` (T33) |
| Wii PAL | RM3P01 | `0x805843A8` | `0x805843AE`–`0x805843BD` | build string `0x580488` (data section 11), ID `0x58048E` |
| Wii NTSC-J | RM3J01 | `0x80587C2C` | `0x80587C32`–`0x80587C41` | – |

- Writing: `seed_id.write_seed_id_to_dol_file(main_dol, seed_id)` (finds the version via the build string, converts
  address → file offset via the DOL header, changes exactly 16 bytes).
- **Reading (for the client, T18 part 2):**

```python
from worlds.metroidprime3.patcher import seed_id
version = seed_id.version_for_game_id("RM3P01")
raw = dolphin.read_bytes(version.build_string_address, len(version.build_string))
found = seed_id.seed_id_from_build_string(raw, version)   # None = unpatched/non-AP ISO
ok = found == seed_id.make_seed_id(room_seed_name, my_slot)
```

  `seed_id_from_build_string` raises `ValueError` if the bytes are not the build string of this version at all.
  From files: `seed_id.read_seed_id(dol_bytes)`, `read_seed_id_from_dol_file(path)`, `build.read_seed_id_from_iso(iso)`
  (fetches only `sys/main.dol` via `wit EXTRACT --files +sys/main.dol`).

### 2.3 Patch file `.apmp3` (T05b)

ZIP file (Archipelago `APPatch`, class `output.MP3Container`), name `<output name>.apmp3`, e.g.
`AP_38224278823687041413_P2_Samus.apmp3`, one per MP3 slot in the output ZIP of `Generate.py`.

| File in the ZIP | Content |
|---|---|
| `archipelago.json` | Archipelago's manifest: `game` = `Metroid Prime 3: Corruption`, `player` (slot), `player_name`, `server` (empty; the WebHost fills in its address on download), `patch_file_ending` = `.apmp3`, `procedure` = `custom`, `compatible_version` 6, `version` 7 |
| `patch_data.json` | AP patch data v1 (section 2), with `seed_id` |

The tool reads the `.apmp3` with the standard library only (`patch_data.read_container`) and rejects it if
`game` is not MP3, `player` does not match `slot`, one of the two files is missing or the patch data is invalid.
Content of the pickups (SPEC E14): own item at an own location → real item name; item of another world (also of another
MP3 slot or of an item link group) → `Archipelago Item`. An own item that the patcher cannot show
(only conceivable via plando of a starting item such as Power Beam) also becomes `Archipelago Item`, with a warning.

**Why `APPatch` and not `APProcedurePatch`:** `APProcedurePatch` applies byte procedures in memory to the
source file (`get_source_data` reads it in completely). That does not fit a 4.7 GB ISO with external tools (nodtool,
MP3Randomizer, wit). `APPatch` is an `APPlayerContainer` with `procedure: "custom"` (like the
`.aptww` of The Wind Waker): Archipelago knows player and extension, applying is done with our tool.

**Example (acceptance T05b):** 2-player seed MP3 (slot 2) + ChecksFinder, seed `38224278823687041413`:
79 own, 20 foreign pickups. `--patch AP_38224278823687041413_P2_Samus.apmp3 --iso ..\mp3.iso --out ..\out\t05b_duo.iso`
→ done after 40 s, game ID `RM3P01`, seed ID `7f5dd9550100c7beb4f4c5ac21f184c7` read back from the ISO
(`--read-seed-id` confirms). The ISO is played in T07/T08.

## 3. Requirements

- **Windows** (the helper programs are `.exe`). Python ≥ 3.10, standard library only.
- The default build (T28) requires `MP3Randomizer.exe` (T16 build,
  see 4), `lzokay/lzokay.dll` (32-bit), `nodtool/nodtool.exe`, `wit/bin/wit.exe` with the four Cygwin DLLs it imports
  (`cygwin1.dll`, `cygcrypto-1.1.dll`, `cygncursesw-10.dll`, `cygz.dll`, from its PE import table),
  `dummy_attract/attract01.thp`, `dummy_attract/Attract02.thp`. The NTSC-U patches also require `hpatchz.exe`
  and the selected `.hdiff` files. If a required file is missing, the tool aborts before extracting.
- `nodtool.exe` needs the Microsoft Visual C++ 2015-2022 Redistributable (`MSVCP140.dll`, `VCRUNTIME140.dll`). If it is
  missing, the error names the redistributable. `MP3Randomizer.exe` is self-contained (.NET runtime inside), `wit.exe`
  only needs its Cygwin DLLs.
- Original Wii standalone ISO. Tested revisions are PAL `RM3P01` Rev 0 (MD5 `f4c734a1e191c45e9ac037d92e14485d`)
  and NTSC-U `RM3E01` Rev 0. The patcher rejects Trilogy by its game ID before extraction.
- Free space: about 2 × ISO size in `--temp-dir` plus the target ISO (≈ 4.5 GB). Duration about 1 minute.

### 3.1 Where the helper programs come from (T28)

`patcher/tools.py` (`find_tools`), first match wins:

1. `--tools` / `metroidprime3_options.tools_folder` in `host.yaml` (the launcher ignores the setting if the folder has
   no `MP3Randomizer.exe`),
2. `$MP3AP_TOOLS_DIR`,
3. the cache: `<cache>/tools-<first 12 hex digits of the ZIP hash>/` with the marker file `metroidprime3_tools.sha256`
   (written only after a verified extraction; a cache of another tools version is ignored),
4. `randovania/data/gollop_mp3_patcher` of a Corruptovania checkout (developers; not present in a packed `.apworld`),
5. `metroidprime3-tools-win.zip` placed into `<cache>/` by hand (offline install; the file is kept),
6. download of the tools ZIP from the fixed URL
   `https://github.com/junkx420/Prime3AP/releases/download/v0.4.0/metroidprime3-tools-win.zip` (`TOOLS_RELEASE_TAG`,
   `TOOLS_ZIP_NAME`). `$MP3AP_TOOLS_URL` replaces the URL (mirror or local test server); the hash is enforced anyway.

`<cache>` = `<Archipelago>/metroidprime3_tools` (`Utils.user_path`, only if Archipelago already imported `Utils`, so the
patcher stays standard library only), outside Archipelago `%LOCALAPPDATA%\metroidprime3_tools`, or `--tools-cache`.

Download: `urllib`, 1 MB chunks into `<zip>.part`, SHA-256 while streaming against `TOOLS_ZIP_SHA256` (fixed in the
code), progress at most every 0.25 s through the progress callback (the T23 patch window shows "Downloading patch tools
(first use only): 12.0 of 31.4 MB..."). Then "Checking patch tools..." / "Extracting patch tools..." into a staging
folder in the cache (paths with `..`, drive letters or absolute paths are rejected), required files checked, marker
written, staging folder renamed. The downloaded ZIP is deleted afterwards; the extracted folder is the cache.

Errors (`PatchToolError`, shown in the launcher's error dialog): offline/HTTP error ("Could not download the patch
tools from <url>: <reason>"), wrong hash ("... have SHA-256 x, expected y. The file was deleted."), damaged manual ZIP
("Delete it and download it again"). Each message ends with the manual steps: download the ZIP from the release page and
put it unextracted into `<cache>`, or extract it anywhere and set `tools_folder`.

`patch_iso` resolves the tools after the game ID check and before extracting, so the download is part of the patch
window. `read_seed_id_from_iso` never downloads unless `allow_download=True` (the CLI's `--read-seed-id` passes it; the
launcher's "is the existing ISO up to date" check does not).

### 3.2 MP3Update and Deflicker on NTSC-U (T34)

The v0.4.0 tools ZIP is prepared with `hpatchz.exe` and the eleven `.hdiff` files. Until publication, point
`metroidprime3_options.tools_folder` or `--tools` to `randovania/data/gollop_mp3_patcher` in a Corruptovania
checkout, or use a locally built v0.4.0 tools ZIP. If an older or incomplete folder is selected, the patch tool lists
the missing files before extracting the ISO. An enabled NTSC-U build shows `[3/7] Applying MP3Update and Deflicker...`
in the progress window. See [AP_NTSC.md](AP_NTSC.md) for the file list and test results.

## 4. Checked-in MP3Randomizer EXE (T16 build)

`randovania/data/gollop_mp3_patcher/MP3Randomizer.exe` is now the source state of T16
(`tools/prime3_patcher/MP3Randomizer`, commit `f348f00bf`), as **one** self-contained win-x86 file
(32 266 413 bytes, no .NET installation needed). The companion file is still `lzokay/lzokay.dll` (unchanged).

```bash
export PATH="/c/Program Files/dotnet:$PATH" DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
dotnet publish tools/prime3_patcher/MP3Randomizer/MP3Randomizer.csproj -c Release -r win-x86 --self-contained true \
  -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -p:DebugType=none \
  --artifacts-path build/mp3r-single -o build/mp3r-single/publish
cp build/mp3r-single/publish/MP3Randomizer.exe randovania/data/gollop_mp3_patcher/MP3Randomizer.exe
```

Why one file: the normal self-contained build (`AP_DEV_SETUP.md` 3) is ~220 files / 67 MB; the single-file EXE
is one file of 32 MB. It still finds `lzokay.dll` via `AppContext.BaseDirectory` (= folder of the EXE,
`Compression.cs`). The old EXE (242 KB, .NET Framework build) needed no runtime; the same holds for the new one.

**Counter-check without `--ap-mode`** (seed IVG2J7OR, flags of the starter preset incl. `--require-launcher
--require-ship-missile`, input = unmodified PAL `DATA/files`): old checked-in EXE against new single-file EXE,
**all 13 files SHA-256-identical** (11 patched, Logbook and MiscData unchanged). A full export with
Randovania (section 5) confirms this.

## 5. Results (acceptance T05a)

See `STATUS.md` T05a. Details:

1. **Tests** (`test_patcher.py`, 20 tests, in the Archipelago clone):
   letter table, order, reverse table, `AP_ITEM` and the syntax tree of `layout_string_for_items`
   identical to the Randovania source (read via `ast`, without importing `randovania`); 50 random placements give
   the same string as the original function; patch data of seed IVG2J7OR → exactly Randovania's layout string
   `00kk44g44…kc602b`; example data set (mixed) = original function; default starting values = Randovania's patch JSON of the
   starter preset; validation (13 error cases); `--ap-mode` in the command, no optional flags; package uses only the
   standard library; writing/reading the seed ID on mock DOLs of all three versions and on a **copy of the real
   PAL DOL** (`MP3_PAL_EXTRACTED`, otherwise skipped): exactly 16 bytes from `0x58048E` change.
   Existing tests: APWorld 84 passed (+ one skip each without environment variable), `test/general` 250 passed.
2. **Example ISO**: `patcher/example_patch.json` (placement IVG2J7OR, every third location `Archipelago Item`, 33 foreign /
   66 own, location 11 = Screw Attack) → `..\out\t05a_example.iso`, game ID `RM3P01`, seed ID read back.
3. **Live test** (PrimeHack 1.0.9, "Emulated CPU Clock Override" off, new game): the ISO boots to Valhalla; in RAM
   game ID `RM3P01` and seed ID `fab57b6dbb249239b0a72671053cdd40`. Location 11 (Docking Bay 5) shows
   "Screw Attack acquired" when collected; afterwards Screw Attack (slot 16) is still 0/0, only ItemPercentage (slot 21) 0/100 → 1/101, in the
   Valhalla flag block only byte 1: 0 → 1.
4. **Normal export** without `--ap-mode`: old and new EXE give 13/13 identical files for IVG2J7OR; a complete
   Randovania export (starter preset) with the new EXE is SHA-256-identical to the T01 ISO (`e63643aa…`).

## 6. Known gaps

1. **Windows only.** macOS/Linux would need the exporter's helper programs for these platforms (Randovania's
   macOS toolchain is not in the repo) and a Linux build of MP3Randomizer.
2. ~~The helper programs come from the repo~~: done in T28. The `.apworld` still does not contain them, but the
   patch tool downloads the tools ZIP of the release on first use (section 3.1).
3. ~~No launcher entry / no `.apmp3`~~: done in T05b (section 2.3, `AP_APWORLD_DEV.md` section 6).
4. **Texts**: foreign pickups all show "Archipelago-Item" (E14); player/item name per location is missing (after the MVP).
   English only (like all patcher texts).
5. NTSC-J (`RM3J01`) remains an untested patcher input and sends a warning. The client supports PAL and NTSC-U.
6. Nobody checks the seed ID before the client (T18 part 2) reads it.
7. Starting location and starting items are patcher strings in the format; structured starting items come with F9 (options).
8. The EXE is 32 MB and lives in Git as a binary file (every new version enlarges the history).
