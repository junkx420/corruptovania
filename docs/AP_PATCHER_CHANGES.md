# AP patcher changes: APItem and AP mode "display only" (T16)

As of 2026-11-24. Implementation of SPEC E10, E14, E15 in the patcher `MP3Randomizer` (C#) and in the Python encoder.
Basis: `AP_PATCHER_NOTES.md` (T09), measurement method from `AP_LIVE_TESTS.md` (test D), flag table
`apworld/metroidprime3/location_flags.py` (T12).

> **Summary**
> - New item **`APItem`** (character `A`): neutral model, text "Archipelago-Item", never gives anything.
> - New switch **`--ap-mode`**: every pickup only shows its item (model, jingle, HUD text) and gives nothing:
>   `item_type FF FF FF FF`, amount/capacity 0/0, no progressive or main-required relays. Missile- and
>   ship-missile-required are always off with it.
> - Without `--ap-mode` the output is **byte-identical** to the previous state.
> - Live (PrimeHack, Clock Override **off**): APItem and an own real item (Progressive Beam) could be collected,
>   model and text were right, one flag byte each was set (location 11 → byte 1, location 4 → byte 8). In the inventory nothing
>   changed apart from the counter ItemPercentage (slot 21, +1 per pickup).

## 1. Changes

### 1.1 C# patcher (`tools/prime3_patcher/MP3Randomizer/`)

| File | Change |
|---|---|
| `ItemName.cs` | new entry `APItem` **at the end** of the enum (existing values unchanged; `X`…`)` in the decoder map to value 0) |
| `MP3Randomizer/Item.cs` | constants `AP_ITEM_MEMO_ID = 0xABCDABCDABCD000A` (next free synthetic ID after `…0009`) and `AP_ITEM_TEXT = "Archipelago-Item"`; new `case ItemName.APItem` (table 1.2) |
| `MP3Randomizer/STRGModificationData.cs` | new STRG `AP_ITEM_MEMO_ID` with the English text "Archipelago-Item". It only ends up in a pak if a pickup has it as a dependency (`PAK.gather_resources`) |
| `MP3Randomizer/MP3Dependencies.cs` | entry `AP_ITEM_MEMO_ID` without dependencies (like the other synthetic STRGs) |
| `MP3Randomizer/MP3Permalink.cs` | decoder: character `A` → `ItemName.APItem` |
| `MP3Randomizer/Configuration.cs` | flag `--ap-mode` (also `-ap-mode`) → `ap_mode`. If it is set, `require_launcher` and `require_ship_missile` are set to `false` at the end of parsing (E15), no matter in which order the flags come. Help text extended |
| `MP3Randomizer/MP3Randomizer.cs` | passes `ap_mode` on to `Patches.add_patches` |
| `MP3Randomizer/Patches.cs` | `add_patches(..., bool ap_mode = false)` → `PickupPatches.add_pickup_patches(..., display_only: ap_mode)` |
| `MP3Randomizer/PickupPatches.cs` | switch `display_only`: directly after `Item.get_item_data` it calls `apply_display_only(item)`: `item_type = FF FF FF FF`, `amount`/`capacity` = 0, `is_progressive = false`, progressive and conversion IDs empty. Model, character, scan, effect, jingle (STAU) and HUD text (MEMO) stay. Applies to `Pickup` and `SpecialFunction` locations (there for the second PCKP `percentage_pickup_id`), to APItem and to real items |
| `MP3Randomizer.Tests/ApModeTests.cs` | 15 new xUnit tests (section 3.1) |

Not changed: fake pickups (`add_fake_pickup_patches`, only show the model), starting inventory, location 0 (is still
never patched), the checked-in `randovania/data/gollop_mp3_patcher/MP3Randomizer.exe` (T05 replaces it).

### 1.2 The APItem

| Field | Value | Origin |
|---|---|---|
| `item_type` | `FF FF FF FF` | no inventory item (like progressive items) |
| `amount`, `capacity`, `percent` | 0 | – |
| `model` (CMDL) | `31EF1551AF0D30D8` | static Energy Cell model (`Item.cs`, Fuse1–9). No animation |
| `character` / `default_animation` | `FF…FF` / `FFFFFFFF` | as Energy Cell (no CHAR) |
| `scan` | `FF…FF` | **no scan**, so that no misleading scan text appears |
| `pickup_effect` (PART) | `6BCBBA792CEA4332` | default effect of most items |
| `streamed_audio` (STRM) | `A832FC0C74651F24` | expansion/Energy Cell jingle |
| `memo` (STRG) | `ABCDABCDABCD000A` | new, text "Archipelago-Item" (English only, like all patcher texts) |

"Neutral" is relative: the game has no placeholder model of its own. The Energy Cell model was chosen because it
is static (no CHAR/ANIM) and is already in `MP3Dependencies`. Another model only needs new values in
`case ItemName.APItem`. The APItem gives nothing **even without** `--ap-mode`.

### 1.3 Python (`randovania/games/prime3/patcher/`)

| File | Change |
|---|---|
| `corruption_items.py` | constant `AP_ITEM = "Archipelago Item"` (Python name of the APItem) |
| `gollop_corruption_patcher.py` | `LETTER_TO_ITEM_MAPPING["A"] = [AP_ITEM]` (previously commented out: `HyperModeBeam`, no pickup slot). `ITEM_NAME_TO_LETTER_MAPPING` derives `AP_ITEM → "A"` from it. New: `AP_MODE_FLAG = "--ap-mode"` and `ap_mode_arguments(ap_mode) -> tuple[str, ...]` (empty without AP mode) |

`patch_data_factory.py` and `game_exporter.py` are **not** changed. The Randovania export knows no AP mode and
stays unchanged. The caller passes the switch itself (section 2), so for T05 the patch tool of the APWorld.

## 2. Calling the AP mode

Build the layout string as before, foreign items as `AP_ITEM`, own items with their normal name:

```python
from randovania.games.prime3.patcher import gollop_corruption_patcher as g
from randovania.games.prime3.patcher.corruption_items import AP_ITEM

names = [...]                      # 100 entries, index = pickup index 0-99 (0 is never patched)
names[11] = AP_ITEM                # foreign item
layout = g.layout_string_for_items(names)
extra = g.ap_mode_arguments(True)  # ("--ap-mode",)
```

Command line (all other flags as in the normal export, `game_exporter._build_randomizer_command`):

```
MP3Randomizer.exe --input-path <paks>\ --output-path <DATA\files>\ --layout <layout> \
  --starting-items custom <hex> --starting-location custom <world> <room> \
  --hyper-hints --fast-flying --ap-mode
```

`--require-launcher`/`--require-ship-missile` may be passed, they are ignored with `--ap-mode`. The patcher expects
`Standard.ntwk` to be in the output folder already (it is in the real export, `IO.write_b` opens with `FileMode.Open`).

Build (win-x86, as `AP_DEV_SETUP.md` section 3): `build/mp3r/publish/MP3Randomizer.exe` plus `lzokay/lzokay.dll`.

## 3. Tests and results

### 3.1 Automatic tests

- `dotnet test tools/prime3_patcher/MP3Randomizer.Tests/MP3Randomizer.Tests.csproj --artifacts-path build/mp3r-tests`:
  **17 passed** (2 old + 15 new). Newly checked: `--ap-mode` off by default and switches missile-required off (both
  orders); APItem data; STRG text and dependency; decoder `A`; `apply_display_only` for Plasma Beam, Progressive
  Beam, main-required expansion, converter launcher, Energy Cell (visuals stay, item fields empty); `add_pickup_patches`
  with `display_only` writes `FF FF FF FF`/0/0 into **all 99** PCKP, including the **10 SpecialFunction locations** (9, 34, 42, 43,
  62, 70, 73, 79, 89, 93; second PCKP), and creates no relays or connections for Progressive Beam; without the switch
  every pickup still gives its item.
- `venv/Scripts/python.exe -m pytest test/games/prime3`: **24 passed** (19 old + 5 new in
  `test/games/prime3/patcher/test_gollop_corruption_patcher.py`: letter `A`, layout string with APItem, layout string of
  seed IVG2J7OR unchanged, `ap_mode_arguments`, every Python letter is known in the C# decoder except the old gaps
  `0` and `L`).
  Note: the GUI tests in `test/games/prime3/gui` need the generated Qt files (`*_ui.py`, excluded via `.gitignore`).
  `setup.py build_ui` failed in this venv (pyqt_distutils `TypeError`). They were generated with
  `pyside6-uic` for every entry from `pyuic.json`.

### 3.2 Byte identity without AP mode

Patcher before the change (source state `a556fc588`, win-x86 build, equal to the checked-in EXE) against the new build,
seed IVG2J7OR (`build/seed/t01.patcher.json`), input = unmodified PAL `DATA/files`:

| Run | Result |
|---|---|
| with `--require-launcher --require-ship-missile` (starter preset) | all **11** output files SHA-256-identical |
| without missile-required | all **11** output files SHA-256-identical |
| old build against checked-in EXE (control) | identical |

With `--ap-mode` and the test seed below Metroid1/3/4/5/7.pak change. FrontEnd, Metroid6/8, UniverseArea, Worlds and
`Standard.ntwk` stay the same. The text "Archipelago-Item" is in Metroid1.pak and Metroid5.pak, i.e. in the paks with
the APItem locations.

### 3.3 Live test

**Environment:** PrimeHack v1.0.9, **CPU Clock Override off** (confirmed by the user via screenshot, 100 %), VBI override off,
PAL RM3P01, new game (Normal, throwaway save slot). Measurement with `dolphin-memory-engine` as in `AP_LIVE_TESTS.md` test D:
before and after every pickup all 70 inventory slots (`PS + 0x54 + slot*0xC`) and the flag block of the world (anchor world ID +
`0x400` at `+0x18` + `0xEAEAEAEA` at `−4`). There was exactly one flag block each time.

**Test ISO** (outside the repo, `..\out\t16_ap.iso`): seed IVG2J7OR with three changed locations, exported with the new
build and `--ap-mode` (missile-required off):
`00kk44}44xtk9A4sdk444Cko{4rk^44}{4D447h44444444448uy44vk4Ik4444II44IIp4qk444B444kzII}44e#I4Ak44H4k4n4k63e2f`

| Location | Item in the seed | Role |
|---|---|---|
| 11, G.F.S. Valhalla – Docking Bay 5 (starting room) | APItem | foreign item |
| 4, Norion – Docking Hub Alpha (Grapple Lasso location) | Progressive Beam | own real item, display only (also checks that the relays are left out) |
| 89, Pirate Homeworld – Command Courtyard (SpecialFunction) | APItem | optional, not visited |

**Result** (2026-11-24):

| Location | Model (user) | Text / jingle (user) | Inventory diff, 70 slots | Flag block |
|---|---|---|---|---|
| 11 (16:52:47 → 16:54:19) | Energy Cell | "Archipelago-Item", jingle | only slot 21 ItemPercentage 0/100 → 1/101 | Valhalla `0x80A20180`: **byte 1** 0 → 1, nothing else (set before: 35) |
| 4 (16:56:29 → 16:56:56) | Plasma Beam | "Progressive Beam acquired!", jingle | only slot 21 1/101 → 2/102. Plasma Beam (slot 1) stays 0/0 | Norion `0x80A042C0`: **byte 8** 0 → 1, nothing else (set before: 1, 6, 118) |

- Both pickups could be collected, no crash. The flag bytes match `location_flags.py` (11 → 1, 4 → 8).
- **Deviation from "inventory diff empty":** **ItemPercentage (slot 21) rises by 1 per pickup**, as with every pickup in
  the normal game. The pickup gives no item. Deliberately left like that: the client's learning/log mode (E19) detects new
  pickups precisely by the rise of ItemPercentage. The value is not in the AP pool and does not disturb the target/current giving (E11).
- Between the pickups only slot 63 changed (game statistics, shots); that has nothing to do with the pickup.

**SpecialFunction location live: not tested.** With the starting items no SpecialFunction location is reachable
(playthrough simulator, physical mode: only locations 4, 11, 84). The nearest is location 89 (Command Courtyard, needs the
Plasma Beam, which could be given by writing memory). The user declined the extra route after the mandatory part.
The patcher part is covered by a unit test (3.1). Live, this remains for T13 or the learning mode in the playtest (E19).

## 4. Open points

1. **T05:** replace the checked-in EXE with this build and build the call with `--ap-mode` in the patch tool of the APWorld.
   The APWorld must not depend on Randovania at runtime. So it needs its own copies of `LAYOUT_LETTERS`, the
   letter table and the checksum (`layout_string_for_items`).
2. Live test of an `FF FF FF FF` pickup at a SpecialFunction location (e.g. location 89), with the flag byte (byte 10 according to the table,
   "probable"). The test ISO already has an APItem there.
3. Whether ItemPercentage should be suppressed in AP mode is decided by the client design (E19 needs the rise).
4. Texts in English only (like all patcher texts). Unchecked on PAL in another system language.
5. Saving/reloading after the AP pickups was not checked in T16. For MRLY bytes this is known from T10.
