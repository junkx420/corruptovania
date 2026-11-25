# SAVW format and location flags (T12)

As of 2026-11-24. Read only, game data stays outside the repo. Applies to Metroid Prime 3 Wii PAL `RM3P01`.
NTSC-U is not checked. Everything that is only inferred from the data and not measured is marked as an **assumption**.

> **Summary**
> 1. The 1024-byte flag block per world (`AP_LIVE_TESTS.md`, test D) is the **state of the Memory Relays (MRLY)** from
>    **list 1 of the SAVW** of this world. Byte `i` belongs to entry `i` of the list, empty slots count too.
> 2. A pickup does not set a byte of its own. When collected, it activates "its" Memory Relay via a relay
>    (`PCKP –ACQU/ACTN→ SRLY –RLAY/ACTV→ MRLY`). On load this MRLY switches the pickup off again (`ACTV/DCTV → PCKP`).
> 3. All three measuring points match: location 11 → byte 1, location 3 → byte 7, location 4 → byte 8.
> 4. Table for all 99 locations: `apworld/metroidprime3/location_flags.py`. **89 certain, 10 probable** (the 10
>    SpecialFunction locations), no collision. Original and patched ISO (T01 seed) give byte-identical tables.
> 5. For the 10 SpecialFunction locations **the second PCKP** (`percentage_pickup_id`) is in the SAVW, **not the SPFN**.
>    Their byte comes from the Memory Relay that the common trigger of SPFN and PCKP activates.

## 1. Reproduction

Extract the ISO (outside the repo, e.g. next to the repo folder):

```powershell
tools\dolphin\Dolphin-x64\DolphinTool.exe extract -i mp3.iso -o pal_extract -g -q
```

Generate the table (repo root, venv from `AP_DEV_SETUP.md`):

```powershell
venv\Scripts\python.exe -I apworld\tools\build_location_flags.py ..\pal_extract
```

With `--check` it only compares (exit 1 on a difference). Running it twice gives a byte-identical file (checked,
also with different `PYTHONHASHSEED`). Without `lzokay` (e.g. system Python) the parser uses a built-in
LZO1X decompressor; checked on 1298 real segments, same result. Run time about 1.5 s.

Tests (without game data 6 run, the 5 game-data tests are skipped):

```powershell
$env:MP3_PAL_EXTRACTED = "..\pal_extract"; venv\Scripts\python.exe -m pytest apworld\tools\test_savw_parser.py -v
```

Sources: parser `apworld/tools/savw_parser.py`. Patcher code `tools/prime3_patcher/MP3Randomizer/MP3Randomizer/`
(`PAK.cs`, `MP3MLVL.cs`, `MP3Area.cs`, `MREANew.cs`, `ScriptLayer.cs`, `ScriptObject.cs`, `Connection.cs`,
`PickupLocations.cs`). Evidence for the runtime form from the T10 snapshots (PrimeHack, MEM1/MEM2, not in the repo).

All numbers are big endian.

## 2. Containers

### 2.1 PAK (Wii)

| Offset | Size | Content |
|---|---|---|
| `0x00` | `0x40` | header (`PakHeader.cs`) |
| `0x40` | 4 | number of sections (3) |
| `0x44` | 3 × 8 | each FourCC + size: `STRG` (names), `RSHD` (resources), `DATA` |
| `0x80` | … | the sections one after another |

`RSHD`: `u32` count, per resource `u32` compressed (0/1), FourCC type, `u64` asset ID, `u32` size, `u32` offset from
`DATA`. `STRG`: `u32` count, per entry C string, FourCC, `u64` ID. In the PAL ISO all MLVL, SAVW and MREA are uncompressed
(flag 0). All 16 game SAVWs are in `Worlds.pak`, the MLVL/MREA in `Metroid1.pak` … `Metroid8.pak`.

### 2.2 MLVL (version `0x19`, `MP3MLVL.cs`)

| Offset | Content |
|---|---|
| `0x00` | magic `0xDEAFBABE` |
| `0x04` | version `0x19` |
| `0x08` | `u64` world name (STRG) |
| `0x10` | `u32` temple_key_world_index |
| `0x14` | **`u64` SAVW ID** |
| `0x1C` | `u64` skybox |
| `0x24` | `u32` number of areas, then per area: `u64` name, 48 B transform, 24 B bounding box, **`u64` MREA ID**, `u64` internal ID, `u32` n + n × `u16` adjacent areas, `u32` docks (each `u32` n + n × 8 B, `u32` m + m × 12 B), C string internal name |

The area index (order in this list) is the "area" field in the instance ID.

### 2.3 MREA (version `0x1E`, `MREANew.cs`)

| Offset | Size | Content |
|---|---|---|
| `0x00` | 4 | magic `0xDEADBEEF` |
| `0x04` | 4 | version `0x1E` |
| `0x08` | 48 | transform |
| `0x38` | 4 | number of world models |
| `0x3C` | 4 | number of script layers |
| `0x40` | 4 | number of data sections |
| `0x44` | 4 | number of compressed blocks |
| `0x48` | 4 | number of section labels |
| `0x4C` | 20 | padding |
| `0x60` | … | per section `u32` size, aligned to 32; per block 4 × `u32` (buffer size, decompressed, compressed, section count), aligned; per label FourCC + `u32` section index (`SOBJ` = first script layer, `DEPS`, `SGEN`, …), aligned; then the blocks |

Block with compressed size 0: raw. Otherwise `(-compressed) mod 32` padding bytes come **before** the data, then segments with
`i16` length (negative = raw), each decompressing to at most `0x4000` bytes (LZO1X). A block contains as many sections as
its header states.

**Script layer** (section `SOBJ + n`): 10-byte header (`SCLY`, version, byte 8 = layer number), `u32` number of objects.
Per object: FourCC type, `u16` size (from here), `u32` instance ID, `u16` number of connections, per connection FourCC
state, FourCC message, `u32` target, then the properties.

**Instance ID** (32 bits): bits 31–26 layer, 25–16 area index, 15–0 local ID. `PickupLocations.cs` contains the layer
(`scly_section`) and the lower 16 bits; the full ID is in the MREA. The PCKP carries the GUID of its SAVW entry in
its properties.

**Peculiarities of the patched game** (Corruptovania patcher, seen on `out/t01_IVG2J7OR.iso`):
- Connection targets are written back without layer bits (`Connection.export`: `00 | area | ID`). The game
  finds the targets anyway (location 4 is on layer 16 and set byte 8 live). The parser therefore resolves targets via the
  lower 26 bits.
- Decompressed blocks are padded to 32 bytes without adjusting the section size.
- Some new patcher objects have the same area+ID in several layers. The parser resolves such targets only by exact
  full ID. For none of the 99 locations is such an object in the chain.

## 3. SAVW (version 6)

| Offset | Size | Content |
|---|---|---|
| `0x00` | 4 | magic `0xC001D00D` |
| `0x04` | 4 | version `6` |
| `0x08` | 4 | number of areas (= areas in the MLVL, checked for all 19 SAVWs) |
| `0x0C` | 4 + n × 20 | **list 0**: cinematics (`CINE`) |
| … | 4 + n × 20 | **list 1: Memory Relays (`MRLY`) = flag block** |
| … | 4 + n × 20 | **list 2**: doors (`DOOR`) |
| … | 4 + n × 12 | scans: `u64` SCAN ID, `u32` logbook category |
| … | 4 + 0 | unknown section, empty in all 19 SAVWs (parser aborts if n > 0) |
| … | 4 + … | variables: each C string + 3 × `u32`, always `(0, 1, 0)` |
| … | 4 + n × 20 | **list 3**: saved objects, among them all PCKP |
| end | | `0xFF` up to a multiple of 64 |

A list entry has 20 bytes: **16-byte GUID + `u32` full instance ID**. 20 zero bytes are an **empty slot**: it occupies
an index, so it counts for the byte index.

Content over all world SAVWs (types resolved from the MREAs):

| List | longest list | Entries |
|---|---|---|
| 0 | 243 | 1401 CINE, 435 empty |
| 1 | 262 | 1338 MRLY, 595 empty |
| 2 | 99 | 545 DOOR, 124 empty |
| 3 | 87 | 110 PCKP, 106 empty, 474 not found in the script layers |

Most of the entries in list 3 that were not found are in area 0 (`universalarea`) on layer 58/59, the same in every
world. **Assumption:** cross-world objects and objects from the `SGEN` section (not evaluated).

Variables are names such as `PiratePlanet_GFShip`, `Mii Bobble Head`, `LandingSite_0G_GFPlanet_VistaBridge_A`.
**Assumption:** the three `u32` are minimum, maximum and starting value.

The order matches the lists in `retro_data_structures/formats/savw.py` (Cinematic Skips, Memory Relays, Layer
Toggles, Doors, Scans), except that MP3 has the doors instead of Layer Toggles and variables and list 3 at the end, and per entry
a GUID instead of a plain instance ID.

The game also has SAVWs in `FrontEnd.pak` (2) and `UniverseArea.pak` (1). They parse with the same format.

## 4. Runtime form

Evidence from the T10 snapshots (Norion block `W = 0x80A13AA0`, D2):

| Offset | Content |
|---|---|
| `W + 0x00` | `u64` MLVL ID |
| `W + 0x08` | pointer to a resource descriptor with `"SAVW"` and the SAVW ID of the world (`0x808C0800` → `… 53415657 … 732E1A63A1122AD3`) |
| `W + 0x0C` | unknown (`0x01FD0000`) |
| `W + 0x10` | pointer to the parsed SAVW object (`0x809886E0`) |
| `W + 0x14` | unknown (`0x01FFFFFF`) |
| `W + 0x18` | `0x400` = number of flags. **Assumption:** `reserved_vector<bool, 1024>` (size, then data) |
| `W + 0x1C` | 1024 bytes, byte `i` = Memory Relay `i` from list 1 |

The parsed SAVW object holds the lists as vectors `(count, capacity, pointer)` in file order:
`+0x00` areas, `+0x04` list 0, `+0x10` list 1, `+0x1C` list 2, `+0x28` list 3, `+0x34` scans,
`+0x40` unknown, `+0x4C` variables. Norion: 243, 149, 53, 33, 232, 0, 4 entries, as in the file.

**All set bytes from T10 are Memory Relays** in the room the player was in:

| World | Byte | List-1 entry | Room | Cause |
|---|---|---|---|---|
| Valhalla | 1 | MRLY `0x00020039` | `01_abandoned_hangar` | location 11 (measuring point) |
| Valhalla | 35 | MRLY `0x000201B2` | `01_abandoned_hangar` | already set before pickup 1 |
| Norion | 1, 6 | MRLY `0x000204E8`, `0x0002039D` | `01_gfplanet_landingsite` | set on arrival |
| Norion | 7 | MRLY `0x00020403` | `01_gfplanet_landingsite` | location 3 (measuring point) |
| Norion | 8 | MRLY `0x000202E0` | `01_gfplanet_landingsite` | location 4 (measuring point) |
| Norion | 118 | MRLY `0x00020534` | `01_gfplanet_landingsite` | set together with location 4 |
| Norion | 24, 116 | MRLY `0x000800AE`, `0x0008015A` | `0a_gfplanet_venttube` | between C2 and D2 (player in the Vent Tube) |

Checked before and rejected: sorting list 3 by GUID or instance ID, grouping by area, combinations
of the lists, simple hashes of the GUID. None matched the three measuring points.

Consequence for the client: the block does not contain only pickup flags (story relays, door logic etc. share it). Only
the byte from the table counts. List 1 is at most 262 entries long, bytes above stay 0 (**assumption**, not checked
live). Where the state of the list-3 objects lives at runtime is open; it is not needed for the checks.

## 5. Mapping location → byte

Per location from `PickupLocations.cs` (1–99, location 0 is dropped, E13): world via the MREA ID in the MLVL, full instance ID from
layer + local ID in the MREA, connection graph of the room, then:

**Pickup locations (89):** candidates are the MRLY that are reached from the PCKP via at most 3 connections with message `ACTV`.
"Its" MRLY is the one that additionally switches the PCKP off on load (`ACTV/DCTV → PCKP`). For all 89
there is exactly one, it is activated only from the pickup's chain, and it is always at depth 2
(`ACQU/ACTN → SRLY`, `RLAY/ACTV → MRLY`). Status **certain**. For 4 locations the same event sets further bytes
(`other_bytes` in the table): 64 (+231), 77 (+220), 87 (+5, +187), 95 (+108).

**SpecialFunction locations (10):** SPFN and the second PCKP have no outgoing connections of their own. A common trigger
(relay `SRLY`, mostly after an animation `ACKF`) sends `ACTN` to the SPFN and `IM00` to the PCKP. What is searched for is the
MRLY that this trigger (or up to two levels before it) activates with `ACTV` and that is activated only from there.
On load it does not switch the SPFN off, but starts a setup relay (`ACTV/ACTN → SRLY`). Status **probable**:
the pattern is unambiguous, but there is no back reference to SPFN/PCKP and it was not measured live.

| Location | World | SPFN | second PCKP (in SAVW list 3, index) | MRLY | Byte | Note |
|---|---|---|---|---|---|---|
| 9 | Norion | `0x000F01EE` | `0x000F026C` (30) | `0x000F01F1` | 53 | |
| 34 | Bryyo - Reptilicus | `0x000E032B` | `0x000E04BA` (69) | `0x000E031B` | 68 | byte 54 is set at the same moment |
| 42 | Bryyo - Reptilicus | `0x00210127` | `0x002103AB` (70) | `0x0021014C` | 109 | |
| 43 | Bryyo - Reptilicus | `0x102100CB` | `0x10210778` (73) | `0x0021036B` | 107 | MRLY sits 2 levels before the trigger (start of the sequence) |
| 62 | SkyTown, Elysia - Main | `0x00180165` | `0x001802E5` (80) | `0x00180045` | 81 | |
| 70 | SkyTown, Elysia - Pod | `0x0010035F` | `0x00100426` (45) | `0x0010019C` | 42 | |
| 73 | SkyTown, Elysia - Pod | `0x001C02F3` | `0x001C01DE` (52) | `0x001C00EA` | 81 | MRLY sits 1 level before the trigger |
| 79 | Pirate Homeworld - Research | `0x00070185` | `0x0007003A` (72) | `0x0007012B` | 45 | byte 176 is set at the same moment |
| 89 | Pirate Homeworld - Command | `0x000502A6` | `0x0005034A` (30) | `0x0005029D` | 10 | |
| 93 | Pirate Homeworld - Mines | `0x0003002B` | `0x000300F4` (33) | `0x0003002E` | 1 | |

For 34 and 79 the trigger activates two MRLY that are activated only from there. The chosen one has the load pattern
`ACTV/ACTN → SRLY` as for the other eight. For detection the choice does not matter; both bytes are set at the same time.

**Checks in the generator:** every location object exists with matching area and layer, exactly one object of the location is
in list 3, no byte is used by two locations of the same world. On a violation the generator aborts or marks
the location as `uncertain` (does not occur at present).

**Applies to all seeds (E12):** The patcher changes item properties and deletes or adds cutscene objects; the chains
pickup → relay → MRLY stay. The table from the patched T01 ISO is byte-identical to the table from the original.
**Assumption** for seeds with other items: progressive items and main-required variants only add connections
(`PickupPatches.cs:109-281`), which does not change the chosen MRLY. Not checked on a second seed.

## 6. Open points

1. **Live spot check (T13):** above all the 10 SpecialFunction locations (status "probable") and one location with
   `other_bytes`. The 89 pickup locations follow the same pattern as the three measuring points.
2. Meaning of `W + 0x0C`, `W + 0x14`, the empty section after the scans and the three `u32` per variable.
3. Where the state of list 3 (PCKP, GUID) lives at runtime, and what the second copy of the block in MEM1 is
   (`AP_LIVE_TESTS.md`, test D).
4. NTSC-U `RM3E01`: format probably the same, asset IDs and lists not checked.
