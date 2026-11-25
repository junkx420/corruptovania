# T08 playtest: 2-player multiworld MP3 + ChecksFinder (incl. T17 goal detection, T13 spot check)

As of 2026-11-25 · Archipelago 0.6.8 (installed, `C:\ProgramData\Archipelago`) · PAL `RM3P01` · PrimeHack 1.0.9

Paths outside the repo are given relative to the project folder `MP3 Archi\` (the folder that contains
`corruptovania\`, `Archipelago\` and `out\`).

## Assignment

Copied once from the task prompt (translated), so that later sittings can read it.

Read first: SPEC.md (3a, E3, E9–E11, E14, E15, E18, E19, E21, F8), STATUS.md (T05b, T06, T07, T08, T13, T14, T17, T18,
T21), `docs/AP_CLIENT.md`, `docs/AP_APWORLD_DEV.md` (sections 2, 6, 7), `docs/AP_PATCH_TOOL.md`,
`docs/AP_SLOT_LIMITS.md` (section 5), `docs/AP_LIVE_TESTS_T11.md` (open points). If this file exists, read it first and
continue where the last sitting stopped (then skip steps 1–3 unless the handover says otherwise). Talk to the user in
German; all project content in English (E21).

**Effort:** sittings run with effort "high". The goal measurement (step 6) needs "extra high". As soon as the player is
close to the final battle (at the latest before comparing memory dumps), stop and tell the user clearly, on a line of
its own: "JETZT AUFWAND AUF EXTRA HOCH STELLEN (Menü unten im Eingabefeld), dann 'weiter' schreiben." Wait for the
confirmation. When the goal detection is done and tested, tell them just as clearly: "AUFWAND WIEDER AUF HOCH STELLEN."

Task T08 (F8, including T17 and the T13 spot check via the learning mode): end-to-end test of a 2-player multiworld
with the installed Archipelago, played to the victory over Aurora Unit 313, measuring and implementing the goal
detection on the way. Several sittings; every sitting ends with a handover.

1. **Preparation:** `git pull --rebase origin archipelago`, all tests green. Raise `world_version` in
   `apworld/metroidprime3/archipelago.json` to 0.2.0. Build the `.apworld` in the Archipelago development clone with
   "Build APWorlds" (`AP_APWORLD_DEV.md` 7), back up the old `.apworld` in `custom_worlds` of the installed Archipelago
   (`C:\ProgramData\Archipelago`), copy the new one in, check that the installed Archipelago 0.6.8 loads the world as
   v0.2.0.
2. **Seed:** 2 players, MP3 (Samus) + ChecksFinder (Finder), default options only, generated with the installed
   Archipelago (if that fails: development clone, document why). Output, spoiler, server file (`.archipelago`) and ISOs
   only outside the repo (`out/t08`). This seed stays the same for all sittings. Host the server locally; record the
   start command in the handover.
3. **ISO and client:** in the installed launcher "Open Patch" with the `.apmp3`, the client starts from the launcher,
   connection to the local server.
4. **Second game:** ChecksFinder runs without a client of its own. Its locations are released through the server
   console (`/send_location Finder <location>`), above all when MP3 needs an item from there according to the spoiler.
   The server may run as a child process with a small stdin wrapper outside the repo (commands from a file passed to the
   console); otherwise the user types them. Ask the user whether they would rather play ChecksFinder themselves.
5. **Play through with the user.** Observe and prove (client log, learning mode JSONL, server log, own read-only
   scripts outside the repo if needed):
   - every collected location arrives at the server exactly once. Compare server log against learning-mode log at the
     end of every sitting; list anomalies (unknown bytes, `location_byte_without_pickup`, `blocks_disagree`,
     SpecialFunction locations, Bryyo Fire byte 2). Every location the learning mode confirms counts as a T13 sample;
   - items in both directions, at least one progression item from ChecksFinder arrives in MP3 and is needed;
   - Progressive Beam/Missile both stages, several Energy Cells inserted (none comes back), Ship Missile/Ship Grapple in
     the game as soon as the ship is usable (T11 open), Hazard Shield against story suits (PED/Phazon, T15 open), story
     Hypermode and corruption in Bryyo with slots 35–39 set by the client;
   - flights between planets, saving/loading, death/continue, restarting Dolphin, client and server in the middle of
     the game: nothing twice, nothing missing;
   - `!hint` works, the learning mode runs through;
   - no freeze, no crash. If it happens: time, last client lines, inventory.

   Traps and "before event" cases (T21) that happen by chance: only note them, do not look for them. If the player
   cannot continue according to the logic: document place, inventory and spoiler excerpt, unlock with `/send` and note it.
6. **Goal (T17)** – before that the "extra high" effort note to the user (see above), wait for confirmation. Have the
   save backed up before the final battle. Take memory dumps (MEM1/MEM2) before the battle, right after the victory
   over Aurora Unit 313 and in the credits (outside the repo). Find a robust indicator (e.g. world ID, flag block of
   Phaaze, inventory slots, story relay) and confirm it with at least one repetition of the battle from the backed-up
   save. Then implement `client/goal.py`, write tests with fake memory. Check live: the client sends `CLIENT_GOAL`, the
   server shows the goal as reached. Afterwards the note "effort back to high".
7. **Client bugs:** fix them, with a test; then raise `world_version` in the patch part (0.2.1, 0.2.2, …), rebuild the
   `.apworld`, copy it into the installed Archipelago, restart the client. Seed and save stay. Bugs in logic, data,
   patcher or APWorld outside these files: only document, with reproduction steps, do not change.
8. **Handover** at the end of every sitting (user pause or context running out): update this file's "Handover"
   section: paths (outside the repo only relative to `MP3 Archi\`), server start command, save slot, current place in
   the game, collected/open locations, next steps, open findings. STATUS T08 stays "running" with an interim state.
   Commit and push. Tell the user to start the continuation prompt in a new session; if the final battle is due in the
   next sitting, tell them to start it with effort "extra high" right away.

**Files that may be changed:** `apworld/metroidprime3/client/`; `apworld/metroidprime3/test/test_client*.py` and
`fake_memory.py`; `apworld/metroidprime3/archipelago.json` (only `world_version`); `docs/AP_PLAYTEST_T08.md` (new),
`docs/AP_CLIENT.md` (goal, live findings, known gaps); `STATUS.md` (only rows T08, T13 and T17).
**Do not touch:** `apworld/metroidprime3/__init__.py` and the other APWorld modules, `data/`, `location_flags.py`,
`patcher/`, `apworld/tools/`, `randovania/`, `tools/`. No ISOs, game files, memory dumps, spoilers or personal paths in
the repo.

**Acceptance (over all sittings):**
1. `.apworld` built from the current commit, loaded in the installed Archipelago (v0.2.x). APWorld tests and
   `test/general` in the development clone green.
2. 2-player seed from the installed Archipelago, ISO via "Open Patch", client from the launcher.
3. Live (PrimeHack, Clock Override off): played to the victory over Aurora Unit 313. All collected locations at the
   server, none twice, none missing. Items in both directions. The points of step 5 are proven or justified as not
   reachable/not checkable. No freeze.
4. Goal detected live and reported to the server (`CLIENT_GOAL`), reproduced at least twice (once after reloading
   before the final battle). Tests for the goal detection green. The user was reminded of "extra high" before step 6.
5. Every bug found is fixed (with a test) or documented.
6. This file: Assignment, setup, course per sitting with times, checkpoint table, evaluation of the learning mode
   (incl. T13 locations), findings, open points, handover. `docs/AP_CLIENT.md` extended by goal detection and live
   findings.
7. Tell the user exactly what to do before every step and wait for their confirmation. Combine steps. Have the save
   backed up first. Only one live test at a time (do not start T14/T21 on the side).
8. Only these files committed and pushed on branch `archipelago` (`git pull --rebase origin archipelago` first).

At the end (last sitting): enter the result in STATUS.md (rows T08, T13 and T17) and write one paragraph on what was
changed and what is open.

## Setup

| Item | Value |
|---|---|
| Repo commit at start | `7cabca0ba` (branch `archipelago`) |
| APWorld | `world_version` 0.2.0 at the start, **0.2.1** from 15:59 (goal detection, B11); built with "Build APWorlds" in `Archipelago\` (dev clone), copied to `C:\ProgramData\Archipelago\custom_worlds\metroidprime3.apworld`; v0.1.0 and v0.2.0 backed up to `out\t08\apworld_backup\` |
| Generator check | installed `ArchipelagoGenerate.exe` lists `Metroid Prime 3: Corruption : v0.2.0` |
| Seed | `61579369889909122189` (spoiler header "Seed: 97512360202151153640"), generated with the installed `ArchipelagoGenerate.exe` from `out\t08\players\` (`samus.yaml`, `finder.yaml`, default options) |
| Slots | 1 = Finder (ChecksFinder, 25 locations), 2 = Samus (MP3, 99 locations) |
| Output | `out\t08\output\` (`AP_61579369889909122189.zip`, `.archipelago`, `_P2_Samus.apmp3`, spoiler) |
| Server | local, port 38281, run by `out\t08\tools\server_wrapper.py` (see handover) |
| ChecksFinder | no client; the worker releases its tiles with `/send_location Finder Tile <n>` (user's choice) |
| Emulator | PrimeHack 1.0.9 (Desktop), user folder `%APPDATA%\Dolphin Emulator`, `OverclockEnable = False` |
| Save backup before T08 | `out\t08\saves\before_t08_<time>\524d3350\` (NAND title folder of RM3P01) |

**Server: installed vs. development clone.** The installed (frozen) `ArchipelagoServer.exe` started as a child process
with a stdin pipe loads the multidata and listens, but ignores console commands from the pipe (`/players` produced no
output, also not in its own log). `MultiServer.py` of the development clone (same version 0.6.8, same MP3 code through
the junction, now v0.2.0) processes them. The server therefore runs from the development clone; generation, patching
and the client use the installed Archipelago.

## Course per sitting

### Sitting 1 (2026-11-25)

| Time | Step | Result |
|---|---|---|
| 04:00 | pull, tests | already up to date; APWorld 130 passed / 2 skipped, `test/general` 253 passed |
| 04:02 | `world_version` 0.2.0, build, install | `.apworld` 202 KB, installed generator loads v0.2.0 |
| 04:02 | seed | generated without errors (0.8 s) |
| 04:05 | server | dev clone `MultiServer.py` via wrapper, `/players` works |
| 04:10 | "Open Patch" in the installed launcher with the `.apmp3` | ISO built (`out\t08\output\AP_61579369889909122189_P2_Samus.iso`), client started from the launcher, `/connect localhost:38281`; new game in **slot 1** (old saves backed up) |
| 04:13 | ingame Valhalla | `Seed check OK … ID 80da4bad80589dd760789a00e1a2e146`; the 7 starting items came as starting inventory, nothing written |
| 04:18 | `/send_location Finder Tile 3`, `Tile 5` | Progressive Beam + Grapple Lasso from Finder, written at once (Plasma 1/1, Lasso 1/1); user: both in the pause menu |
| 04:21–05:13 | Valhalla → Norion → Bryyo Fire/Reptilicus → Norion → PH Command/Research → Norion → Bryyo → Rundas | 22 locations, each once at the server; Missile Launcher booked 4 locked expansions over (slot 68 20 → 0, Missiles 25/25); two savestate loads (B4) |
| 05:04 | `!hint screw attack` | correct hint (= spoiler) |
| 05:15–05:18 | restart test: PrimeHack + client closed, server `/exit` + restarted, all started again, save loaded | nothing sent again, nothing written, inventory complete |
| 05:23–05:24 | Hypermode until corruption → Game Over → Continue (Bryyo Fire) | inventory = save, no write; slots 35–37 untouched |
| 05:37–05:41 | Ship Missile / Ship Grapple used (Bryyo Reptilicus) | works; consumption not "refilled" by the client |
| 05:43–05:48 | Bryyo Leviathan Core without Hyper Ball | softlock (B5), escaped by savestate (B6) |
| 05:50, 06:14 | Energy Cells 1 and 9 inserted on Valhalla | not given back |
| 06:27–06:34 | Hangar Bay (SpecialFunction 42, 43) | both detected; 43 only after flying away and back (B8) |
| 07:06–14:40 | user break (asleep); server, probe and logger kept running | client lost the server connection at 14:39:57 (PC/network), reconnected 14:40:07; nothing lost |
| 14:44 | `/send_location Finder Tile 15, 17, 21` (user wants the shortest way to the goal) | Energy Tank, Grapple Voltage, Spider Ball written at once |
| 14:57 | five savestates loaded within 12 s | client wrote the final state at 14:57:54 (B6) |
| ~15:00 | crash after Elysia seed bomb part 1 (B9) | savestate; location 97 released by the server at 15:04 (Nova Beam) |
| 15:31 | location Xenoresearch B released by the server (user request) | Hyper Grapple written |
| 15:34 | saved before Phaaze; save backed up (`out\t08\saves\before_phaaze_1534\`) | 55 locations at the server, none twice |
| 15:36–16:16 | goal measurement (T17), see "Goal detection" | first victory 15:53 (measurement), goal detected live 16:07:27 and 16:16:04 |

## Checkpoints

| Checkpoint | Status | Evidence |
|---|---|---|
| every collected location exactly once at the server | ok | `reconcile.py` at the end: 99/99 at the server, none twice. 53 collected live (each: server 1×, client log ≥ 1×, learning mode ≥ 1×; re-collected after savestates/continue never sent again), 2 released by the worker on request (97, Xenoresearch B, B9/B10), 44 by the server's auto-release after the goal |
| items in both directions, CF progression item needed in MP3 | ok | CF → MP3: Progressive Beam (Tile 3), Grapple Lasso (Tile 5) at 04:18:43, written at once; Grapple Lasso is progression (Green Lock). MP3 → CF: Map Height/Width/Bombs ×4 (04:28–05:21) |
| Progressive Beam both stages | ok | Plasma Beam 0/0 → 1/1 (04:18:43, from CF); Nova Beam 0/0 → 1/1 (15:04:25, location 97 released by the server, B9) |
| Progressive Missile both stages | ok (stage 2 via release) | Ice Missile 0/0 → 1/1 (04:40:51, location 89); Seeker Missile 0/0 → 1/1 at 16:08:49, when the auto-release after the goal delivered the second Progressive Missile (not from a live pickup) |
| several Energy Cells inserted, none comes back | ok (2 cells) | cells 1 and 9 received (Fuses 2/9). 05:50:46 cell 1 inserted on Valhalla: 22 2/9 → 1/9, 52 0/9 → 1/9, 23 Fuse1 → 0/1, 53 Fuse1Used → 1/1. 06:14:14 cell 9 inserted: 22 1/9 → 0/9, 52 → 2/9, 31 Fuse9 → 0/1, 61 Fuse9Used → 1/1. The client gave neither back (checked 05:56 and 06:14:29; its only write in between was an Energy Tank) |
| Ship Missile / Ship Grapple in game | ok | Ship Grapple 1/1 (04:36:59), Ship Missile 3/3 (04:57:59) written by the client. ~05:37–05:41 Bryyo Reptilicus: user used both successfully (T11 open point closed). Slot logger: Ship Missile 3/3 → 2/3 (05:37:43), back to 3/3 by the game (05:37:59), 3/3 → 2/3 (05:41:26); the client wrote nothing (consumption stays, ammo rule) |
| Hazard Shield vs. story suits (PED/Phazon) | ok / PED not checkable | Hazard Shield: Suit 0/6 → 5/6 (04:52:21). PED Suit is the starting state of the AP seed (after the Norion story), no event. Phaaze: the game set slot 41 (HyperModePhaaze) 0/0 → 1/1 about a minute after landing; suit stayed 5/6 through Phaaze and the final battle, no freeze. In the end sequence the game sets suit 5 → 0 (T17) |
| story Hypermode / corruption in Bryyo with slots 35–39 | corruption ok | 05:23:44–05:24:21, Bryyo Fire, saved before: Hypermode held until the bar turned red → Game Over → Continue. Slot logger: only 47 0/1 → 1/1 → 0/0; 19, 42, 46 stayed 0/0 (corruption is not stored in these slots); 35–37 stayed 1/1. No freeze, no client write needed |
| planet flights | ok | Valhalla → Norion → Bryyo Fire/Reptilicus/Ice ↔ Norion ↔ Pirate Homeworld Command/Research: "Ingame: <world>" each time, blocks found, no duplicate check |
| saving/loading | ok | saved at 05:15, loaded after the restart at 05:18: inventory complete from the save, no write needed |
| death/continue | ok | 05:24:03 Game Over (client: "No longer ingame"), 05:24:21 continue: inventory = save, nothing written, nothing sent. Also two savestate loads (B4) |
| restart Dolphin / client / server mid-game | ok | 05:15 PrimeHack and client closed, server stopped with `/exit` and restarted ("Loaded save file with 24 received items"), 05:18 client + PrimeHack again: seed check OK, saved locations recognised, **nothing sent again**, no write needed |
| `!hint` | ok | 05:04:14 `!hint screw attack` → "Skybridge Hera" = spoiler; shown in the client's Hints tab |
| learning mode runs through | ok | 61 entries in two files (57 `pickup`, 4 `blocks_disagree`), no error; 3 false "pickup without location byte" warnings from savestate jumps (B6). Evaluation below |
| no freeze / crash | one game crash, not the client | ~15:00 crash after an out-of-order Elysia story sequence (B9, T21 note). Otherwise no freeze over ~5 h of play, incl. the whole pool written at once (Missiles 244/245, 14 Energy Tanks, 11 Ship Missiles) |
| goal detected, `CLIENT_GOAL` (T17), 2× | ok | 16:07:27 and 16:16:04 (client v0.2.1, both after loading the savestate before the final battle, the second with a freshly started client); server: "Samus (Team #1) has completed their goal", `/status`: "Samus … has finished (99/99)". Section "Goal detection" |

## Learning mode evaluation (T13)

Files `C:\ProgramData\Archipelago\logs\MP3Client_learning_2026-11-25_04-10-41.jsonl` and `…_05-17-54.jsonl`
(later client starts logged no pickups). Evaluated with `out\t08\tools\t13_eval.py` (read only).

**53 locations confirmed live**, every one exactly as in `location_flags.py` (byte and world), **no difference to the
table**. They cover 9 worlds (Valhalla, Norion, Bryyo Fire/Reptilicus/Ice/Seed, Elysia Main/Pod, PH Command/Research)
and all were `FF FF FF FF` pickups (AP mode). Each is a T13 sample:

| World | Locations (byte) |
|---|---|
| G.F.S. Valhalla | 11 (1), 12 (11), 13 (12) |
| Norion | 4 (8), 5 (15), 6 (119), 7 (36), 10 (57) |
| Bryyo - Fire | 17 (6), 18 (10), 19 (14), 20 (20), 21 (148), 23 (28, Rundas drop) |
| Bryyo - Reptilicus | 25 (20), 26 (22), 28 (25), 29 (27), 30 (148), 31 (47), 32 (253), 33 (66), 35 (70), 37 (150), 38 (80), 40 (101), 41 (105), **42 (109)**, **43 (107)**, 46 (143), 47 (144) |
| Bryyo - Ice | 48 (20), 49 (44), 50 (21) |
| Bryyo - Seed | 98 (0, after Mogenar) |
| SkyTown, Elysia - Main | 51 (6), 52 (1), 53 (12), 54 (13), 56 (40), 59 (68), 60 (76), 61 (75), **62 (81)**, 63 (85), 66 (114) |
| SkyTown, Elysia - Pod | 71 (44), 74 (86) |
| Pirate Homeworld - Command | 86 (1), 88 (9), **89 (10)**, 90 (178) |
| Pirate Homeworld - Research | 84 (147) |

**SpecialFunction locations ("probable", T12):** 4 of 10 confirmed live: **42, 43, 62, 89** (bold above). Not visited
live: 9, 34, 70, 73, 79, 93 (released by the server after the goal).

**Locations with `other_bytes` (64/77/87/95):** none collected live, not checked.

**Unknown bytes** (set next to a location byte within the window, story/room relays, no location): Valhalla 63, 79, 80;
Norion 1, 66, 73, 118, 126; Bryyo Fire 116, 129, 147; Bryyo Reptilicus 49, 165, 166, 175, 205, 232, 259, 260; Bryyo Ice
36, 40; Elysia Main 5, 42, 72, 79, 86, 157, 185, 194, 196, 198; PH Command 3, 15, 109. **Bryyo Fire byte 2** (T06) was
not seen in this run (route via Main Lift/Imperial Hall without it); it stays unclassified.

**Other entries:** 4× `blocks_disagree` (Norion 3× at 04:23 while collecting location 4, B2; Bryyo Fire 1× at 05:24:21
right after the continue, three blocks differing only in non-location bytes 60–66, 77, 78, 102, 104, 105, 153). No
`location_byte_without_pickup`. 3 "pickup collected without the expected location byte" = savestate jumps (B6), no
real pickup.

## Goal detection (T17)

**Measurement.** `out\t08\tools\goal_probe.py` (read only) logged every 0.1 s: `[0x80680234]`, world ID, CPlayer
holder/pointer/vtable, PS and slots 0, 17, 19, 20, 21, 40–42, 46–50; MEM1 (24 MiB) + MEM2 (64 MiB) dumps on every world
or ingame change and on demand (`out\t08\dumps\`, 10 dumps, outside the repo). Analysis scripts `analyze_dumps.py`,
`phaaze_block.py`, `dump_slots.py`.

| Time | Moment | World | CPlayer | Slot 41 HyperModePhaaze | Suit 17 | Phaaze flag block |
|---|---|---|---|---|---|---|
| 15:37:54 | arrival on Phaaze (dumps 02–06) | `4B07619AB6125B33` | loading, then valid | 0/0 | 5/6 | all 0 |
| 15:39:10 | ~1 min after landing | Phaaze | valid | **1/1** | 5/6 | – |
| 15:47:24 | before the final battle (dump 07) | Phaaze | valid | 1/1 | 5/6 | 25 bytes set |
| 15:53:16 | right after the victory over Aurora Unit 313 (dump 08) | Phaaze | valid | 1/1 | 5/6 | **unchanged** |
| 15:54:10.705 | start of the end cutscene | Phaaze | valid | **0/1** | **0/6** (+ Grapple Lasso/Swing/Voltage 1/1 → 0/1) | – |
| 15:54:11 (dump 09), 15:56:38 (dump 10) | end cutscene, credits | Phaaze | **still valid** | 0/1 | 0/6 (v0.2.0 client wrote 5/6 back, B11) | unchanged |

Rejected candidates: world ID (stays Phaaze through cutscene and credits), Phaaze flag block (no byte changes from
before the battle to the credits), ingame/menu (CPlayer stays valid in the credits), slot 40/42/46 (unchanged), static
memory diffs (114 774 changed words in `0x80580000–0x80700000` between two dumps: noise).

**Indicator:** ingame, world Phaaze, inventory filled, **slot 41 = 0/1** (amount 0, capacity 1), two consecutive polls.
Slot 41 is only 1/1 while on Phaaze and drops to 0/1 exactly when the end sequence starts; the client never writes it
(now in `READ_ONLY_SLOTS` together with 40 and 42). Timing: about 1 minute after the boss dies (start of the end
cutscene), not at the boss's death itself.

**Repetitions** (savestate before the final battle):

| Run | Client | Indicator | Client log | Server |
|---|---|---|---|---|
| 1 (15:47–15:54) | v0.2.0 (no detection) | 15:54:10.705 slot 41 1/1 → 0/1 | – | – |
| 2 (16:01–16:07) | v0.2.1, restarted, savestate loaded 16:01:12 | 16:07:26.652 | 16:07:27.589 "Goal reached: Aurora Unit 313 …", "Goal sent to the server (CLIENT_GOAL)"; no write during the end sequence | "Samus (Team #1) has completed their goal"; auto-release of the remaining 44 locations; `/status` "Samus … has finished (99/99)" |
| 3 (16:10–16:16) | v0.2.1, freshly started, savestate loaded | 16:16:03.871 | 16:16:04.448 "Goal reached …", "Goal sent …" | already finished (99/99) |

Implementation: `client/goal.py` (`ending_sequence`, `GoalDetector`), `context.py` (`observe_goal`, `send_goal`: no item
giving while the end sequence runs, `CLIENT_GOAL` once per connection, also sent later if detected offline),
`/dolphin` shows the goal state. Tests `test/test_client_goal.py` (10 tests). `world_version` 0.2.1.

## Findings

| ID | Time | Finding | Classification / action |
|---|---|---|---|
| B1 | S1 04:21 | A received Energy Tank shows up **empty**: the client raises slot 20 (Energy Tank) 0/0 → 1/1, but the current energy (health) is not refilled, unlike a vanilla tank pickup. User: "I always get an empty energy tank." | Client gap, not a write error (slot value correct, HUD shows the tank). The health address is not known (`AP_MEMORY_MAP.md` slot 18 "Energy" is not the health). Workaround: saving at the ship / energy pickups refill the tanks (T15). Not fixed in T08; possible follow-up: measure the health address, refill on a new tank |
| B2 | S1 04:23 | Norion: **three** valid blocks (`0x80A042C0` in MEM1, `0x8117F8E0`, `0x81188780` in MEM2). While walking to and collecting location 4 the learning mode logged `blocks_disagree` three times (bytes 6 → 1, 6, 118 → 1, 6, 8, 118): the newly set bytes appear in one block first. Location 4 was still sent exactly once (OR assumption) | Note for T14 (live copy / OR). No wrong check so far |
| B4 | S1 04:43, 04:48 | User loaded **Dolphin savestates** twice (Pirate Homeworld Command/Research). RAM incl. inventory and flag block goes back without a menu/loading phase (CPlayer stays valid). The client re-gave what was missing at once (Energy Tanks 1/1 → 2/2 at 04:43:20, Hyper Missile 0/0 → 1/1 at 04:48:25); location 84 was collected again after the savestate (learning mode logged it twice), the server got it once | Works like death/continue (E11 target/current). Expected, no action |
| B5 | S1 05:43–05:48 | **Softlock in the Bryyo Leviathan Core** (Bryyo - Seed). Entered without Hyper Ball, beat Mogenar, collected location 98 "Bryyo Leviathan Core - Pickup (Hyper Ball)" (here: Missile Expansion, sent once at 05:47:10). The only way out needs Hyper Ball → stuck; the user escaped with an older savestate. Inventory then: Power/Plasma/Charge, Missiles 60, Ice Missile, Grapple Lasso/Swing, Boost Ball, Command Visor, Hypermode + Hyper Missile, 2 Energy Tanks, cells 1 + 9, Hazard Shield, Ship Missile/Grapple – **no Hyper Ball** (spoiler: Hyper Ball at "Bryyo - Reptilicus - Ruined Shrine - Pickup (Energy Tank)", sphere 11) | **Logic/converter gap, not the client.** `Bryyo - Seed.txt`: Door to Core Access → Event - Mogenar (bombs, morph, hypermode, damage) → Pickup (Hyper Ball) (trivial) → Dock to Bryyo - Reptilicus only with "Use Hyper Ball"; no way back. AP logic only checks reachability, so location 98 counts as reachable without Hyper Ball. E18's `escape_requirement` only covers events that occur negated, not one-way rooms after a boss. Reproduction: this seed, go to Bryyo - Seed before Ruined Shrine, beat Mogenar, take the pickup. Proposal for the converter (not changed here): add an escape requirement (path back to a ship/teleporter) to every connection into nodes without a way back, or at least to the Mogenar event. Workaround: reload the save |
| B6 | S1 05:48:49 | Savestate jump: the user loaded an old savestate (Pirate Homeworld Command, ItemPercentage 11) and right after it another one (Bryyo Seed, ItemPercentage 28). The client wrote into the old state after 0.2 s (11 slots, all correct target values) and into the next one again (Missiles 55/55 → 60/60). Learning mode: "ItemPercentage 11 -> 28 … pickup collected without the expected location byte" | Harmless: absolute targets. The learning mode treats a savestate jump as a pickup (false warning). Savestates keep `[0x80680234]` and `PS`, so the client's "settle 2 polls after loading" does not trigger. Note only. Again at 14:57:34–14:57:46: the user flipped through five savestates within 12 s (Valhalla, Bryyo Seed, PH Command, Elysia Main, PH Research, Elysia Main). The client wrote the full target into each state; when the next savestate replaced the state before the read-back, it logged "Changed by the game" for 10 slots and throttled them (5 s, then 10 s). At 14:57:54 it wrote the final state once (Missiles 79/80 → 84/85, Voltage, X-Ray, Screw Attack, Energy Tanks 6 → 8, cells 4 + 8, Spider Ball, Ship Missiles 3 → 4); read at 14:58:28: everything received is present, inserted cells 1 + 9 not given back. User asked "send me the items I should have" – nothing to send, the client had already restored them |
| B7 | S1 | Slot logger (read only) on story slots: 42 HyperModeOriginal = 1/1 in the old savestate (~04:42), 0/0 from 05:23 on (cleared by the game in between, probably by a Bryyo story event); 40 HyperModePermanent capacity 0 → 1 at 05:47:09.9, right after beating Mogenar/collecting location 98 | For T15 (story slots). The client never writes 40–42; no conflict |
| B8 | S1 06:27–06:34 | Location 43 (Bryyo Reptilicus, Hangar Bay, ship upgrade "Ship Missile", SpecialFunction): the command field for the ship upgrade was greyed out. Cause (user): the ship still held an object with the Ship Grapple; after releasing it, the ship flew to the hangar, but the game did not register the ship there (the scaffold could be moved up and down). After flying elsewhere and back it worked: location 43 at 06:34:25, learning mode byte 107 (status "probable" → confirmed) | Game state quirk around the ship grapple, not the client and not because Ship Missile was already given by the client (it was 3/3 since 04:57 and the upgrade still worked). Workaround: fly away and back |
| B9 | S1 ~15:00 | User: the game **crashed** near the Elysian Leviathan Core (location 97); the user went back to an older savestate far away. No "Lost connection to Dolphin" in the client log (the client kept polling; last entries 14:57:54 write, 15:02:59 `!hint Progressive Beam`) | **Cause (user):** in the Elysia bomb sequence only **part 1 of the seed bomb** was collected (no Seeker Missile to continue), then the user went back to SkyTown Elysia - Main → the game crashed there. Game/story state, not the client (no client write or error around it). Classification: event order outside vanilla, belongs to T21 ("before event"/sequence cases, noted only, not reproduced). Reproduction: this seed, Elysia bomb sequence without Seeker Missile, take bomb part 1, return to Elysia Main. On request, location 97 was **released by the server** at 15:04:25 (`/send_location Samus SkyTown, Elysia - Seed - Elysian Leviathan Core - Pickup (Hyper Missile)`): Progressive Beam stage 2 → Nova Beam 0/0 → 1/1 written at once. Location 97 therefore not collected live (no learning-mode sample) |
| B10 | S1 15:31 | On the user's request (shorten the run to the goal), location "SkyTown, Elysia - Pod - Xenoresearch B - Pickup (Seeker Missile)" was **released by the server** (`/send_location Samus …`): Hyper Grapple 0/0 → 1/1 at 15:31:14 (slot 39, with slot 36 already 1/1) | Server release, not a live pickup; location not in the learning mode |
| B11 | S1 15:54:10 | **Client bug (fixed in v0.2.1):** in the end sequence the game strips suit (5 → 0) and Grapple Lasso/Swing/Voltage (amount 1 → 0); client v0.2.0 wrote them back 2 ms later ("Written to the game: Grapple Lasso 0/1 -> 1/1, …, Suit 0/6 -> 5/6") | Fixed: while the goal condition holds the client gives nothing (`context.observe_goal`); test `test_goal_sent_once_and_no_writes_in_ending`. Live run 2/3: no write in the end sequence, suit stayed 0/6 |
| B12 | S1 16:07:27 | After `CLIENT_GOAL` the server auto-released ("Release: auto") the remaining 44 locations; the own items among them arrived at once and were written after the savestate reload (16:08:49: Missiles 84/85 → 244/245, Seeker Missile, Energy Tanks 9 → 14, cells 2/3/7, Ship Missiles 4 → 11) | Expected Archipelago behaviour. Side result: almost the whole pool in game at once, all values within the limits (Missiles 244/245, Energy Tanks 14/14, Ship Missiles 11/11), no freeze |
| B3 | S1 04:23 | Norion pickup at location 4 (byte 8) also set bytes 1 and 118 (unknown, not location bytes); byte 6 was set before the pickup | Story/room relays, as already seen in T06/T12 (Norion 118). Location confirmed (T13) |

## Open points

- **T13 rest:** 6 SpecialFunction locations (9, 34, 70, 73, 79, 93) and the `other_bytes` locations (64/77/87/95) were
  not collected live; Bryyo Fire byte 2 not seen again. The learning mode stays on for later playtests.
- **B1 Energy Tank refill:** received tanks stay empty (health address unknown).
- **B2/T14:** several valid blocks per world (Norion 3, Bryyo Fire 3); OR assumption held, no wrong check. T14 open.
- **B5 Leviathan cores, B9 Elysia bomb sequence:** logic/patcher topics (T21, converter), only documented.
- **Goal timing:** detected at the start of the end cutscene (~1 min after the boss dies); a player who resets during
  that minute does not get the goal. The boss's death itself showed no stable marker in the dumps.
- **Phaaze saves:** not tested whether slot 41 can be 0/1 after loading a save made on Phaaze (no save was made
  there). The goal condition would then fire falsely; low risk, noted in `goal.py`/`AP_CLIENT.md`.
- **Release after goal (B12):** auto-release is the server default; nothing to do.
- **Leviathan seed warning in the client (user wish, later in T08 or after):** when the player enters a Leviathan
  seed world, warn in the client window if the exit item is missing (B5): Bryyo Seed → Hyper Ball (location 98),
  SkyTown Elysia Seed → Hyper Missile + Missile ≥ 4 (location 97), Pirate Homeworld Seed → Hyper Grapple + Grapple
  Voltage (location 99), taken from `randovania/games/prime3/logic_database/* - Seed.txt`. No warning if the core's own
  pickup gives the exit item to this player (`LocationScouts`). Would be client-only (`client/`), with tests, then
  `world_version` 0.2.x. The user decided on 2026-11-25 to build it later.
- **In-game text via a DOL hook (user wish, F10):** the user wants to push messages into the game later (received
  items, warnings such as the seed trap). Not possible today: the game shows texts only for its own pickups,
  Randovania has no MP3 string display (T02), no DOL hook in the MVP (E16). Needs a hook that calls the game's HUD
  message function (patcher/DOL work, outside T08).
- **Own Archipelago model for foreign items (user wish, after the MVP):** today foreign items use the Energy Cell
  model and the shared text "Archipelago-Item" (E14, T16). The user wants an own AP model, **simple, not elaborate,
  roughly like the AP items in the 2s2h world (Majora's Mask)**, and per-location texts such as "Map Bombs for
  Finder". Needs a new model/STRG in the patcher (outside T08).
- **Proper fix for B5:** logic/converter (escape requirement for the three Leviathan cores) and/or patcher (core doors
  stay closed without the exit item). Outside T08.

## Handover

**State 2026-11-25 16:20: T08 finished** (goal reached and detected live; no further sitting needed for T08).

| Item | Value |
|---|---|
| Seed | `61579369889909122189` (output `out\t08\output\`, spoiler `AP_61579369889909122189_Spoiler.txt`) |
| Server start command | from `MP3 Archi\out\t08`: `..\..\Archipelago\.venv\Scripts\python.exe -I tools\server_wrapper.py "<abs. path>\out\t08\output\AP_61579369889909122189.archipelago" server_cmds.txt server.log 38281` (runs `MultiServer.py` of the dev clone; append console commands to `server_cmds.txt`; stop with a `/exit` line). Save state `output\AP_61579369889909122189.apsave`: Samus finished 99/99, Finder 19/25 |
| Client | installed launcher → "Metroid Prime 3 Client", `/connect localhost:38281`, slot `Samus`; `.apworld` v0.2.1 |
| ISO | `out\t08\output\AP_61579369889909122189_P2_Samus.iso` (seed ID `80da4bad80589dd760789a00e1a2e146`) |
| Save | NAND slot 1 (last in-game save 15:34 before Phaaze, copy `out\t08\saves\before_phaaze_1534\`); user savestate right before the final battle; save before T08: `out\t08\saves\before_t08_*\` |
| Logs | server `out\t08\server.log`; client `C:\ProgramData\Archipelago\logs\MetroidPrime3Client_2026_11_25_*.txt`; learning mode `MP3Client_learning_2026-11-25_*.jsonl`; slot logger `out\t08\slots_hyper.log`; goal probe + dumps `out\t08\dumps\` |
| Read-only tools | `out\t08\tools\` (`reconcile.py`, `inv.py`, `slot_logger.py`, `goal_probe.py`, `analyze_dumps.py`, `phaaze_block.py`, `dump_slots.py`, `t13_eval.py`) |
| Locations | 99/99 at the server: 53 live, 2 released on request (B9, B10), 44 auto-released after the goal |

Next steps (outside T08): Leviathan seed warning in the client (open points), B1 health refill, T13 rest, T14, T21
(B5, B9), in-game texts/own AP model (F10).
