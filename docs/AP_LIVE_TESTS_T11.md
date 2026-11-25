# AP live tests PAL: direct writing for all item classes (T11)

As of 2026-11-23. Checks SPEC E9/E16: does directly writing amount/capacity to `PS + 0x54 + slot*0xC`
(`PS = [[0x80680234]+0x24]`, per slot `u32 amount, u32 max, u32 ?`, big endian) work for all item classes in the pool?
Slot meanings according to `AP_MEMORY_MAP.md` section 3 and `AP_PATCHER_NOTES.md`. Differences are noted below; the measurement applies.

## Test environment

| Item | Value |
|---|---|
| Emulator | PrimeHack v1.0.9 (Dolphin fork), Windows 11 |
| CPU Clock Override | on, 500 % (`OverclockEnable = True`, `Overclock = 5.` in `Dolphin.ini`) |
| Disc speed | `FastDiscSpeed = True` in `GameSettings\RM3P01.ini` ("Speed up Disc Transfer Rate", i.e. no emulated read time). In T10 the user reported "Emulate Disc Speed off", which fits |
| Game | PAL `RM3P01`, ISO `out/t01_IVG2J7OR.iso` (seed IVG2J7OR, starter preset), outside the repo |
| Save | throwaway save from T10 (confirmed by the user), Norion, Docking Hub Alpha, ingame. Early game: ship not usable, hyper corruption (story, according to the user only in Bryyo) not triggered |
| Starting inventory | seed starting items (Power, Charge, Combat, Scan, Space Jump, Morph Ball, Bombs), plus from T10 Missile 15/15, Plasma, Grapple Lasso, Energy Tank, Screw Attack. `PS = 0x80995B20`, world Norion `0x6FB8EF2A9523C343` |
| Tool | dolphin-memory-engine 1.3.0 (Python 3.12), throwaway scripts in the scratchpad outside the repo. Per write: all 70 slots before writing, then reads after 0 s, 0.5 s and 3 s, and all 70 slots after 3 s |
| Time span | 21:20 to 21:43 (2026-11-23), save + reset + Continue Game at 21:42 |
| Crash | none |

Method: the user played and reported for each step what they saw. The value written was the one a real pickup would give according to `Item.cs`
(the pickup's `capacity`/`amount` added to the starting value). **Important for the evaluation:** the user gave one overall verdict per item ("works") and after
reloading "everything still there". HUD and pause menu were therefore not asked about individually in every case. Where the menu was specifically asked about or photographed, this is stated
in the column. Otherwise it says "overall verdict".

## Result table

Legend: yes / no / n/c (not checkable, with reason). "Overall verdict" = the user reported "works" or "everything still there" without an individual question.
"Reload" = save, reset, Continue Game; memory value **and** user verdict.

| Slot | Item | Written (before → value) | Works | HUD | Menu | Survives reload | Side effect |
|---|---|---|---|---|---|---|---|
| 17 | Suit (SuitType) | 0/6 → 5/11 (pickup: +5/+5) | yes, suit visibly changed | overall verdict | overall verdict (menu "Suits") | amount yes (5). **Max no: 11 → 3** | max is cut to 3 bits on saving/loading (11 mod 8 = 3). No crash, no sequence |
| 13 | Command Visor | 0/0 → 1/1 | yes (visor switchable) | yes (visor switch usable) | after reload: overall verdict | yes | none |
| 14 | X-Ray Visor | 0/0 → 1/1 | yes | yes (visor switch usable) | after reload: overall verdict | yes | none |
| 44 | Ship Grapple | 0/0 → 1/1 | **n/c:** ship not usable in the early save | n/c | not reported, no entry noticed | memory yes (1/1) | none |
| 45 | Ship Missile | 0/0 → 3/3 (pickup: +3/+3) | **n/c:** as slot 44 | n/c | not reported, no entry noticed | memory yes (3/3) | none |
| 35 | Hyper Mode Tank | 0/0 → 1/1 | n/c individually (see hyper block below) | n/c | n/c | memory yes | none |
| 37 | Hyper Missile | 0/0 → 1/1 | see hyper block | see hyper block | yes, listed in the menu "Hypermode" (screenshot) | yes (menu after reload: overall verdict) | none |
| 38 | Hyper Ball | 0/0 → 1/1 | see hyper block | see hyper block | yes, listed (screenshot) | yes | none |
| 39 | Hyper Grapple | 0/0 → 1/1 | see hyper block | see hyper block | yes, listed (screenshot) | yes | none |
| 22 | Energy Cells total (Fuses) | 0/9 → 2/9 | n/c: terminal not in reach, effect only checked as display | yes, menu shows 2 cells **only with this slot** | yes (see below) | yes (2/9) | none |
| 23 | Energy Cell 1 (Fuse1) | 0/1 → 1/1 | see slot 22: **alone without display** | no, alone without slot 22 | no, alone without slot 22 | yes (1/1) | none |
| 24 | Energy Cell 2 (Fuse2) | 0/1 → 1/1 | see slot 22 | as slot 23 | as slot 23 | yes (1/1) | none |
| 33 | Boost Ball | 0/0 → 1/1 | yes (boost thrust) | overall verdict | overall verdict | yes | none |
| 34 | Spider Ball | 0/0 → 1/1 | yes (sticks to the rail) | overall verdict | overall verdict | yes | none |
| 5 | Ice Missile | 0/0 → 1/1 | yes | overall verdict | overall verdict | yes | none |
| 6 | Seeker | 0/0 → 1/1 | yes | overall verdict | overall verdict | yes | none |
| 8 | Grapple Swing | 0/0 → 1/1 | yes | overall verdict | overall verdict | yes | none |
| 9 | Grapple Voltage | 0/0 → 1/1 | yes | overall verdict | overall verdict | yes | none |
| 2 | Nova Beam | 0/0 → 1/1 | yes | overall verdict | overall verdict | yes | none |
| 15 | Space Jump | 1/1 → 0/0 → 1/1 | yes: at 0/0 only a single jump (Screw Attack kept working), at 1/1 double jump | overall verdict | overall verdict | yes | none |
| 36 | HyperModeBeam (no pickup item, additional attempt) | 0/0 → 1/1 | see hyper block | – | yes: unlocks the menu category "Hypermode" | yes (memory 1/1) | none |

Note on "n/c" for the individual hyper abilities: Hyper Mode itself started (below). Whether Hyper Missile, Hyper Ball and Hyper Grapple worked individually was not reported individually by the user.
Energy Cells 25–31 (Fuse3–9) were not written (requirement: at least 2). Boost Ball and Spider Ball both work according to the user.

### Hyper Mode (slots 35, 36, 37, 38, 39)

- After writing 35, 37, 38, 39 (each 1/1) Hyper Mode started (according to the user). **I had not tested Hyper Mode before**, so it is not measured whether these four writes were needed for it. Slot 42 (HyperModeOriginal) was already at 1/1 before the test.
- Hyper Mode triggered **no corruption** (according to the user the story event only comes in Bryyo). `HypermodeEnergy` (slot 19) stayed 0/0, `Stat_HypermodeUses` (66) rose 0 → 3, `FaceCorruptionLevel` (46) stayed 0/0.
- Pause menu: with 35/37/38/39 the top left showed **"???"** (locked). After writing slot 36 (HyperModeBeam, 1/1) the category is called **"Hypermode"** and lists Hyper Beam, Hyper Ball, Hyper Missile and Hyper Grapple (screenshot from the user). Slot 36 is **not** a pickup item of the patcher. So unlocking the menu depends on a slot that no pickup sets. Not measured: whether the category depends on slot 36 alone or on the combination.
- Slot 47 (not one of my slots): the max rose during Hyper Mode use 0 → 1 → 2, the amount stayed 0. After saving and reloading 0/0 again (as in T10 test B). Whether this also happens in the unmodified game is not checked.

### Energy Cells

- Slots 23 and 24 alone (each 1/1): pause menu and HUD showed **nothing**.
- Additionally slot 22 at 2/9: the game shows 2 cells. The game does **not** recompute slot 22 from slots 23–31 (slot 22 stayed 0/9 until I wrote it).
- Not checked: whether a real Energy Cell pickup also raises slot 22 (the patcher writes only the fuse slot in `Item.cs`; the increase of 22 probably happens in the game). Not checked: inserting the cells (effect on slot 52 `EnergyCellsUsed`, terminals).

## Diff of all 70 slots

For each write (after 3 s) **only** the written slot changed, no other. Exception: game counters and slot 47 (see above).

Overall comparison baseline (21:19:59) → before saving (21:41:50), 26 slots:
all slots written by me (2, 5, 6, 8, 9, 13, 14, 17, 22, 23, 24, 33, 34, 35, 36, 37, 38, 39, 44, 45) with the values of the table, plus game values:
slot 4 (Missile) 15 → 14 (shot), 47 (0/0 → 0/2, Hyper Mode use), 63 (Stat_ShotsFired 62 → 184), 64 (Stat_DamageReceived 2 → 9), 65 (Stat_DataSaves 4 → 5), 66 (Stat_HypermodeUses 0 → 3).

Comparison before saving (21:41:50) → after reloading (21:43:43), 5 slots:

| Slot | before | after | Cause |
|---|---|---|---|
| 4 | 14/15 | 15/15 | game refills missiles |
| 17 | 5/11 | **5/3** | max cut to 3 bits (finding), amount stays |
| 47 | 0/2 | 0/0 | as T10, game resets |
| 63 | 184 | 189 | shots |
| 65 | 5 | 6 | saving counts DataSaves |

All other 65 slots, among them all test slots, stayed the same. After reloading, world, `PS` and ingame detection are unchanged.

## Story events and inconsistent states

- **Suit:** the suit changed visibly, no sequence ran, no crash. After reloading the max is 3. The amount stays 5, so the connector rule "amount ≥ 5 = has item" (`corruption_remote_connector.py:142-152`) still holds. A real pickup (+5 on max 6 = 11) would also be cut to 3 by the same calculation; this is **not** checked with a real pickup.
- **Hyper Mode:** the game started Hyper Mode without the story event (no corruption, no crash). The menu behaviour (entry only with slot 36) is the only inconsistency I observed. What happens when the user later triggers the story event in Bryyo was not measured (belongs to T15).
- **Ship items:** cannot be judged without a usable ship. The memory kept the values even after reloading; no menu or game hint was reported.
- Did not occur: crash, skipped sequence, change of other slots through my writes.

## Differences from the memory map

- Slot 22 (Fuses) is not just a sum: the menu only shows the cells when slot 22 is written. `AP_MEMORY_MAP.md` line 102 names "Energy Cells Total" without this dependency.
- Slot 17 (SuitType): the max is limited to 3 bits after saving/loading (measured 11 → 3). `AP_MEMORY_MAP.md` names max 6.
- Slot 36 (HyperModeBeam): no pickup in the patcher, but determines the menu category "Hypermode".
- Slot 47: the max rises in the game with the Hyper Mode uses (0/0 → 0/2 with 3 uses).

## Items that do NOT work via direct writing

None of the checked items turned out to be ineffective. Restrictions (no malfunctions, but conditions for the client):

1. **Energy Cells 23–31** only show up in the game if slot 22 is written too (2 cells only with 22 = 2/9, not with 23/24 alone).
2. **Hyper Mode menu** ("Hypermode" category instead of "???") needs slot 36 = 1/1, which no pickup sets.
3. **Suit (17):** the max survives only 3 bits (11 → 3), the amount 5 stays.

Not checkable (early game): effect of Ship Grapple (44) and Ship Missile (45), effect of Hyper Missile/Ball/Grapple individually, effect of the Energy Cells (terminals), behaviour at the later story event in Bryyo.

## Conclusion for E16 (DOL hook)

All checked item classes (suit, visors, beams, missiles, grapple, Boost/Spider, Space Jump, hyper slots, Energy Cells) worked via direct writing and survived saving and reloading. The condition from E16 ("only if T11 finds an item that does not work via direct writing") is therefore not met according to this measurement. Open are the effect of the ship items and the behaviour at the later hyper story event; the client must also write slot 22 (Energy Cells) and slot 36 (Hypermode menu) and can only reliably hold the amount (not the max) for the suit.

## Open points

1. Test ship items (slots 44, 45) in a save with a usable ship (effect, HUD, menu).
2. Check Hyper Missile, Hyper Ball, Hyper Grapple and Hyper Tank individually for effect; clarify whether 35/37/38/39 are needed to start Hyper Mode and whether slot 36 alone unlocks the menu item.
3. Insert Energy Cells (terminal) and check whether slot 22 is raised too with a real pickup; check slots 25–31 with the same pattern.
4. Suit max: counter-measure with a real suit pickup whether the max drops to 3 there as well.
5. Behaviour at the story event in Bryyo after hyper slots given via direct writing (T15).
6. Not checked: NTSC-U (`RM3E01`), standard Dolphin and the measurement without 500 % Clock Override.
