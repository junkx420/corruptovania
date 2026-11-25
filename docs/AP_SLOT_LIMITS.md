# Inventory slots: bit width, persistence and game events (T19, T15)

As of 2026-11-25. PAL `RM3P01` only, PrimeHack v1.0.9, **CPU Clock Override off** (`OverclockEnable = False`), Disc Speed
"fast" (`FastDiscSpeed = True`). Basis: SPEC E9/E11, `AP_LIVE_TESTS.md` (T10), `AP_LIVE_TESTS_T11.md` (T11).
Inventory as there: `PS + 0x54 + slot*0xC`, per slot `u32 amount, u32 capacity`, `PS = [[0x80680234]+0x24]` (live `0x80995B20`).

> **Summary for T07**
> 1. `main.dol` contains a table with 70 entries (name, **maximum**, **flags**) from `0x8057D5F8`. On saving, every
>    slot keeps only the lower `bits = bit_length(maximum)` bits of amount **and** capacity separately, i.e.
>    `value mod 2^bits`. **Nothing is clamped.** Measured on 54 slots in two passes, all 108 values match (section 3).
>    The maximum is identical to `max_capacity` in Randovania's `header.json`.
> 2. Slots without flag bit 31 are **not saved at all**; after loading they are 0/0: 18 Energy, 19, **47**,
>    48, 49, 50, **69**.
> 3. The T11 finding "Suit 11 → 3" is **reproduced and explained**: SuitType has 3 bits (maximum 6), 7 is kept,
>    8 becomes 0.
> 4. **Conflicts with the pool:** Suit (capacity 6 + 5 = 11 > 7) and Energy Cells, if T07 adds capacity there
>    (22: 9 + 9 = 18 > 15, 23–31: 1 + 1 = 2 → 0). All other pool sums fit: Missile 245 ≤ 255, Energy Tank 14 ≤ 15,
>    Ship Missile 11 ≤ 15, slot 68 240, ItemPercentage 199 ≤ 255.
> 5. **Live freeze:** Suit amount 13 freezes the game in the same frame. The amount in slot 17 is an index.
> 6. **T15:** Inserting an Energy Cell lowers the **amount** of 22 and Fuse_i, the capacity stays. Hypermode and the flight to Norion
>    lower nothing. A death loads the last save, so everything drops to the saved state.

## 1. Source of the bit width: powerup table in the DOL

PAL `main.dol`, address `0x8057D5F8` (file offset `0x5796D8`), 70 × 12 bytes: `u32` pointer to the name, `u32` maximum,
`u32` flags. Original ISO (`pal_extract`) and T01 ISO (`pal_t01_extract`) are byte-identical here. Reproduction
(repo root, venv):

```powershell
venv\Scripts\python.exe -I apworld\tools\live\slot_probe.py dol ..\pal_extract\DATA\sys\main.dol
```

The script compares the DOL with `SLOT_TABLE` in `apworld/tools/live/slot_probe.py` (exit 1 on a difference).

Flags: **bit 31 = is saved.** This is backed by measurement: all slots with bit 31 kept their values, and the
checked slots without bit 31 (47, 69, according to T10 also 48, 49) are 0/0 after loading. Bit 30 is not set for 21, 40, 41,
51–61, and set for the other saved slots. Its meaning is **unknown**; it has no influence on saving (21 and 53–61 were
measured).

Names in the DOL that differ from `AP_MEMORY_MAP.md` or are missing there: **43 = HyperModeCharge**, **47 = PhazonBall**,
**52 = FusesUsed** (there "EnergyCellsUsed"), **53–61 = Fuse1Used … Fuse9Used**.

## 2. Course of the measurement

| Time (2026-11-25) | Step |
|---|---|
| 01:41 | Save backed up (`out/t19/save_backup_before`, outside the repo) |
| 01:45 | New game (rando start, G.F.S. Valhalla, Docking Bay 5, ship usable), current state `baseline` |
| 01:45 | **Pass 1** (`pass1`) written: 54 slots, capacity = `2^bits − 1`, amount = pool maximum. Saved at the ship, reset, Continue |
| 01:47 | **Pass 2** (`pass2`) written: amount `2^bits + 1`, capacity `2^bits`, 3/2 for 1-bit items, Suit 13/8. **PrimeHack froze at once** (memory unchanged, still before saving). The save from pass 1 was kept |
| 01:51 | Restart, pass 1 state loaded (identical to `loaded_pass1`). **Pass 2s** (`pass2s`, defused): amount = capacity = `2^bits`, Suit 5/8, critical slots 0/11/12/15/32 at 1/1. Ran, saved, reset, Continue |
| 01:53 | Freeze probe: only slot 17 at 13/8 → **froze at once**. Restart |
| 01:54–01:58 | T15 (section 5), logger with 0.1 s interval over all 70 slots |
| 02:00 | Original inventory written back, saved at the ship, checked (`after_final_save`: only Stat_DataSaves +1) |

Raw data (JSON per step, JSONL logs) is in `out/t19/` next to the repo, not in the repo.

## 3. Measured values of pass 1 and 2s

"before" = read 3 s after writing (the game changed nothing, except slot 47), "after" = after saving, reset, Continue.

| Slot | Name | bits | P1 before | P1 after | P2s before | P2s after | Finding |
|---|---|---|---|---|---|---|---|
| 0 | PowerBeam | 1 | 1/1 | 1/1 | 1/1 | 1/1 | critical, only 1 written |
| 1–3, 5–10, 13, 14, 16 | Beams, Charge, missile upgrades, Grapple, Bomb, Command/X-Ray, Screw | 1 | 1/1 | 1/1 | 2/2 | **0/0** | 1 bit |
| 4 | Missile | 8 | 245/255 | 255/255 | 256/256 | **0/0** | 8 bits, amount is filled up to capacity on saving at the ship |
| 11, 12, 15, 32 | Combat/Scan Visor, DoubleJump, MorphBall | 1 | 1/1 | 1/1 | 1/1 | 1/1 | critical, only 1 written |
| 17 | SuitType | 3 | 5/7 | 5/7 | 5/8 | **5/0** | 3 bits, 7 stays, 8 → 0 |
| 20 | EnergyTank | 4 | 14/15 | 15/15 | 16/16 | **0/0** | 4 bits, amount is filled up on saving |
| 21 | ItemPercentage | 8 | 199/255 | 199/255 | 256/256 | **0/0** | 8 bits, save menu shows "199%" |
| 22 | Fuses | 4 | 9/15 | 9/15 | 16/16 | **0/0** | 4 bits |
| 23–31 | Fuse1–9 | 1 | 1/1 | 1/1 | 2/2 | **0/0** | 1 bit |
| 33–39 | Boost, Spider, HyperModeTank/Beam/Missile/Ball/Grapple | 1 | 1/1 | 1/1 | 2/2 | **0/0** | 1 bit |
| 43 | HyperModeCharge | 1 | 1/1 | 1/1 | 2/2 | **0/0** | 1 bit (T10 assumption confirmed) |
| 44 | ShipGrapple | 1 | 1/1 | 1/1 | 2/2 | **0/0** | 1 bit |
| 45 | ShipMissile | 4 | 11/15 | 11/15 | 16/16 | **0/0** | 4 bits, amount **not** filled up (stays 11) |
| 47 | PhazonBall | – | 0/1 (amount live → 0) | **0/0** | 0/2 | **0/0** | not saved |
| 52 | FusesUsed | 4 | 15/15 | 15/15 | 16/16 | **0/0** | 4 bits |
| 53, 55, 57, 59, 61 | Fuse1/3/5/7/9Used | 1 | 1/0 | 1/0 | 2/3 | **0/1** | 1 bit, amount and capacity separate |
| 54, 56, 58, 60 | Fuse2/4/6/8Used | 1 | 0/1 | 0/1 | 3/2 | **1/0** | 1 bit, amount and capacity separate |
| 68 | Stat_TinCanHighScore | 17 | 240/131071 | 240/131071 | 131072/131072 | **0/0** | 17 bits |
| 69 | Stat_TinCanCurrentScore | – | 8/8 | **0/0** | 9/9 | **0/0** | not saved |

Evaluation (`slot_probe.py check`): the hypothesis "mod 2^bits" matches **54/54** in P2s and all capacities in P1. The two
amount differences in P1 (slots 4 and 20) come from the filling up on saving at the ship. The logging confirms the sequence:
Missile 245 → 255 and Energy Tank 14 → 15 only came on saving, Stat_DataSaves rose to 1 at the same time.
The hypothesis "clamping to the table maximum" matches 7/54 and is thus **refuted**. Values above the table maximum
are kept as long as they fit into the bit width (Suit 7 > 6, Energy Tank 15 > 14, Fuses 15 > 9, Ship Missile 15 > 11).

**Freeze (pass 2):** In `pass2` several impossible values were written at the same time. Only
SuitType 13/8 was checked on its own; it freezes at once. Not checked on their own are amount > capacity for items (3/2), ItemPercentage
257/256, Missile 257/256 (the HUD showed "255" meanwhile) and Energy Tank 17/16. Amount > capacity for Fuse*Used (1/0, 3/2) ran
without problems. Whether Suit amount 6 or 7 already freezes is **not** checked. 5 (Hazard Shield, T11) works.

## 4. Table for T07 (machine-readable)

All slots an AP item can touch, plus the starting items and the special slots from the task. `bits_amount` and
`bits_capacity` apply to the save; live, all slots hold full `u32`. `max_valid` is the highest value that survives saving
and loading (`2^bits − 1`), or 0 for slots that are not saved. `pool_max` is the capacity after start plus the full
AP pool (`apworld/metroidprime3/data/items.py`, amounts from `Item.cs`). `tab_max` is the maximum from the DOL (= `header.json`
`max_capacity`). Measurement evidence: section 3 (`P1` = pass 1, `P2s` = pass 2s).

```csv
slot;name;bits_amount;bits_capacity;max_valid;tab_max;pool_max;pool_ok;notes
0;PowerBeam;1;1;1;1;1;yes;starting item, capacity>0 is the client's ingame criterion, only 1 measured
1;PlasmaBeam;1;1;1;1;1;yes;Progressive Beam stage 1, 2 -> 0 measured
2;NovaBeam;1;1;1;1;1;yes;Progressive Beam stage 2, 2 -> 0 measured
3;ChargeUpgrade;1;1;1;1;1;yes;starting item, 2 -> 0 measured
4;Missile;8;8;255;255;245;yes;launcher 5 + 48x5, saving at the ship fills amount up to capacity, 256 -> 0, transfer from slot 68 (T10) can add on top
5;IceMissile;1;1;1;1;1;yes;2 -> 0 measured
6;SeekerMissile;1;1;1;1;1;yes;2 -> 0 measured
7;GrappleBeamPull;1;1;1;1;1;yes;2 -> 0 measured
8;GrappleBeamSwing;1;1;1;1;1;yes;2 -> 0 measured
9;GrappleBeamVoltage;1;1;1;1;1;yes;2 -> 0 measured
10;Bomb;1;1;1;1;1;yes;starting item, 2 -> 0 measured
11;CombatVisor;1;1;1;1;1;yes;starting item, only 1 measured
12;ScanVisor;1;1;1;1;1;yes;starting item, only 1 measured
13;CommandVisor;1;1;1;1;1;yes;2 -> 0 measured
14;XRayVisor;1;1;1;1;1;yes;2 -> 0 measured
15;DoubleJump;1;1;1;1;1;yes;starting item Space Jump Boots, only 1 measured
16;ScrewAttack;1;1;1;1;1;yes;2 -> 0 measured
17;SuitType;3;3;7;6;11;NO;start 0/6, pickup +5/+5 gives 5/11 -> 5/3 after loading, 7 stays, 8 -> 0, amount is an index: 13 freezes live at once
20;EnergyTank;4;4;15;14;14;yes;16 -> 0, saving at the ship fills amount up to capacity
21;ItemPercentage;8;8;255;255;199;yes;start 0/100, game +1/+1 per pickup, client does not write, 256 -> 0
22;Fuses;4;4;15;9;9;yes (amount only);start 0/9: capacity is fixed at 9, amount = cells held, inserting lowers amount by 1, capacity +1 per cell would give 18 -> 2
23;Fuse1;1;1;1;1;1;yes (amount only);start 0/1, amount = cell held, inserting sets amount 0, capacity stays 1, 2 -> 0
24;Fuse2;1;1;1;1;1;yes (amount only);as 23
25;Fuse3;1;1;1;1;1;yes (amount only);as 23
26;Fuse4;1;1;1;1;1;yes (amount only);as 23
27;Fuse5;1;1;1;1;1;yes (amount only);as 23
28;Fuse6;1;1;1;1;1;yes (amount only);as 23
29;Fuse7;1;1;1;1;1;yes (amount only);as 23
30;Fuse8;1;1;1;1;1;yes (amount only);as 23
31;Fuse9;1;1;1;1;1;yes (amount only);as 23
32;MorphBall;1;1;1;1;1;yes;starting item, only 1 measured
33;BoostBall;1;1;1;1;1;yes;2 -> 0 measured
34;SpiderBall;1;1;1;1;1;yes;2 -> 0 measured
35;HyperModeTank;1;1;1;1;1;yes;pool item Hypermode, 2 -> 0
36;HyperModeBeam;1;1;1;1;1;yes;no pickup, unlocks the Hypermode menu (T11), 2 -> 0
37;HyperModeMissile;1;1;1;1;1;yes;2 -> 0
38;HyperModeBall;1;1;1;1;1;yes;2 -> 0
39;HyperModeGrapple;1;1;1;1;1;yes;2 -> 0
43;HyperModeCharge;1;1;1;1;-;-;name from the DOL, 2 -> 0, not suitable for counters/markers
44;ShipGrapple;1;1;1;1;1;yes;2 -> 0
45;ShipMissile;4;4;15;11;11;yes;Ship Missile 3 + 8x1, amount not filled up on saving, 16 -> 0
47;PhazonBall;0;0;0;1;-;-;not saved (flag 0), amount = Hypermode active (1 while in use), new game 0/1, after loading 0/0, never write
52;FusesUsed;4;4;15;9;-;-;inserted cells, inserting +1/0 (amount), 16 -> 0
53;Fuse1Used;1;1;1;1;-;-;cell 1 inserted (amount 0 -> 1 on inserting, start 0/1), amount and capacity saved separately
54;Fuse2Used;1;1;1;1;-;-;as 53
55;Fuse3Used;1;1;1;1;-;-;as 53
56;Fuse4Used;1;1;1;1;-;-;as 53
57;Fuse5Used;1;1;1;1;-;-;as 53
58;Fuse6Used;1;1;1;1;-;-;as 53
59;Fuse7Used;1;1;1;1;-;-;as 53
60;Fuse8Used;1;1;1;1;-;-;as 53
61;Fuse9Used;1;1;1;1;-;-;as 53
68;Stat_TinCanHighScore;17;17;131071;99999;240;yes;locked Missile Expansions (T10: +5 each), game transfers to slot 4, 131072 -> 0
69;Stat_TinCanCurrentScore;0;0;0;99999;-;-;not saved (flag 0), whether locked Ship Missiles land here is open
```

## 5. T15: Do capacities drop through game events?

Setup: new game with the original inventory, plus Hypermode (35–39 each 1/1), 3 Energy Tanks and Energy Cell 1
(23 = 1/1, 22 = 1/9) by direct writing. Logger over all 70 slots at a 0.1 s interval. Statistics slots 62–64 are left out here.

| Event | checked | Slot: before → after | Capacity dropped? |
|---|---|---|---|
| Energy Cell 1 inserted at the terminal in Docking Bay 5 (01:54:52) | yes | 22: 1/9 → **0/9**, 23: 1/1 → **0/1**, 52: 0/9 → 1/9, 53: 0/1 → 1/1 | **no**, but the **amount** drops (22, 23) |
| Activate and end Hypermode, twice (01:55:02–01:55:40) | yes | 47: 0/1 → 1/1 → 0/1 (per use), 66: 0 → 1 → 2. Energy Tank stayed 3/3 | no |
| Hypermode until corruption | yes, but could not be triggered | Hypermode ran out without corruption (story Hypermode not reached yet) | – |
| Death (Game Over, caused by the player) and Continue (01:56:50–01:56:55) | yes | All 70 slots = inventory of the last save (byte-identical with `loaded_pass2s`). Whatever was added since saving was gone | **yes, to the state of the last save** |
| Flight Valhalla → Norion (01:57:46) | yes | no inventory change | no |
| Saving at the ship | yes (T19) | Missile and Energy Tank amounts are filled up to capacity, Ship Missile is not, Stat_DataSaves +1 | no |
| Return flight Norion → Valhalla (01:58:35) | only state change logged | comparison not evaluated (log buffer not written when stopping) | open |

**Not checked (not reachable without game progress), detection is left to the client in the playtest:**
- Suit change to the PED Suit (story after Norion/Olympus), Phazon Suit on Phaaze (slots 17, 40, 41)
- Story Hypermode and corruption in Bryyo (slots 42 HyperModeOriginal, 46 FaceCorruptionLevel, 19 HypermodeEnergy), death by corruption
- Phaaze: permanent Hypermode (40 HyperModePermanent, 41 HyperModePhaaze), loss of Hyper Mode after the final battle
- Inserting Energy Cells 2–9 (only Cell 1 checked), terminals outside Valhalla
- Command Visor jammed (51 CommandVisorJammed), Ship Missile consumption, locked Ship Missile Expansion (slot 69?)
- Real Suit pickup (does `add_power_up` clamp the capacity to 6? T11 open)

## 6. Consequences for T07 and E11

- Set target values **absolutely** and clamp them to the table maximum (`tab_max`, = `header.json` `max_capacity`). That is
  always `≤ 2^bits − 1`, so every written value survives saving. Do not add blindly.
- **Suit (17):** write the pool item Hazard Shield as fixed values: amount 5, capacity 6 (starting capacity). Never 11
  (→ 3 after loading) and never an amount ≥ 8 (13 freezes, 6/7 unchecked).
- **Energy Cells (22–31):** The capacity is set from the start (0/9, 0/1) and never changes. The item is the **amount**,
  and it drops on inserting. Target for Fuse_i: amount 1 as long as cell i is received **and** Fuse_iUsed (slot 52 + i, amount)
  is 0, otherwise 0. Target for slot 22: amount = received minus inserted cells (= sum of the Fuse_i amounts), capacity 9.
  A cell that has been inserted once must not be given again.
- **Missile (4) / Energy Tank (20):** Saving fills up the amount. On an increase, set capacity to the target and raise the amount
  by the same difference (do not reset an amount that dropped through consumption). Pool 245 and 14 respectively fits.
  If slot 68 (locked expansions) can still be filled in AP mode, the game adds it onto slot 4 at the next Missile pickup
  (T10). That can lead above 255 and must be avoided. With `--ap-mode` (T16, pickups give 0/0) this goes away.
- **Death/Continue** resets everything to the last save. This is exactly why E11 needs the reconciliation without a stored index:
  after every load the client must check all target values again.
- Never use slots 47 and 69 as storage for client state (not saved). 43 and 53–61 hold only 1 bit, and 53–61 have
  a meaning in the game (inserted cells).

**Recommendation E11:** "only raise the target capacity" remains viable for all real capacity slots if T07 sets the target values
absolutely and clamps them to `max_capacity`. Exceptions are the Suit (write a fixed 5/6) and the Energy Cells 22–31: there
the amount counts, and it drops on inserting, so target = received minus inserted according to slots 52–61, and inserted cells
are never given again.

## 7. Limits of the measurement

- PAL `RM3P01` only, PrimeHack v1.0.9 only (Clock Override off), saving at the ship only (no save station).
- For the critical slots 0, 11, 12, 15, 32 the transition 2 → 0 is not measured (only 1/1). The bit width comes from the table
  and follows the measured pattern of the other 1-bit slots.
- The save after pass 1 contained values above `tab_max`. The game loaded them without errors, but they were not used in the game.
- Measurement script: `apworld/tools/live/slot_probe.py` (writes only to the inventory array in the PrimeHack RAM, only ingame).
