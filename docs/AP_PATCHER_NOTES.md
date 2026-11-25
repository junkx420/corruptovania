# AP patcher analysis: MP3Randomizer and exporter (T09)

As of 2026-11-23. Read only, no code in the repo changed. Answers the four questions from `STATUS.md` (T09) as
input for F-01 (location check detection and item giving from outside).

Sources and conventions:
- `PATCHER/` = `tools/prime3_patcher/MP3Randomizer/MP3Randomizer/` (C#, `net8.0`). `ItemName.cs` is one level higher
  in `tools/prime3_patcher/MP3Randomizer/`.
- `EXP/` = `randovania/games/prime3/exporter/`. `GOLLOP` = `randovania/games/prime3/patcher/gollop_corruption_patcher.py`.
- `OPR/` = `venv/Lib/site-packages/open_prime_rando/dol_patching/` (open-prime-rando 0.15.1, not checked into the repo).
- **Own measurement on the PAL `main.dol` (`RM3P01`)**: the file was only read and only analysed in the scratchpad. Evidence
  for it is given as virtual Wii addresses, not line numbers. The script is in section 8 so that it can be repeated.
- Everything that was only inferred from code and is not shown live in the game is marked as **unchecked** or
  **inference**.

> **Summary**
> 1. In the patch JSON a pickup has **not a single field of its own**. All 100 pickups are one letter each in the string
>    `seed`. Item ID, model, text and amount come from the fixed C# table `Item.cs`.
> 2. `ItemName.cs` (57 entries) are **patcher names, not inventory IDs**. The inventory slots (0–69) are addressed in the game via
>    a sorted **hash→slot table in `main.dol`** (59 entries). Per pickup the patcher writes the
>    4-byte hash (`item_type`), not the slot.
> 3. **Free and addressable per pickup is only slot 47.** Slots 43 and 53–61 are free, but have no hash.
>    Slots 68 and 69 are already used by the patcher itself as "temporary" marker items. That is the proof that a
>    pickup can give a stat slot as a marker.
> 4. The patcher does **not** touch `main.dol`. The DOL is only changed in the exporter via `hpatchz` (Deflicker, only
>    NTSC-U). A hook of our own is feasible, but only with reverse engineering effort.

---

## 1. How does a pickup get from the patch JSON into the game?

### 1.1 Data flow

```
Randovania layout (patches.pickup_assignment)
  └─ CorruptionPatchDataFactory.create_game_specific_data        EXP/patch_data_factory.py:18
       ├─ pickup_names[0..99]  (empty index = "Missile Expansion")       :26-33
       └─ layout_string_for_items(pickup_names) → string "seed"          :35 → GOLLOP:188-197
  └─ patch JSON (11 keys, table 1.2)                                     :108-120
  └─ CorruptionGameExporter._do_export_game                              EXP/game_exporter.py:60
       ├─ extract ISO (DATA/files, DATA/sys)                             :78-79
       ├─ optional main.dol via hdiff (NTSC-U only)                      :89-98
       ├─ copy 13 files to paks_path                                     :124-144
       └─ call MP3Randomizer.exe --layout <seed> --starting-items ...    :146-150 and :236-255
            └─ MP3Randomizer.Main                                        PATCHER/MP3Randomizer.cs:10
                 1. read arguments (--layout = encoded_permalink)        PATCHER/Configuration.cs:65-67
                 2. decode_permalink: string → ItemName[]                PATCHER/MP3Randomizer.cs:13, MP3Permalink.cs:12
                 3. swap in main-required variants                       PATCHER/MP3Randomizer.cs:14-32
                 4. Patches.add_patches: collect all game patches        PATCHER/MP3Randomizer.cs:50, Patches.cs:268-329
                 5. PAK.modify_pak per pak, then NTWK                    PATCHER/MP3Randomizer.cs:51-66, PAK.cs:94-121
       └─ WIT builds the ISO from DATA                                   EXP/game_exporter.py:152-159
```

### 1.2 Fields in the patch JSON

Source: `EXP/patch_data_factory.py:108-120` (plus `_randovania_meta`, which the framework adds; example
`build/seed/t01.patcher.json`).

| Key | Content | Read by |
|---|---|---|
| `commands` | `set` lines in the style of `randovania/data/gollop_mp3_patcher/RandomizePaks.bat:1` | nobody (the exporter does not read them) |
| `seed` | layout string: 2 rotation characters + 100 pickup characters + 5 hex characters SHA-256 checksum | `EXP/game_exporter.py:242-243` → `--layout` |
| `starting_items` | `custom <43 hex digits>` | `game_exporter.py:231,244-245` → `--starting-items` |
| `starting_location` | `custom <world ID> <room ID>` | `game_exporter.py:232,246-247` |
| `random_door_colors`, `random_welding_colors` | bool | `game_exporter.py:248-249` |
| `missile_required_mains`, `ship_missile_required_mains` | bool | `game_exporter.py:252-253` |
| `phaaze_skip` | bool | `game_exporter.py:254` |
| `mp3_update`, `disable_deflicker` | bool | `game_exporter.py:89,100` (exporter, not the patcher) |

**A pickup has neither item ID nor model nor text nor amount in the JSON.** There is exactly one character per pickup index:
- The index comes from the Randovania pickup index 0–99 (`patch_data_factory.py:26-33`). An unassigned index becomes
  `"Missile Expansion"` (`:31-32`). For the index 0–99 there are 100 pickup nodes in the database (checked, without gaps).
- The character comes from `LETTER_TO_ITEM_MAPPING` (`GOLLOP:47-127`). An item without a letter raises a
  `KeyError` in Python (`GOLLOP:128,195`).
- The alphabet is `LAYOUT_LETTERS` (`GOLLOP:13`). The first two characters (`"00"`, `GOLLOP:189`) mean "no
  rotation". Otherwise the C# decoder rotates (`MP3Permalink.cs:14-15,255`).
- The checksum is the first 5 hex characters of SHA-256 over the rest (`GOLLOP:194-195`, checked in
  `MP3Permalink.cs:18-24`, error = `ArgumentException`).
- There is no pickup model for an item of another world. The pickup database only has the empty key
  `default_offworld_model` (`pickup_database/pickup-database.json:776`), and the patch data does not know it.

### 1.3 What the patcher defines per item (`Item.cs`)

The decoder turns the character into an `ItemName` (`MP3Permalink.cs:35-253`). `Item.get_item_data(ItemName)`
(`PATCHER/Item.cs:43`) then returns an object with these fields (`Item.cs:7-41`):

| Field | Size | Meaning | Written to (property ID) | Line |
|---|---|---|---|---|
| `item_type` | 4 B | **hash of the inventory slot** (see 2.2). `FF FF FF FF` = no inventory item (progressive) | PCKP `A0 2E F0 C4` | `PickupPatches.cs:68` |
| `capacity` | 4 B | capacity increase (Missile Expansion = 5, Suit = 5, Ship Missile = 3, otherwise 1) | PCKP `28 C7 1B 54` | `:69`, `Item.cs:134,478,715` |
| `amount` | 4 B | amount increase | PCKP `94 AF 14 45` | `:70` |
| `model` | 8 B | asset ID CMDL (static model). `FF…FF` = none; only the Energy Cells set it | PCKP `C2 7F FA 8F` | `:71`, `Item.cs:558` |
| `character` + `default_animation` | 8 B + 4 B | asset ID CHAR (animated model) plus animation. This is the visible pickup model | PCKP `A2 44 C9 D8` | `:72`, `:30-41` |
| `scan` | 8 B | asset ID SCAN (scan text) | PCKP `B9 4E 9B E7` | `:73` |
| `pickup_effect` | 8 B | asset ID PART (particle effect) | PCKP `A9 FE 87 2A` | `:74` |
| `streamed_audio` | 8 B | asset ID STRM (jingle) | STAU `9D 1A 67 A8` | `:94` |
| `memo` | 8 B | asset ID STRG (HUD message, e.g. "Plasma Beam acquired!") | MEMO `91 82 25 0C` | `:95` |
| `percent` | 4 B | is set, but **never evaluated** (no use outside `Item.cs`) | – | `Item.cs:11` |
| `is_progressive`, `progressive_*` | – | Progressive Beam/Missile (two inventory givers in the room) | – | `PickupPatches.cs:235-281` |
| `conversion_start_*`, `conversion_end_*` | – | main-required variants (see 3.1) | – | `PickupPatches.cs:109-234` |

So amount and text are bound to the `ItemName`. A pickup with e.g. "Plasma Beam, 3 pieces, own text" cannot be
expressed today.

### 1.4 Which game structures does the patcher write?

| Structure | What | Line |
|---|---|---|
| Script object **PCKP** (pickup) in the room's MREA script | item type, capacity, amount, model, scan, effect (7 properties) | `PickupPatches.cs:66-75` |
| Script object **SPFN** (special function) | for the 10 locations of type `SpecialFunction` (index 0, 9, 34, 42, 43, 62, 70, 73, 79, 89): the SPFN is reconfigured, a **second PCKP** (`percentage_pickup_id`) gets type, capacity, amount | `:78-91`, `PickupLocations.cs:11,20,45,53,54,73,81,84,90,100` |
| **STAU**, **MEMO** | jingle and HUD text per location; optionally change the HUD type | `:94-107` |
| **New script objects** (conditional relay, inventory giver/taker) and **connections** | progressive items and main-required conversion | `:109-281`, `SpecialFunction.cs:7-53`, `ConditionalRelay.cs:7-52` |
| **Dependency lists** per MREA (CMDL, PART, CHAR, SCAN, STRG, STRM) | so that the model is loaded in the room | `:46-64`, `MP3Dependencies.cs:9,1575,1601` |
| **STRG resources** (texts) | 32 fixed English strings (+2 optional hyper hints), 10 of them with synthetic IDs `0xABCDABCDABCD00xx` | `STRGModificationData.cs:10-41` (hints `:42-56`), `StringPatches.cs:7-23`, `Item.cs:78` |
| **Fake pickups** | 19 display objects (model and scan only, no item type) that show the item of index n | `PickupPatches.cs:424-465`, `FakePickupLocations.cs:8` |
| **Starting inventory**: SPWN object in the starting room | 30 properties (amounts, capacities, flags per item) | `StartPatches.cs:236-287`, `MP3Inventory.cs:5-87` |
| Starting location (TEL1), reveal map (1 timer + 22 AVMC) | – | `StartPatches.cs:7-234,289-296` |
| about 40 further room patches (cutscenes, doors, fixes) | – | `Patches.cs:270-316` |
| `Standard.ntwk` (tweaks) | – | `MP3Randomizer.cs:66` |

**Not written:** `main.dol`, save, boot files. The patcher only changes 10 paks (`MP3Randomizer.cs:52`)
and `Standard.ntwk`.

### 1.5 Pitfalls for Archipelago

- **Location 0 is never patched.** The loop starts at 1 (`PickupPatches.cs:12`). Entry 0 has a dummy MREA ID
  `9999999999999999998` (`PickupLocations.cs:11`) and is "Pickup (Phazon Enhancement Device)" in
  MedLab Delta (Olympus) in the database. The layout still has a character there (an Energy Tank in seed `IVG2J7OR`). It has
  no effect in the game. For AP 99 patchable locations remain.
- **Exactly 100 locations, hard-wired:** `new PickupLocation[100]` (`PickupLocations.cs:9`). More locations need new entries
  with script instance IDs from the paks.
- **Python and C# do not match:** Python knows `L` = CannonBall (`GOLLOP:95`), the C# decoder does not
  (`MP3Permalink.cs:252-253` throws "Unsupported character"). `0` (Power Beam) and all commented-out letters
  (`GOLLOP:66-106`) are missing in C# as well.
- **Texts English only** (`STRGModificationData.cs:10ff`, `Language.English`). On PAL in another system language the
  behaviour is unchecked (already in `AP_DEV_SETUP.md`, section 7).
- **The patcher only gets the seed string** (`--layout`), not the JSON (`game_exporter.py:224-255`). New fields
  (marker, text) need either a new CLI argument or a new character alphabet.

---

## 2. Inventory item IDs, unused slots and comparison with `AP_MEMORY_MAP.md`

### 2.1 Two different "IDs"

| Term | Where | Range |
|---|---|---|
| `ItemName` | `tools/prime3_patcher/MP3Randomizer/ItemName.cs:1-60` | 57 patcher names (enum index 0–56). **Not** the game ID |
| Item hash (`item_type`) | `Item.cs` per variant, column `specific` in `logic_database/header.json` | 4 bytes, e.g. Plasma Beam `0x93AD6DF9` |
| Inventory slot (`item_id`) | `header.json` (`extra.item_id`), memory `PS + 0x54 + id * 0xC` (`AP_MEMORY_MAP.md:61`) | 0–69 |

**Of the 57 `ItemName` entries, 44 are implemented in `Item.get_item_data`.** The other 13 are Echoes leftovers
(`DarkBeam`, `LightBeam`, `AnnihilatorBeam`, `BeamAmmoExpansion`, `DarkSuit`, `LigthSuit`, `DarkVisor`, `EchoVisor`,
`SeekerLauncher`, four translators; `ItemName.cs:47-59`). They throw `ArgumentException("Unsupported item")`
(`Item.cs:813-814`) and also have no character in the decoder.

The hash in the patcher is **identical** to `extra.specific` from `header.json` (all 38 hashes used
compared, e.g. Plasma Beam `147,173,109,249` = `2477616633` = `0x93AD6DF9`, `Item.cs:49`).

### 2.2 The hash→slot table in `main.dol` (own measurement, PAL)

In the PAL `main.dol` at **`0x80584AB8`–`0x80584C88`** (file offset `0x580B98`–`0x580D68`) there is a table sorted
by hash with **59 entries** of 8 bytes each: `u32 hash, u32 slot`. Example: `93AD6DF9 00000001` = Plasma Beam →
slot 1. The code accesses the start and the end via `lis r5,0x8058 / addi r5,r5,0x4AB8` (`0x802DA564`/`0x802DA568`)
and `addi …,0x4C90` (`0x802DACA8`). That is an opcode pattern; **I did not disassemble the function**. That the
table translates the PCKP hash into a slot by binary search is an **inference** and not shown live. It fits with
the table being sorted and the patcher writing the hashes exactly like this.

Further measured values:
- All 58 hashes from `header.json` are in the table, each exactly once. In addition there is **one entry that is not in
  `header.json`: `0x51E1A9FB` → slot 47**.
- `add_power_up`, `incr_pickup`, `decr_pickup` (PAL `0x80191E2C`, `0x801920B0`, `0x8019222C`, addresses from
  `AP_MEMORY_MAP.md:38-40`) each start with `stwu r1,-0x20(r1)`, `mflr r0`, **`cmplwi r4,0x45`**. So the game
  accepts slots **0 to 69** (0x45). This confirms the function addresses on the real PAL DOL for the first time.

### 2.3 All slots 0–69

"Pickup use" = `ItemName` variants of the patcher that write this hash as `item_type` (`Item.cs`).
If the entry is missing, the patcher never writes the slot via a pickup.

| Slot | Hash (PAL table) | Name (`header.json`) | Pickup use in the patcher |
|---|---|---|---|
| 0 | `0xFB73F2B8` | PowerBeam | – (starting item, no character `0` in C#) |
| 1 | `0x93AD6DF9` | PlasmaBeam | PlasmaBeam |
| 2 | `0x50A0AAA5` | NovaBeam | NovaBeam |
| 3 | `0x35488520` | ChargeUpgrade | ChargeUpgrade |
| 4 | `0x922DA6A8` | Missile | MissileExpansion, MissileLauncher, ConverterMissileLauncher |
| 5 | `0x90F0CED4` | IceMissile | IceMissile |
| 6 | `0xB7F4E76D` | Seekers | SeekerMissile |
| 7 | `0x719B5C5D` | GrappleBeamPull | GrappleLasso |
| 8 | `0x1F2950DC` | GrappleBeamSwing | GrappleSwing |
| 9 | `0x1FF64711` | GrappleBeamVoltage | GrappleVoltage |
| 10 | `0xB9876CD1` | Bomb | Bomb |
| 11 | `0x96664E97` | CombatVisor | CombatVisor |
| 12 | `0xB3CADC47` | ScanVisor | ScanVisor |
| 13 | `0x73D674EA` | CommandVisor | CommandVisor |
| 14 | `0x662B235A` | XRayVisor | XRayVisor |
| 15 | `0x95C0052A` | DoubleJump | SpaceJump |
| 16 | `0xD9CD9EDE` | ScrewAttack | ScrewAttack |
| 17 | `0xD02B0AD8` | SuitType | Suit |
| 18 | `0x26B5C6C5` | Energy | – |
| 19 | `0x1D966CE8` | HypermodeEnergy | – |
| 20 | `0xB36AECDD` | EnergyTank | EnergyTank |
| 21 | `0x50499B43` | ItemPercentage | – |
| 22 | `0xABBC4C2E` | Fuses | – |
| 23–31 | `0x336E6C92` … `0x3DB5E4A0` | Fuse1 … Fuse9 | Fuse1 … Fuse9 |
| 32 | `0x482F8235` | MorphBall | MorphBall |
| 33 | `0xB21BB8C7` | BoostBall | BoostBall |
| 34 | `0x4D415752` | SpiderBall | SpiderBall |
| 35 | `0x5568B8C9` | HyperModeTank | HyperModeTank |
| 36 | `0x49E8A1AC` | HyperModeBeam | – |
| 37 | `0x515556A0` | HyperModeMissile | HyperMissile |
| 38 | `0x8C4847AB` | HyperModeBall | HyperBall |
| 39 | `0x87560845` | HyperModeGrapple | HyperGrapple |
| 40 | `0x8FEBB10D` | HyperModePermanent | – |
| 41 | `0xF4FFB39D` | HyperModePhaaze | – |
| 42 | `0xE5BA1551` | HyperModeOriginal | – |
| **43** | **no entry** | – (gap in `header.json`) | – |
| 44 | `0x57A20D1A` | ShipGrapple | ShipGrapple |
| 45 | `0x81A153FF` | ShipMissile | ShipMissileExpansion, ShipMissile, ConverterShipMissile |
| 46 | `0x7DC366E4` | FaceCorruptionLevel | – |
| **47** | `0x51E1A9FB` | – (not in `header.json`) | – |
| 48 | `0x7B6A8F3A` | CannonBall | – (`L` missing in the C# decoder) |
| 49 | `0xB42B43DE` | ActivateMorphballBoost | – |
| 50 | `0x898D3214` | HyperShot | – |
| 51 | `0x3F82745E` | CommandVisorJammed | – |
| 52 | no entry | EnergyCellsUsed (`header.json`, without hash) | – |
| **53–61** | **no entry** | – (not in `header.json`) | – |
| 62–67 | `0xC05C27EB` … `0x47E7BCEA` | Stat_EnemiesKilled … Stat_CommandoKills | – |
| **68** | `0x22390F26` | Stat_TinCanHighScore | **MainRequiredMissileExpansion** (`Item.cs:152-171`) |
| **69** | `0x38BE4C42` | Stat_TinCanCurrentScore | **MainRequiredShipMissileExpansion** (`Item.cs:773-792`) |

IDs 1000–1003 (`MissileLauncher`, `ShipMissileLauncher`, `TemporaryMissile`, `TemporaryShipMissile`) are pure
logic resources without slot and without hash (`header.json`, `AP_MEMORY_MAP.md:117`).

### 2.4 Free or unused slots, with reasons

"Free" here means: neither the patcher nor the Randovania database occupies the slot, and there is no evidence of
use in the game. **That the game never reads a slot cannot be proven statically.** The game has the slot
in the array (index ≤ 69), and no value was ever observed in it. The proof needs a live test (section 5).

| Slot | Hash-addressable per pickup? | Status | Reason |
|---|---|---|---|
| **47** | **yes** (`0x51E1A9FB`) | **best candidate** | In the DOL table, but in no Randovania/patcher file (`header.json`, `Item.cs`, `MP3Inventory.cs`). `GOLLOP:94` names "PhazonBall" for the gap between `FaceCorruptionLevel` (46) and `CannonBall` (48) (commented out, probably a cut feature). That is a hint from a comment, **unchecked**. Max. capacity of the slot unknown |
| **43** | no (no hash) | free, but only writable | gap between 42 and 44 in `header.json` and in the DOL table. **Caveat:** the starting inventory struct has a field `HyperModeCharge` (`StartPatches.cs:285`, `MP3Inventory.cs:81`) that `header.json` does not know. It could belong to slot 43, **unchecked** |
| **53–61** | no (no hash) | free, but only writable | named in no source. The stats start at 62 (`header.json`). The array reaches up to 69 (`cmplwi r4,0x45`), so the slots exist |
| 52 | no (no hash) | unclear | `header.json` knows `EnergyCellsUsed` (max 9, `AP_MEMORY_MAP.md:115`) without hash. Whether the game itself uses the slot is open |
| 68, 69 | yes | **occupied by the patcher**, free only with `missile_required_mains = false` and `ship_missile_required_mains = false` | `MP3Randomizer.cs:16-23` replaces Missile Expansion / Ship Missile Expansion with the main-required variants, whose `item_type` are these two stat hashes. The starter preset has both flags at `true` (`build/seed/t01.patcher.json`) |
| 62–67 | yes | not free | the game counts itself: 63 and 64 confirmed live (`AP_MEMORY_MAP.md:272-273`). 62, 65 to 67 by name as well, not seen live |
| 18–19, 21–22, 36, 40–42, 46, 49–51 | yes | not free | game state (energy, hypermode, face corruption, flags). The patcher writes them only as starting values, not per pickup |

### 2.5 Comparison with `docs/AP_MEMORY_MAP.md`

| Point in `AP_MEMORY_MAP.md` | Finding | Consequence |
|---|---|---|
| Line 119: "IDs 43, 47 and 53–61 are missing in `header.json`" | correct. But **47 has a hash in the DOL**, 43 and 53–61 have none | 47 is addressable per pickup, 43/53–61 are not |
| Line 117 and 189-190: `TemporaryMissile` (1002) "not in memory" | On the game side the ammo is probably in **slot 68** (`Stat_TinCanHighScore`) and the Ship Missile ammo in slot 69. This follows from `Item.cs:152-171,773-792` and the hashes. **Derived from code, not measured live.** T02 only names `ItemPercentage` +1 for the first pickup (`AP_MEMORY_MAP.md:271`); slot 68 is not mentioned there. Whether the watch log showed it is open | A "Locked Missile Expansion" would have to raise slot 68 by 5 as long as the Missile Launcher is missing. Easy to check live |
| Line 199: counter item "for example an unused slot (43, 47, 53–61)" | Per pickup the patcher can today only write slots with a hash. That rules out 43 and 53–61 | see section 3 |

---

## 3. Can a pickup give any inventory item with an ID of its own?

**Yes, with restrictions.** The patcher only writes the 4-byte hash (`PickupPatches.cs:68`). There is no whitelist check
apart from the `switch` in `Item.get_item_data` (`Item.cs:46-815`). There are two proofs that the game accepts hashes of
slots that are not a "real" item:
- **Slots 68 and 69** are stat counters. The patcher already hands them out as markers today
  (`Item.cs:152-171,773-792`), and the conversion into real missiles runs via relays (`PickupPatches.cs:109-234`).
- Progressive items manage without an inventory hash at all: `item_type = FF FF FF FF` plus two inventory giver objects
  (`Item.cs:69,233`, `PickupPatches.cs:259-280`).

A marker per location with an ID of its own runs into **three limits**, however:

| Limit | Finding |
|---|---|
| **Too few slots** | hash-addressable and free is only slot 47 (plus 68/69 if the main-required flags are switched off). 99 locations would need 99 slots. The 11 slots without hash (43, 52–61) are unreachable per pickup |
| **Unknown clamping** | the game has a maximum capacity per slot (Missile 255, stats 99999, `AP_MEMORY_MAP.md:78-116`). For 43, 47 and 53–61 it is unknown. If it is 0 or 1, amount bits disappear |
| **Amount is additive** | a pickup increases `amount`/`capacity` (live: ItemPercentage 0/100 → 1/101, `AP_MEMORY_MAP.md:271`). Two pickups of the same slot add up |

### 3.1 Options and their effort

| Variant | Idea | Assessment |
|---|---|---|
| **A. Bit mask in `amount`/`capacity`** | every location adds `2^k` to a marker slot. A sum of different powers of two can be decomposed unambiguously | needs 99 bits. Stat slots (max 99999) carry at most 16 bits per field. 3 slots (47, 68, 69) × 2 fields × 16 bits = 96 bits, so barely too few if slot 47 does not carry more. Depends entirely on the clamping (unchecked). **Feasible with conditions** |
| **B. Extend the DOL table** | add hash entries for 43, 52–61 (11 more slots) | still only 12–13 slots. Does not help for 99 locations, additionally requires a DOL patch (section 4) |
| **C. Counter item (count only)** | every pickup increases a counter by 1. The client sees "one more came in", but not which | not enough for unambiguous checks. Usable as a plausibility check (ItemPercentage does that already) |
| **D. Event hook in the DOL** | hook in `add_power_up`/`incr_pickup` writes (slot, delta) into a ring buffer | the hook sees the arguments **before** any clamping. With a unique delta per location (`amount = location ID + 1` in slot 47) the location in the buffer is unambiguous, without amounts having to add up. Needs the DOL patch from section 4 |

### 3.2 What would have to be changed in the patcher for this (description only)

For a neutral "AP item" (model + text) and a marker per location:

1. **`ItemName.cs:1-60`**: add a new entry `APItem` (or one per marker type). Alternatively repurpose one of the 13 dead
   Echoes entries so as not to change the enum order.
2. **`Item.cs:43-815`**: new `case` with `item_type` = hash of the marker slot (for 47: `51 E1 A9 FB`), `capacity`/`amount`
   (the marker amount), `model`/`character`/`scan`/`pickup_effect`/`memo`/`streamed_audio`. The amount per location is
   not parameterisable today (the amount is part of the `ItemName`). For "one marker per location" `get_item_data` would additionally need the
   location index (`PickupPatches.cs:29`: `Item.get_item_data(item_list[j])`, the index `j` is available there).
3. **Model and text:** only assets listed in `MP3Dependencies.get_file_dependencies()` (`MP3Dependencies.cs:9`). For
   unknown ones `PAK.gather_resources` aborts with "Failed to find dependency" (`PAK.cs:73-90`). A neutral model can
   be reused from existing items without intervention (e.g. the generic sphere model of the Energy Cells,
   `Item.cs:558`). A text of its own needs an STRG entry. New IDs work, see the synthetic
   `0xABCDABCDABCD00xx` (`Item.cs:78,242`, `STRGModificationData.cs:40-41`). For 99 individual texts ("Sent Hookshot
   to Player2") it would be 99 new STRG resources. Scaling to that is **unchecked**.
4. **`MP3Permalink.cs:35-253`**: a new character for the AP type. The decoder computes exactly one item per character. The
   100-location markers do not fit in this way. Cleaner is a **second parameter**, e.g. `--ap-markers <list>` with one
   marker number per location (`Configuration.cs:65ff` knows the pattern for arguments).
5. **`EXP/patch_data_factory.py:26-35,108-120`** and **`GOLLOP:47-127,188-197`**: add the marker list to the patch JSON,
   extend `_build_randomizer_command` (`game_exporter.py:224-255`). On Windows the exporter today uses the
   checked-in `MP3Randomizer.exe` (`toolchain.py:86`), not the source (`AP_DEV_SETUP.md`, section 3). A changed
   patcher needs a new win-x86 build in `randovania/data/gollop_mp3_patcher/` (checked-in binary file, see T05).
6. **Location 0** stays unpatchable (`PickupPatches.cs:12`) as long as the loop starts at 1 and the dummy MREA ID applies.

---

## 4. Does the patcher change `main.dol`?

**No.** In the patcher source there is no access to `main.dol`, no addresses and no PowerPC code. Searching for
`dol`, `ppc`, `hook`, `0x8…` across `tools/prime3_patcher` only finds the hit `AppContext.BaseDirectory` in
`Compression.cs:33`. The patcher also only gets the paks and `Standard.ntwk` as input
(`game_exporter.py:127-141`), never the DOL.

The only DOL change in the whole chain is **in the exporter**:

| Step | Line | Effect |
|---|---|---|
| `hpatchz` applies `MP3Update/main.hdiff` to `DATA/sys/main.dol` | `game_exporter.py:89-98`, `toolchain.py:27-28,87` | switch off deflicker. The hdiff stores the size of the NTSC-U DOL (6 045 952 B); the PAL DOL (6 055 776 B) is rejected (`AP_DEV_SETUP.md`, section 8, F3) |

### 4.1 Would a hook of our own be feasible?

**Feasible with effort.** What already exists and what is missing:

| Building block | State | Evidence |
|---|---|---|
| Point in the export where the DOL is accessible | available: `extract_path/DATA/sys/main.dol` is already edited | `game_exporter.py:95` |
| DOL editor and PowerPC assembler in Python | available in the venv (`ppc_asm`, used by `open-prime-rando`): `DolEditor.write_instructions` | `venv/Lib/site-packages/ppc_asm/dol_file.py:74-116` |
| Appending a new DOL section | **not** in `ppc_asm`. `offset_for_address` raises for an unknown address | `ppc_asm/dol_file.py:91-95` |
| Space for code | **available, without a new section.** PAL DOL, section 0 (text, `0x80004000`–`0x800066C0`) has two zero gaps: **1228 B at `0x80005868`** and **716 B at `0x80004A68`**. In addition 8 section slots in the DOL header are unused (5 text, 3 data), in case one wants to append a section after all | own measurement, section 8 |
| Space for data (ring buffer) | zero gaps in the data sections, e.g. **490 B at `0x805B58D4`** (section 12). Whether they are writable and unused by the game is unchecked | own measurement |
| Ready-made MP3 hook | **missing.** `remote_execution_patch_start` and `_load_player_state` raise `ValueError` for Corruption | `OPR/all_prime_dol_patches.py:82,177` |
| Entry point "every frame" | **unknown.** `string_display = None` for all three regions | `OPR/corruption/dol_versions.py:17,41,58` (`AP_MEMORY_MAP.md:41`) |
| Entry point "item received" | **known**: `add_power_up`, `incr_pickup`, `decr_pickup` | PAL `0x80191E2C`, `0x801920B0`, `0x8019222C`. The prologues are confirmed. The first instruction `stwu r1,-0x20(r1)` is position-independent and can be copied into the gap |
| Other regions | **missing:** every region has its own addresses (`OPR/corruption/dol_versions.py`), no NTSC-U dump is available | `AP_DEV_SETUP.md`, section 7 |

Proposal for the smallest sensible variant (**unchecked**): redirect `add_power_up` via a trampoline. In `.init` sit a
few dozen instructions that write `(slot, delta)` into a ring buffer in the data area and then jump into the original
function. The item event is then certain for every pickup, even without a marker bit mask. An
item queue "from outside in", on the other hand, needs the missing frame entry point. **Not needed for the MVP**: giving
items works without a hook via direct writing into the inventory (`AP_MEMORY_MAP.md:158-160`, to be tested live in T07).

An **alternative without ISO change** fits E2 (Dolphin only): the client writes the hook code into memory at runtime via
`dolphin-memory-engine`. Whether Dolphin flushes the JIT cache after such a write is unchecked.

---

## 5. Optional live test

**Not tested.** Reasons: the test needs (a) an out-of-repo build of the patcher with a changed `Item.cs`,
(b) a new export (about 1 minute, 15 GB of space) and (c) someone to collect the pickup in the game. That does not
reliably fit into 30 minutes. Instead the PAL DOL was evaluated statically (sections 2.2 and 8).

Proposal for the test that answers the biggest open question (clamping and persistence of slot 47):
1. Copy of `PATCHER/` outside the repo. `ItemName.DarkBeam` (`ItemName.cs:47`, unused) gets a `case` in
   `Item.cs` with `item_type = 51 E1 A9 FB`, `capacity = 00 00 00 05`, `amount = 00 00 00 05` and the visuals of `EnergyTank`
   (`Item.cs:496-515`). In the decoder `MP3Permalink.cs:130` redirect the character `B` (HyperMissile) to it for the test.
2. Seed `IVG2J7OR` (`build/seed/t01.patcher.json`): swap the character of a location near the start (starting world Valhalla,
   `AP_MEMORY_MAP.md:249`), compute the new SHA-256 checksum (`GOLLOP:194-195`), export. The Missile Expansion in Docking
   Bay 5 is the first pickup (`AP_MEMORY_MAP.md:271`, "probably" there).
3. Collect in Dolphin and read slot 47: `PS + 0x54 + 47 * 0xC` = **`PS + 0x288`** (chain `AP_MEMORY_MAP.md:60-61`).
   Log before/after, then save, reload and read once more.
4. Additionally write slots 43 (`PS + 0x258`) and 53–61 (`PS + 0x2D0` … `PS + 0x330`) by hand (Dolphin Memory Engine)
   and check whether the game resets them on a room change, saving or loading.

---

## 6. Assessment

| Question | Verdict | Reasoning and effort |
|---|---|---|
| **Neutral "AP item" with its own model and text** | **feasible with effort** | new `ItemName` + `case` in `Item.cs` + one character in the decoder. Model from existing assets, text via a new STRG ID. Effort: about 4 patcher files, 2 Python files, one new win-x86 build. Individual texts per location unchecked |
| **Marker item per location (unambiguous)** | **feasible with effort, with conditions** | **A slot of its own per location is not feasible** (free and addressable is only slot 47). Two routes remain: (A) a bit mask across a few slots. That only works if the slots hold values up to 2^16 or more, and even then barely (96 bits for 99 locations). That is unchecked. (D) A unique delta per location (`amount = location ID + 1` in slot 47), read by a DOL hook. D is independent of the clamping, but needs the hook. Effort for both: an additional patcher parameter (one marker number per location, section 3.2), a live test (section 5). Location 0 stays excluded. **The live test of the clamping is decisive** |
| **Hook in `main.dol`** | **feasible with effort** (item event only, region PAL) / **high effort** (frame hook, further regions) | infrastructure exists (export point, `ppc_asm`, code gaps, confirmed `add_power_up` address). Missing: frame entry point, NTSC-U/J addresses, check of the data gap for the ring buffer. Not needed for the MVP if variant A works |
| **Direct item writing (c)** | **not investigated (T07)** | slot array is valid up to 69 (`cmplwi r4,0x45`). Side effects open (`AP_MEMORY_MAP.md:158-160`) |

**Recommendation for F-01:** approach (a) is feasible in principle, but not as "one slot per pickup". Realistic is a
marker made of a few slots whose amount encodes the location. The live test from section 5 is needed before the decision. Approach (b)
is only realistic as an event hook on `add_power_up`. Approach (c) (giving items by writing) stays plausible for the MVP.

---

## 7. Open points

1. Live test of slot clamping and persistence (section 5). This is the only point that can overturn the marker decision.
2. Does slot 47 have a function in MP3 ("PhazonBall" is only a comment in `GOLLOP:94`)? Does slot 43 have the field `HyperModeCharge`?
3. Is `TemporaryMissile` really slot 68? Check live: collect a "Locked Missile Expansion" and read slot 68.
4. Disassemble the lookup function at `0x802DA564` to prove the inference "binary search hash→slot" and the behaviour for an unknown hash
   (crash or no effect).
5. Evaluate the NTSC-U DOL as soon as a dump is available (E7). Table and function addresses differ per region.
6. 99 individual STRG texts: scaling of the patcher (size of the paks, dependencies) unchecked.

---

## 8. Reproduction of the DOL measurement

The PAL `main.dol` was taken read-only from our own ISO (`DolphinTool extract`) and is not in the repo. Check script
(Python 3.12, `py -I`), argument = path to the `main.dol`:

```python
import struct, sys
d = open(sys.argv[1], "rb").read()
offs  = struct.unpack(">18I", d[0x00:0x48])   # file offsets of the 18 sections
addrs = struct.unpack(">18I", d[0x48:0x90])   # virtual addresses
sizes = struct.unpack(">18I", d[0x90:0xD8])
def v2f(v):
    for o, a, s in zip(offs, addrs, sizes):
        if s and a <= v < a + s:
            return o + v - a
p, table = v2f(0x80584AB8), {}                # PAL: start of the hash->slot table
while True:
    h, slot = struct.unpack(">II", d[p:p + 8]); table[slot] = h; p += 8
    if h == 0xFB73F2B8: break                 # largest hash = last entry
print(len(table), "entries; missing slots 0-69:", [i for i in range(70) if i not in table])
# expected: 59 entries; missing [43, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61]
for name, addr in [("add_power_up", 0x80191E2C), ("incr_pickup", 0x801920B0), ("decr_pickup", 0x8019222C)]:
    o = v2f(addr); print(name, [hex(w) for w in struct.unpack(">3I", d[o:o + 12])])
# expected for each: ['0x9421ffe0', '0x7c0802a6', '0x28040045']  (stwu, mflr, cmplwi r4,0x45)
```

Header of the PAL `main.dol`: 10 used sections (2 text, 8 data), 8 free slots (5 text, 3 data), BSS `0x805C2E00`–`0x80686A04`, entry
`0x80006320`, no data after the last section (file size = section end `0x5C6760`).
