# AP live tests PAL: item giving, slot 47, slot 68, pickup state (T10)

As of 2026-11-23. Provides facts for the architecture question F-01 in `STATUS.md`.
Basis: `AP_MEMORY_MAP.md` (inventory `[[0x80680234]+0x24]+0x54+slot*0xC`, per slot `u32 amount, u32 max, u32 ?`, big endian)
and `AP_PATCHER_NOTES.md` (slots, hash table). All addresses are PAL `RM3P01`.

Legend of the measurement source: **[D]** = Dolphin 2609b (before the crash), **[P]** = PrimeHack. **All numbers in tests A to D come from [P].**
Only the preliminary measurement below is [D].

## Test environment

| Item | Dolphin [D] | PrimeHack [P] |
|---|---|---|
| Emulator, version | Dolphin 2609b, JIT64, D3D11 (`AP_DEV_SETUP.md` section 6) | PrimeHack v1.0.9 (folder `PrimeHack.v1.0.9`, user data in `%APPDATA%\Dolphin Emulator`) |
| CPU Clock Override | default (off), confirmed by the user | **on, 500 %** (`OverclockEnable = True`, `Overclock = 5.0`) |
| Disc speed ("Emulate Disc Speed") | default | **off** (switched off by the user) |
| Game ISO | `out/t01_IVG2J7OR.iso` (seed IVG2J7OR, starter preset), outside the repo | same ISO. A new game was created in PrimeHack, start Valhalla, Docking Bay 5 |
| Detection of the seed ISO | – | starting inventory matches: PowerBeam (0), ChargeUpgrade (3), Bomb (10), CombatVisor (11), ScanVisor (12), DoubleJump (15), MorphBall (32) each 1/1 |
| Measurement tool | dolphin-memory-engine 1.3.0 (Python 3.12), throwaway scripts in the scratchpad outside the repo | same. Snapshots (MEM1 24 MB + MEM2 64 MB) take 0.2 s and are not in the repo |
| Save | throwaway save (confirmed by the user) | new profile, throwaway save |

Connection to PrimeHack confirmed: game ID `RM3P01`, CPlayerState base `PS = 0x80995B20` (the same as in Dolphin), world, CPlayer vtable as in
`AP_MEMORY_MAP.md`. The pointer `[0x80680234]` (CGameState) changes on loading (`0x80998DC0`, `0x80A234E0`, `0x80A10880`), `PS` stayed the same.

## Log

| Time (2026-11-23) | Event |
|---|---|
| about 20:00 | Backup of the Wii save from Dolphin [D] (scratchpad, not in the repo). The save in the old Dolphin was from 18:56 (T01/T02), not from this session |
| 20:10–20:11 | [D] test C/D **step 1**: Bryyo Fire, Main Lift, pickup 17 (Missile Expansion according to the seed). Snapshot 1 and slots 62–69 read, logger started (20:11:19, 70 slots every 0.25 s) |
| between 20:11 and 20:14 | **Crash of Dolphin 2609b [D]** during **test C/D, between step 1 and step 2**. The user was standing in front of the pickup. **No write** was running; nothing was written in the whole [D] session. Before that only reading: one snapshot (88 MB in 0.2 s) and 70 slots 4× per second. Settings: default, **without** Clock Override (according to the user), disc speed default. `dolphin.log` is empty (0 bytes). Cause unknown. A connection with reading via Memory Engine cannot be ruled out and is not proven |
| 20:14:27 | PrimeHack [P] started. The old logger was stopped |
| about 20:22–20:25 | [P] new game, test C/D steps 1 and 2 (pickup 1, Valhalla) |
| 20:25:27 | Pickup 1 collected |
| 20:29–20:30 | Save, reload (reset), snapshot 4 |
| 20:35:29 | Pickup 2 (Norion, Docking Hub Alpha) collected |
| 20:36:43–20:41:01 | Test A: writes to slots 4, 7, 20, 1 |
| about 20:45–20:46 | Save, reload (snapshots C1 before, C2 after loading) |
| 20:47:20–20:51:27 | Test B: writes to slot 47 (two passes), probe 47/43/53/54, persistence test, reset |
| 20:54:07 | Pickup 3 (Norion, Docking Hub Alpha, Missile Expansion) collected |

**No crash with PrimeHack [P]**, not even during the writes. No [P] test ran without the 500 % Clock Override.

## Preliminary measurement [D], repeated with [P] for confirmation

Read with [D] before the crash (save Norion/Bryyo, three pickups, no Missile Launcher). Confirmed with [P] in a fresh game, as far as stated
below.

| Slot | Name | Amount/max [D] | [P] confirmed |
|---|---|---|---|
| 21 | ItemPercentage | 3/103 | yes, 0/100 at game start, +1 per pickup |
| 47, 48, 49, 53–61 | free or CannonBall, ActivateMorphballBoost | each 0/1 | yes (fresh game). After loading from the save: 47, 48, 49 = 0/0, 53–61 stay 0/1 |
| 52 | EnergyCellsUsed | 0/9 | yes |
| 43 | (free) | 0/0 | yes |
| 68 | Stat_TinCanHighScore | 10/10 (two expansions without launcher) | yes, 5 per locked Missile Expansion (test C) |
| 69 | Stat_TinCanCurrentScore | 0/0 | yes, 0/0 |

## Test A: item giving by writing the inventory directly

**Setup:** [P], Norion, Docking Hub Alpha, ingame. One write per item with `dolphin_memory_engine.write_bytes` to `PS + 0x54 + slot*0xC`
(amount and max as two `u32`). Then 2.5 s of reading (the value stayed the same); the user checked function, HUD and pause menu in the game. At the end save and
reload (reset, Continue Game), then read the memory and check in the game. The tests ran in this order; the items stayed active.

| Item | Slot (address) | Written (amount/max), before 0/0 | Works | HUD | Pause menu | Survives saving + reloading |
|---|---|---|---|---|---|---|
| Missile (expansion: max raised) | 4 (`0x80995BA4`) | 5/5 | yes (shot, amount 5 → 4, 3, 2, 1, 0; refills to 5/5) | yes | yes | yes (memory 4/5 after reload, max 5 kept) |
| Grapple Lasso | 7 (`0x80995BC8`) | 1/1 | yes | yes | yes | yes (memory 1/1 after reload) |
| Energy Tank | 20 (`0x80995C64`) | 1/1 | yes (an empty tank appears, fills up according to the user) | yes (empty tank) | yes (reported by the user as "I think so", uncertain) | yes (memory 1/1 after reload) |
| Beam upgrade Plasma Beam | 1 (`0x80995B80`) | 1/1 | yes (MP3 has fixed beams, switching only to the Hyper Beam) | yes | yes | yes (memory 1/1 after reload) |

According to the user, all four were still present in the game after reloading.

**Side effects and observations:**
- ItemPercentage (slot 21) stayed unchanged for all writes (2/102). It only rises through real pickups.
- Missile (slot 4) works without the Missile Launcher item. **The write to slot 4 triggers the transfer of the locked missiles:** at the next
  Missile pickup (20:54:07, pickup 3) slot 68 was set from 5/5 to 0/0 and slot 4 from 5/5 to **15/15** (5 from slot 68 plus 5 from the pickup plus the
  5 written). This is the same mechanism that would release the locked missiles when the launcher is really picked up. Without the write
  slot 68 would have shown 10/10 after the second expansion (as [D] before the crash).
- Stat_DataSaves (slot 65) rises with every save (1, 3, 4 read).
- No crash, no wrong display in the HUD, no resetting of the values by the game.

**Result:** Missile, Grapple Lasso, Energy Tank and Plasma Beam can be given by writing directly into the inventory slot and take effect at once, show
up in the HUD and pause menu and are kept after saving and reloading.

## Test B: slot 47

**Setup:** [P], Norion, ingame, slot 47 = `PS + 0x288` = `0x80995DA8`. Pass 1: write only the amount (first four bytes), max stayed 0. Pass 2: amount and
max set to the same value. Read each time at once, after 0.5 s and after 3 s. Probe with 4 ms sampling (slots 47, 43, 53, 54, each 7/7). Persistence: slot 47 at 0/65535,
plus slot 43 = 65535/65535, slot 53 = 1000/1000, slot 54 = 7/7, save, reload, read.

**Table written value → read value** (amount/max):

| Written (amount) | Pass 1, max=0: at once → after 0.5 s and 3 s | Pass 2, max=value: at once → after 0.5 s and 3 s | After saving + reloading |
|---|---|---|---|
| 1 | 1/0 → 0/0 | 1/1 → 0/1 | not checked individually (live always 0) |
| 2 | 2/0 → 0/0 | 2/2 → 0/2 | not checked individually (live always 0) |
| 50 | 50/0 → 0/0 | 50/50 → 0/50 | not checked individually (live always 0) |
| 255 | 255/0 → 0/0 | 255/255 → 0/255 | not checked individually (live always 0) |
| 1000 | 1000/0 → 0/0 | 1000/1000 → 0/1000 | not checked individually (live always 0) |
| 65535 | 65535/0 → 0/0 | 65535/65535 → 0/65535 | **0/0** (saved with 0/65535, because the amount dropped to 0 live) |

- **The game resets the amount in slot 47 to 0 after about 18 ms (one frame)**, even if the max is just as high. Measured with 4 ms sampling:
  value 7 was there at 0 ms, at 18 ms it was 0.
- **The max in slot 47 stays live at every value up to 65535** (no clamping seen). After saving and reloading the max is 0 again.
- After loading from the save, slot 47 is always 0/0; in the fresh game it was 0/1.
- Neighbours 46 and 48 stayed 0/0, ItemPercentage stayed 2/102. No crash, no side effect that the user would have reported.

**Side measurement** (same probe, for comparison with the other free slots):

| Slot | Written | After 1 s live | After saving + reloading |
|---|---|---|---|
| 43 (`0x80995D78`) | 7/7, then 65535/65535 | stays (7/7, 65535/65535) | **1/1** |
| 53 (`0x80995DF0`) | 7/7, then 1000/1000 | stays | **0/0** |
| 54 (`0x80995DFC`) | 7/7 | stays | **1/1** |

One bit per slot would explain the pattern (7 and 65535 are odd → 1, 1000 is even → 0). **This is an assumption**; no further value (e.g. 2 or 3) was
written. The test slots were set back to their original values afterwards (43 = 0/0, 53 and 54 = 0/1).

**Result:** An amount in slot 47 does not last a frame, and the max of slot 47 does not survive reloading, so slot 47 can carry values neither live nor through the save.

## Test C: slots 68 and 69

**Setup:** [P], Valhalla, Docking Bay 5. Slots 68 and 69 read at three points in time. The pickup was a Missile Expansion (seed location "Pickup (Energy Cell)" in Docking Bay 5,
pickup 11). The player had no Missile Launcher (slot 4 = 0/0), so the expansion was "locked".

| Point in time | Slot 68 | Slot 69 | Slot 4 (Missile) | Slot 21 (ItemPercentage) |
|---|---|---|---|---|
| 1. In the game (after game start) | 0/0 | 0/0 | 0/0 | 0/100 |
| 2. Before collecting (20:24, snapshot 1) | 0/0 | 0/0 | 0/0 | 0/100 |
| 3. After collecting (20:25:27) | **5/5** | 0/0 | 0/0 | 1/101 |

Slot 68 and slot 21 changed in the same logger tick. For comparison [D] before the crash: slot 68 = 10/10 with two locked expansions.
Slot 69 (Ship Missile Expansion) was not measured; there was no Ship Missile pickup.

**Contradiction resolved:** `AP_PATCHER_NOTES.md` (section 2.5) is right: the ammo of a locked Missile Expansion is in **slot 68** (5 per expansion).
`AP_MEMORY_MAP.md` (line 117 and 189–190: "`TemporaryMissile` not in memory") is thereby outdated. Slot 68 is transferred to slot 4 when a Missile Expansion is picked up,
as soon as slot 4 is no longer 0 (measured in test A, 20:54:07).

**Result:** Slot 68 rises by 5 with a locked Missile Expansion, slot 69 stays 0/0.

## Test D: pickup state in memory

**Setup:** [P]. Snapshots of MEM1 and MEM2 (`0x80000000`–`0x817FFFFF` and `0x90000000`–`0x93FFFFFF`), each two directly one after the other (3 s apart) as a noise pair:

| Name | Point in time | Place |
|---|---|---|
| A1, A1b | before pickup 1 | Valhalla, Docking Bay 5 |
| A2, A2b | after pickup 1 (Missile Expansion) | Valhalla, Docking Bay 5 |
| A3, A3b | after the flight to Norion and back | Valhalla, Docking Bay 5 |
| A4, A4b | after saving and reloading | Valhalla |
| B1, B1b / B2, B2b | before / after pickup 2 (Screw Attack, pickup 4) | Norion, Docking Hub Alpha |
| C1 / C2 | before / after saving and reloading (test A) | Norion |
| D1, D1b / D2, D2b | before / after pickup 3 (Missile Expansion, pickup 3) | Norion, Docking Hub Alpha |

"Leave the room and come back" was not possible in Docking Bay 5, hence the flight to Norion and back (reloads the world).

**PrimeHack as a source of interference and noise:** at idle, **124 528 words in MEM1 and 36 549 in MEM2** change between two snapshots 3 s apart (A1 against A1b).
How much of this is PrimeHack camera and control values was not separated. The noise pair was therefore used as a filter (addresses that change in the idle pair do not count).
The block found (below) was unchanged in all idle pairs (A1/A1b, B1/B1b, D1/D1b, D2/D2b). PrimeHack writes do not hit it.

**Ruled out:**
- **ItemPercentage** (slot 21): rises with every pickup, but does not say which one.
- **Raw diff A1 → A2:** too noisy. 1 433 words in MEM1 change stably (A2 = A3 = A4); most of them are freed heap and static data, 0 in MEM2.
- **Pointer chains from `[0x80680234]`** (depth 4, 39 stable candidates): only resource objects (`STRG` texts) and allocator remains.
- **Save file `save.bin`** (65 536 bytes, bit-packed with checksum): not decoded.
- Single-bit changes in memory: 573 hits in MEM1, mostly heap and allocator noise.

**Found (search for the world ID as 8 bytes in memory, 37 hits. Of the 26 checked in the heap and its surroundings only one changed around pickup 1; the other hits were not evaluated):** per world there is a heap block with this structure
(addresses using Valhalla as an example, `W = 0x80A1FD40`):

| Offset | Content |
|---|---|
| `W − 4` | `0xEAEAEAEA` (guard value of the allocator) |
| `W + 0x00` | MLVL asset ID of the world as `u64` (Valhalla `0xC133F919C108BDF9`, Norion `0x6FB8EF2A9523C343`) |
| `W + 0x18` | `0x00000400` (size) |
| `W + 0x1C` … `W + 0x41B` | **1024 bytes of flags**, in the game only the values 0 or 1 were seen. Below, byte index from `W + 0x1C` |

The block is in the heap and moves: Valhalla `0x80A1FD40` before the first load, `0x80A49CC0` afterwards. It is found via the world ID plus `0x400` at `+0x18` plus `0xEAEAEAEA` at `−4`.
There is a second copy with the same content in MEM1 (Valhalla `0x811ED3C0`), purpose unknown.

**Measured values, pickup → changed byte** (no other change in the block):

| Pickup (location) | World, block `W` | Byte index before → after | Address | Survives |
|---|---|---|---|---|
| 11, Docking Bay 5, Missile Expansion (seed) | Valhalla, `0x80A1FD40` | 1: `0x00` → `0x01` | `0x80A1FD5D` | planet change yes, saving + reloading yes (block moved to `0x80A49CC0` in the process, same content) |
| 4, Docking Hub Alpha, Grapple Lasso location (seed: Screw Attack) | Norion, `0x80A13AA0` | 8: `0x00` → `0x01` | `0x80A13AC4` | saving + reloading yes (C1 → C2, block stayed at the same address, same content) |
| 3, Docking Hub Alpha, Missile Expansion | Norion, `0x80A13AA0` | 7: `0x00` → `0x01` | `0x80A13AC3` | not checked |

- Each of the three pickups set **exactly one** new byte in the 0x460-byte block. At idle, on a planet change and on reloading only the pointer header changes.
- The two pickups in the same room (Docking Hub Alpha, pickups 3 and 4) have **adjacent** bytes (7 and 8). That fits "byte index = pickup number + 4" for Norion, but only two points back it.
  In Valhalla pickup 11 is on byte 1, so the offset differs per world.
- **The block also holds other states:** Norion already had bytes 1 and 6 set before pickup 2, and between pickup 2 and saving bytes 24, 116 and 118 were added
  (in that time the user tried out Grapple Lasso and the beam, among other things). So a pickup's byte is not the only byte set, and the mapping of a byte to a location cannot
  be read from the block alone.

**Second pickup in another world/room, same pattern?** Yes: Valhalla (pickup 11) and Norion (pickups 3 and 4) each set exactly one byte in the same block type.

**Result:** The state of a collected pickup is stored as one byte in the 1024-byte flag block of the respective world (found via world ID + `0x400` + `0xEAEAEAEA`),
confirmed on three pickups in two worlds, while the mapping byte ↔ location (and the persistence of pickup 3) is open.

## Conclusion for F-01

Writing directly into the inventory slot (variant c) works for Missile (slot 4), Grapple Lasso (slot 7), Energy Tank (slot 20) and Plasma Beam (slot 1): ability, HUD and pause menu react at once, the values
survive saving and reloading, ItemPercentage does not change in the process, and a write to slot 4 triggers the transfer from slot 68 to slot 4 at the next Missile pickup.
Slot 47 carries no marker: the game sets its amount to 0 after about 18 ms, its max (stable live up to 65535) is 0 again after reloading, so variant (a) with slot 47 as a bit mask is ruled out by the measured values.
Slots 43 and 53–61 hold every written value live, but keep only one bit after reloading, and the patcher hash method does not reach them.
Variant (d) has a proven core: per world there is a 1024-byte flag block (anchor: world ID `u64` + `0x400` at `+0x18` + `0xEAEAEAEA` at `−4`), in which each of the three tested pickups set exactly one byte,
which was checked after reloading for two of the three pickups and was kept, while the block moves in the heap, also contains other states and is mapped for only two locations (Docking Hub Alpha, pickups 3 and 4: bytes 7 and 8).
Open are the mapping of all 99 locations to byte indices (derivable from patcher/MREA, or only measurable by collecting every location) and the question whether the byte is set for every item type, including the 10 locations of type `SpecialFunction`.

## Open points

1. Mapping byte index ↔ pickup index for all 99 locations (hypothesis Norion: pickup number + 4, Valhalla pickup 11 → 1, different per world).
2. Check of the 10 `SpecialFunction` locations and of location 0 (never patched) in the block.
3. Persistence of pickup 3 after saving/reloading, and behaviour of the block when loading a save with more than one world visited.
4. Measure slot 69 with a locked Ship Missile Expansion. Amount per expansion (Ship Missile: 3?) and whether slot 69 follows the pattern of slot 68.
5. Whether the max of slot 47 survives reloading when set by a real pickup (hash `0x51E1A9FB`) (here only checked by direct writing).
6. Bits per slot for 43 and 53–61 after loading (only 1 bit assumed).
7. NTSC-U (`RM3E01`) and the measurement without 500 % Clock Override are not checked. All numbers above come from PrimeHack with 500 % Clock Override.
