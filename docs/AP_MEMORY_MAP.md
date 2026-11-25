# AP memory mapping: Metroid Prime 3 in Dolphin (T02)

As of 2026-11-23. Basis: `randovania/game_connection/connector/corruption_remote_connector.py`,
`prime_remote_connector.py`, `executor/dolphin_executor.py` and the version tables from
**open-prime-rando 0.15.1** (`venv/Lib/site-packages/open_prime_rando/dol_patching/…`, below `OPR/…`).
Checked live with **PAL `RM3P01`** (Rev 0), seed `IVG2J7OR` from T01, Dolphin 2609b, dolphin-memory-engine 1.3.0.

> **Summary**
> - For PAL the build string, current world, the detection "ingame/menu/loading" and the inventory are **confirmed live**.
>   On collecting, `ScrewAttack` changes from 0/0 to 1/1 and `ItemPercentage` from 1/101 to 2/102.
> - **Today Randovania can neither give items into the game for MP3 nor detect location checks.**
>   Neither is implemented in the connector (sections 4 and 5). For the AP client (T06/T07) these are the
>   two gaps that have to be built new.
> - T33 verifies the NTSC-U (`RM3E01`) client addresses in the DOL and compares its data against PAL.
>   See [AP_NTSC.md](AP_NTSC.md) for the evidence and live results. NTSC-J (`RM3J01`) values come from code.

Conventions:
- All addresses are virtual Wii addresses (MEM1 `0x80000000–0x81800000`, `dolphin_executor.py:15-16`). All values
  are **big endian**.
- `[X]` means: read the 4-byte pointer at address X. `[X]+off` means: read the pointer, then add the offset.
  This is how the executor works too: a `MemoryOperation` with `offset` first reads the pointer at `address` and then adds
  the offset (`dolphin_executor.py:84-92, 113-132`).
- Source `OPR/corruption/dol_versions.py` = `open_prime_rando/dol_patching/corruption/dol_versions.py`.

---

## 1. Version table (global addresses per region)

Source: `OPR/corruption/dol_versions.py:6-65`. The connector picks the version by the build string
(`randovania/game_connection/builder/prime_connector_builder.py:40,64-100`).

| Field | NTSC-U "Wii NTSC" (RM3E01) | PAL "Wii PAL" (RM3P01) | NTSC-J "Wii NTSC-J" (RM3J01) | Source |
|---|---|---|---|---|
| `build_string_address` | `0x805822B0` | `0x805843A8` | `0x80587C2C` | `dol_versions.py:10,34,51` |
| `build_string` | `…2007/07/27 13:13 Build v3.436 (MP3)` | `…2007/08/24 16:52 Build v3.453 (mp3)` | `…2007/11/12 14:15 Build v3.495 (jpn)` | `dol_versions.py:11,35,52` |
| `game_state_pointer` | `0x8067DC0C` | `0x80680234` | `0x80683A7C` | `dol_versions.py:14,38,55` |
| `cplayer_vtable` | `0x80592C78` | `0x80595238` | `0x80598650` | `dol_versions.py:15,39,56` |
| `cstate_manager_global` | `0x805C4F70` | `0x805C7570` | `0x805CAA30` | `dol_versions.py:16,40,57` |
| `powerup_functions.add_power_up` | `0x8019111C` | `0x80191E2C` | `0x801932D0` | `dol_versions.py:26,43,60` |
| `powerup_functions.incr_pickup` | `0x801913A0` | `0x801920B0` | `0x80193554` | `dol_versions.py:27,44,61` |
| `powerup_functions.decr_pickup` | `0x8019151C` | `0x8019222C` | `0x801936D0` | `dol_versions.py:28,45,62` |
| `string_display` | `None` | `None` | `None` | `dol_versions.py:17,41,58` |
| `sda2_base` / `sda13_base` | `0x806869C0` / `0x806801C0` | `0x80688FE0` / `0x806827C0` | `0x8068C840` / `0x80686000` | `dol_versions.py:12-13,36-37,53-54` (not used by the connector) |
| **Status** | **T33 DOL comparison** (see [AP_NTSC.md](AP_NTSC.md) for scope) | **confirmed live** (except `powerup_functions`, `sda*`) | **code only** | |

---

## 2. Field table (pointer chains)

PAL example addresses come from the live run. The dynamic addresses (heap) change from session to session.

| Field | Address / pointer chain | Type | Region | Status | Source (file:line) |
|---|---|---|---|---|---|
| Game ID | `0x80000000`, 6 bytes | ASCII | all | PAL live: `RM3P01` | Dolphin standard (not read by the connector) |
| Build string (version detection) | `build_string_address`, `len(build_string)` bytes | ASCII | see table 1 | PAL live: matches | `prime_remote_connector.py:86-104`, `prime_connector_builder.py:67-100` |
| Layout UUID | bytes `[6:22]` of the build string | 16-byte UUID | all | PAL live: **not set** (original text `roidBuildInfo!#$`) → `INVALID_UUID` | `prime_remote_connector.py:92-101` |
| Current world (MLVL asset ID) | `[game_state_pointer] + 0x8`, 8 bytes | `u64` (`>Q`) | see table 1 | PAL live: Valhalla, Norion, FrontEnd | `corruption_remote_connector.py:48-49,64-65,72`; comparison `prime_remote_connector.py:110-136` |
| "Pending op" byte | `cstate_manager_global + 0x2`, 1 byte | `u8` | see table 1 | PAL live: **always `0xFF`** (menu, loading, ingame) | `corruption_remote_connector.py:73,87-88`, `prime_remote_connector.py:254` |
| CPlayer pointer | `[cstate_manager_global + 0x28] + 0x2184`, 4 bytes | pointer | see table 1 | PAL live: menu/loading = `0`, ingame e.g. `0x80B81AE0` | `corruption_remote_connector.py:67-74,77` |
| CPlayer vtable (ingame check) | `[[cstate_manager_global + 0x28] + 0x2184]`, 4 bytes | pointer | see table 1 | PAL live: `0x80595238` = expected | `corruption_remote_connector.py:79-85`, `prime_remote_connector.py:127-133` |
| CPlayerState base | `[game_state_pointer] + 0x24` = pointer slot; `PS = [[game_state_pointer] + 0x24]` | pointer | see table 1 | PAL live: `PS = 0x80995B20` (the same in all reads) | `corruption_remote_connector.py:95-102` |
| Inventory slot `item_id` | `PS + 0x54 + item_id * 0xC`, 8 bytes | `u32 amount`, `u32 capacity` (`>II`) | all | PAL live, see section 3 | `corruption_remote_connector.py:37-41,104-111`, `prime_remote_connector.py:151-166` |
| Give item (capacity) | function call `add_power_up(PlayerState, item_id, delta)` | PPC function | see table 1 | code only, **not usable in MP3** (section 4) | `OPR/all_prime_dol_patches.py:202-213`; `corruption_remote_connector.py:117-125` |
| Give item (amount) | `incr_pickup` / `decr_pickup(PlayerState, item_id, n)` | PPC function | see table 1 | code only, **not usable in MP3** | `OPR/all_prime_dol_patches.py:216-227` |

Derivation of the inventory offset (`corruption_remote_connector.py:37-41`):
`0x50` (powerup vector in CPlayerState) + `0x4` (data pointer/size of the vector) + `item_id * 0xC` (size of an
entry). Only the first 8 bytes of an entry are read (`amount`, `capacity`). What is in the remaining 4 bytes
is not documented.

---

## 3. Inventory: item ID → offset

Item IDs from `randovania/games/prime3/logic_database/header.json` (`resource_database.items[*].extra.item_id`).
Offset relative to `PS`. PAL absolute addresses apply to `PS = 0x80995B20` from the live run. Only IDs `< 1000` are in
memory (`prime_remote_connector.py:155`). IDs from 1000 on are pure logic resources.

| item_id | Name (`header.json`) | Offset from `PS` | PAL address (live) | max. capacity |
|---|---|---|---|---|
| 0 | PowerBeam | `+0x054` | `0x80995B74` | 1 |
| 1 | PlasmaBeam | `+0x060` | `0x80995B80` | 1 |
| 2 | NovaBeam | `+0x06C` | `0x80995B8C` | 1 |
| 3 | ChargeUpgrade (Charge Beam) | `+0x078` | `0x80995B98` | 1 |
| 4 | Missile | `+0x084` | `0x80995BA4` | 255 |
| 5 | IceMissile | `+0x090` | `0x80995BB0` | 1 |
| 6 | Seekers | `+0x09C` | `0x80995BBC` | 1 |
| 7 | GrappleBeamPull (Lasso) | `+0x0A8` | `0x80995BC8` | 1 |
| 8 | GrappleBeamSwing | `+0x0B4` | `0x80995BD4` | 1 |
| 9 | GrappleBeamVoltage | `+0x0C0` | `0x80995BE0` | 1 |
| 10 | Bomb | `+0x0CC` | `0x80995BEC` | 1 |
| 11 | CombatVisor | `+0x0D8` | `0x80995BF8` | 1 |
| 12 | ScanVisor | `+0x0E4` | `0x80995C04` | 1 |
| 13 | CommandVisor | `+0x0F0` | `0x80995C10` | 1 |
| 14 | XRayVisor | `+0x0FC` | `0x80995C1C` | 1 |
| 15 | DoubleJump (Space Jump Boots) | `+0x108` | `0x80995C28` | 1 |
| 16 | ScrewAttack | `+0x114` | `0x80995C34` | 1 |
| 17 | SuitType | `+0x120` | `0x80995C40` | 6 (connector: ≥5 = "has item", `corruption_remote_connector.py:142-152`) |
| 18 | Energy | `+0x12C` | `0x80995C4C` | 1499 (live 0/0 although the HUD shows 99: **not** the health energy) |
| 19 | HypermodeEnergy | `+0x138` | `0x80995C58` | 0 |
| 20 | EnergyTank | `+0x144` | `0x80995C64` | 14 |
| 21 | ItemPercentage | `+0x150` | `0x80995C70` | 255 |
| 22 | Fuses (Energy Cells Total) | `+0x15C` | `0x80995C7C` | 9 |
| 23–31 | Fuse1 … Fuse9 (Energy Cell 1–9) | `+0x168` … `+0x1C8` (step `0xC`) | `0x80995C88` … `0x80995CE8` | 1 |
| 32 | MorphBall | `+0x1D4` | `0x80995CF4` | 1 |
| 33 | BoostBall | `+0x1E0` | `0x80995D00` | 1 |
| 34 | SpiderBall | `+0x1EC` | `0x80995D0C` | 1 |
| 35–42 | HyperModeTank, HyperModeBeam, HyperModeMissile, HyperModeBall, HyperModeGrapple, HyperModePermanent, HyperModePhaaze, HyperModeOriginal | `+0x1F8` … `+0x24C` | `0x80995D18` … `0x80995D6C` | 1 |
| 44 | ShipGrapple | `+0x264` | `0x80995D84` | 1 |
| 45 | ShipMissile | `+0x270` | `0x80995D90` | 11 |
| 46 | FaceCorruptionLevel | `+0x27C` | `0x80995D9C` | 4 |
| 48 | CannonBall | `+0x294` | `0x80995DB4` | 1 |
| 49 | ActivateMorphballBoost | `+0x2A0` | `0x80995DC0` | 1 |
| 50 | HyperShot | `+0x2AC` | `0x80995DCC` | 2 |
| 51 | CommandVisorJammed | `+0x2B8` | `0x80995DD8` | 1 |
| 52 | EnergyCellsUsed | `+0x2C4` | `0x80995DE4` | 9 |
| 62–67 | Stat_EnemiesKilled, Stat_ShotsFired, Stat_DamageReceived, Stat_DataSaves, Stat_HypermodeUses, Stat_CommandoKills | `+0x33C` … `+0x378` | `0x80995E5C` … `0x80995E98` | 99999 |
| 68 | Stat_TinCanHighScore (locked Missiles, +5 per Missile Expansion) | `+0x384` | `0x80995EA4` | 99999 (17 saved bits each for amount and capacity) |
| 69 | Stat_TinCanCurrentScore | `+0x390` | `0x80995EB0` | 99999 (unsaved, reloads as 0/0) |
| 1000–1003 | MissileLauncher, ShipMissileLauncher, TemporaryMissile, TemporaryShipMissile | – (logic IDs; locked Missiles are stored in slot 68) | – | – |

IDs 43, 47 and 53–61 are missing in `header.json`. The slots exist in the array because it reaches at least ID 69. Their content
was not checked.

Note on `get_inventory` (`prime_remote_connector.py:154-160`): the memory ops are only created for IDs `< 1000`,
but are then zipped with **all** items. This only works because the IDs from 1000 on come last in `header.json`.

---

## 4. Giving items into the game (Randovania's mechanism)

**Not implemented for MP3.** The general Prime mechanism (MP1/MP2) is a *remote code execution*:

1. The connector builds PPC instructions that call `add_power_up` and `incr_pickup` with `item_id` and delta
   (`OPR/all_prime_dol_patches.py:180-227`, called in `corruption_remote_connector.py:113-126`).
2. `create_remote_execution_body` assembles these instructions at the address
   `string_display.update_hint_state + prologue` (`OPR/all_prime_dol_patches.py:242-265`).
3. It writes the code there and sets `cstate_manager_global + 0x2 = 0x01` (`prime_remote_connector.py:246-258`).
4. A hook built into the DOL by the patcher (`apply_remote_execution_patch`, `OPR/all_prime_dol_patches.py:238-239`)
   checks this byte in every frame, executes the code and resets the byte to `0`
   (`OPR/all_prime_dol_patches.py:66-128`).
5. Counting is done via a "magic item": its `capacity` is the number of remote items already given
   (`prime_remote_connector.py:201-233`).

Why this does not work in MP3:
- `string_display = None` for all three MP3 versions (`dol_versions.py:17,41,58`). So there is neither a target address
  nor a HUD text.
- `remote_execution_patch_start` and `_load_player_state` raise a `ValueError` for `Game.CORRUPTION`
  (`OPR/all_prime_dol_patches.py:82,177`).
- `CorruptionRemoteConnector.execute_remote_patches` raises a `RuntimeError` (`corruption_remote_connector.py:139-140`),
  `receive_remote_pickups` returns a fixed `False` (`:131-137`), `_dol_patch_for_hud_message` raises (`:128-129`),
  `multiworld_magic_item` raises `NotImplementedError` (`:51-54`).
- The MP3 patcher (`MP3Randomizer`) builds in no hook. Live, the byte `cstate_manager_global + 0x2` on PAL is
  permanently `0xFF`, so it is not a flag that a hook resets. Therefore `current_game_status` would **always** hold
  `has_pending_op = True` (`corruption_remote_connector.py:87-88`), and `update()` would never reach the multiworld part
  (`prime_remote_connector.py:336-340`).
- The layout UUID is not written into the build string (live: original text). The connector therefore sets
  `INVALID_UUID` (`prime_remote_connector.py:97-99`).

**Consequence for T07 (gap):** The AP client needs its own way to give items. Options:
- (a) **Write directly:** set `amount`/`capacity` in the slot `PS + 0x54 + id*0xC`. That is simple, but side effects
  are unchecked, e.g. for HUD, weapon unlocking, Energy Tanks (refill energy?), `ItemPercentage` and saving.
  This has to be tested live in T07.
- (b) **Rebuild the remote execution hook for MP3:** patcher extension plus MP3 addresses for `update_hint_state` or another
  per-frame hook and for CStateManager→PlayerState. A clean, but much larger effort.

---

## 5. Location check detection

### How Randovania does it today

**Not at all; there is no way for MP3.** The generic flow in `PrimeRemoteConnector.known_collected_locations`
(`prime_remote_connector.py:168-199`) reads the magic item. Its `amount - 1` is the `PickupIndex` of the last
collected foreign pickup. It then resets it to 0 via a remote patch and reports `PickupIndexCollected`
(`:360-366`). For MP3:
- `multiworld_magic_item` raises `NotImplementedError` (`corruption_remote_connector.py:51-54`).
- The patcher creates no magic item pickups, and remote patches do not work (section 4).
- The connector only reports the **region** (`PlayerLocationChanged`) and the **inventory** (`InventoryUpdated`)
  (`prime_remote_connector.py:328-335, 354-358`). Even for that `update()` would have to work. Because
  `multiworld_magic_item` raises and `has_pending_op` (see above) is always true, one never gets to
  `_multiworld_interaction`.

**Named gap:** There is no address and no flag that identifies a single pickup location. The room (area)
is not read by the connector, only the world.

### What can be measured live (PAL)

Every collected pickup increases `ItemPercentage` (ID 21) by 1, in `amount` **and** `capacity`
(0/100 → 1/101 → 2/102). This fits with every pickup in `pickup-database.json` also giving `"ItemPercentage": 1`
(e.g. line 137). This counter is the only value that changes with **every** pickup. A locked Missile Expansion
(without the Missile Launcher) also adds 5 to both amount and capacity in slot 68 while slot 4 stays at 0/0.
The game transfers the locked ammo to slot 4 at the next Missile pickup once slot 4 is nonzero
([AP_LIVE_TESTS.md](AP_LIVE_TESTS.md), tests A and C). Slot 68 saves 17 bits each for amount and capacity.
Slot 69 stayed at 0/0 in test C and reloads as 0/0 because it is unsaved
([AP_SLOT_LIMITS.md](AP_SLOT_LIMITS.md), sections 3 and 4).

### Proposal for the AP client (T05/T06)

1. **Short term (heuristic, without patcher change):** poll every 0.5 s. If `ItemPercentage.amount` changes, the
   inventory is compared before/after and the matching location is searched with the current world plus the placement from the seed.
   This is ambiguous if several locations in a world carry the same item (e.g. Missile Expansions, AP foreign items)
   or a pickup changes only `ItemPercentage`. It is not enough for the MVP, but usable as a plausibility check.
2. **Recommended:** every pickup additionally gives a **unique counter item**, for example an unused slot
   (43, 47, 53–61) with `amount = location index + 1` as with the MP1/MP2 magic item. Alternatively one item of its own per location group.
   The client reads the slot, reports the check and resets it to 0 by direct writing. This needs a
   patcher extension in T05 and a live test whether unused slots stay stable and are saved too.
3. **Not investigated:** layer or Memory Relay states per room (CWorldLayerState), through which the game remembers which
   pickups are gone. That would be the patcher-free solution, but Randovania has no addresses for it.

---

## 6. Ingame vs. menu / loading screen

Connector procedure (`corruption_remote_connector.py:56-89`, `prime_remote_connector.py:116-136`):
**ingame** ⇔ the CPlayer pointer is valid **and** its vtable is `cplayer_vtable` **and** the MLVL ID belongs to a
region in the database. Otherwise `None` is reported, i.e. not ingame.

PAL measurements (watcher log, 0.5 s polling):

| State | MLVL `[gsp]+8` | CPlayer pointer | vtable ok | Inventory |
|---|---|---|---|---|
| Title / Game Select / menu | `0xF4A9F72C65FBAE26` (FrontEnd, no region) | `0x0` | no | all 0/0 |
| Intro text "Life-Support Status" / landing approach | `0xC133F919C108BDF9` (Valhalla) | valid, vtable ok | yes | **still 0/0** |
| ingame Valhalla (start, ~19 s after world change) | `0xC133F919C108BDF9` | `0x80B81960` | yes | starting items 1/1 |
| Flight Valhalla → Norion (loading phase) | changes to `0x6FB8EF2A9523C343` | **briefly `0x0`** (2 s) | no | stays |
| ingame Norion | `0x6FB8EF2A9523C343` | `0x80F5AA60` | yes | stays |

Conclusions:
- The check "CPlayer + vtable" reliably separates menu and loading from the game.
- In the intro and cutscenes one already counts as "ingame" according to the connector, although the inventory is not filled yet. An
  AP client should only write once `PowerBeam.capacity > 0` as well, or wait for another plausibility check.
  There is no check for cutscenes in MP3: the MP1/MP2 camera check in `OPR/all_prime_dol_patches.py:70-82` is missing for Corruption.
- The byte `cstate_manager_global + 0x2` is **not** suitable as a state flag in MP3 (always `0xFF`).

---

## 7. Current world / room

- **World:** `[game_state_pointer] + 0x8` as `u64`. Compared against `region.extra["asset_id"]` from
  `logic_database/<Region>.json:4` (`prime_remote_connector.py:110-114`). The mapping name → ID is also in
  `randovania/games/prime3/assets/migration_data.json:2-18`.
- **Room (area):** is **not** read by the connector (`PlayerLocationEvent(region, None)`,
  `prime_remote_connector.py:331`). Address unknown. The area asset IDs are in the database
  (`migration_data.json` → `area_name_to_id`, `<Region>.json` → `extra.asset_id`).

| Region | MLVL asset ID (hex) | Status PAL |
|---|---|---|
| G.F.S. Valhalla | `0xC133F919C108BDF9` | confirmed live (starting world seed IVG2J7OR) |
| Norion | `0x6FB8EF2A9523C343` | confirmed live |
| FrontEnd (menu) | `0xF4A9F72C65FBAE26` | seen live, no region in the DB |
| G.F.S. Olympus | `0x37A9E86F0A0CAF6F` | DB only |
| other 12 regions | see `migration_data.json:2-18` | DB only |

Note on T01: according to `t01.rdvgame` the starter preset seed `IVG2J7OR` starts on **Valhalla, Docking Bay 5**, not on
Olympus. The memory values confirm this. The T01 observation "boots up to Olympus" should be checked; it was probably
Valhalla.

---

## 8. Live check PAL: log

Tools: throwaway scripts outside the repo (scratchpad), `mp3mem.py` (single read) and `mp3watch.py` (0.5 s polling,
logs only changes). They reproduce the pointer chains from section 2. The user played the collecting,
the script read the values.

Confirmed values (PAL `RM3P01`):

| # | Field | Expected (code) | Read | Result |
|---|---|---|---|---|
| 1 | Game ID `0x80000000` | `RM3P01` | `RM3P01` | ✔ |
| 2 | Build string @ `0x805843A8` | `…2007/08/24 16:52 Build v3.453 (mp3)` | identical | ✔ |
| 3 | CPlayer vtable | `0x80595238` | `0x80595238` | ✔ |
| 4 | World `[0x80680234]+8` | Valhalla `0xC133F919C108BDF9`, after the flight Norion `0x6FB8EF2A9523C343` | identical | ✔ |
| 5 | Inventory starting items | seed: Charge, Power, Combat, Scan, Space Jump, Morph Ball, Bombs | exactly these 7 at 1/1, rest 0 | ✔ |
| 6 | **ScrewAttack** (ID 16) @ `0x80995C34` | – | **before 0/0 → after 1/1** (19:25:43, Norion, Docking Hub Alpha, location "Pickup (Grapple Lasso)", Screw Attack according to the seed) | ✔ |
| 7 | **ItemPercentage** (ID 21) @ `0x80995C70` | +1 per pickup | 0/100 → **1/101** (19:22:41, Valhalla; probably the Missile Expansion in Docking Bay 5, `Missile` stayed 0/0) → **2/102** (Screw Attack) | ✔ |
| 8 | Stat_DamageReceived (ID 64) | – | 0/0 → 2/2 when the HUD dropped from 99 to 97 | ✔ |
| 9 | Stat_ShotsFired (ID 63) | – | counts up every shot (0 → 12) | ✔ |

Not checked live: `powerup_functions` (giving items), writes of any kind, NTSC-U and NTSC-J.

---

## 9. Open points for T05–T07

1. Item giving (T07): test direct writing into the inventory slot live, including saving, loading, Energy Tank and beam switching.
2. Location checks (T05/T06): counter item in the patcher, or find layer state addresses (section 5).
3. Room address (area) for tracker or DeathLink, optional.
4. NTSC-U address verification is tracked in [AP_NTSC.md](AP_NTSC.md) (T33, SPEC E7).
5. Layout UUID: the MP3 patcher does not write it. Mapping client ↔ seed needs a marker of its own
   (e.g. seed hash in the build string, as with `apply_build_info_patch`, `OPR/all_prime_dol_patches.py:316`).
