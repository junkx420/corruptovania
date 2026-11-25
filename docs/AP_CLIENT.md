# Metroid Prime 3 Client (T06 connection and location checks, T07 item giving and seed check)

As of 2026-11-25 · Archipelago 0.6.8 · **PAL `RM3P01`** only (SPEC E7) · Dolphin or PrimeHack

The client reads game memory through `dolphin-memory-engine`, detects collected locations from the flag block of the
current world (SPEC E8, E12) and reports them with `LocationChecks`. It gives received items by writing absolute target
values into the inventory (SPEC E9, E11) and only does either of these when the seed ID in the running ISO belongs to
the connected slot (T18 part 2).

Code: `apworld/metroidprime3/client/`, tests: `apworld/metroidprime3/test/test_client.py` (T06) and
`test_client_items.py` (T07).

## 1. Start

Requirements: Archipelago checkout with the APWorld linked in as described in `docs/AP_APWORLD_DEV.md` (section 1),
`dolphin-memory-engine >= 1.3.0` in the venv (comes with `ModuleUpdate.py --yes` through the Wind Waker world,
otherwise `.venv\Scripts\python.exe -m pip install "dolphin-memory-engine>=1.3.0"`).

1. Start Dolphin or PrimeHack and boot the ISO built from **this slot's** `.apmp3` (`AP_APWORLD_DEV.md` section 6).
2. Start the client, either in the launcher (**"Metroid Prime 3 Client"**, or by opening the `.apmp3`) or directly:

   ```powershell
   .venv\Scripts\python.exe Launcher.py "Metroid Prime 3 Client"
   ```

   Without GUI, connected right away:

   ```powershell
   .venv\Scripts\python.exe Launcher.py "Metroid Prime 3 Client" -- --nogui --connect localhost:38281 --name Samus
   ```

3. In the client type `/connect <host:port>` (unless `--connect` was given), then the slot name.

The order does not matter: the client reconnects to Dolphin every 5 s until it works. Location checks and item giving
start as soon as the client is connected to the server **and** the seed check passed (section 5).

Local test server: generate a seed (`AP_APWORLD_DEV.md`, section 2), then
`.venv\Scripts\python.exe MultiServer.py output\AP_<seed>.zip` (port 38281). Items for tests can be given in the server
console with `/send <player> <item>` and `/send_multiple <amount> <player> <item>`.

## 2. Configuration

| Option (command line) | Default | Meaning |
|---|---|---|
| `--connect host:port`, `--password`, `--name` | – | server, password, slot name (as in CommonClient) |
| `url` (positional) | – | `archipelago://name:pass@host:port` (launcher links) |
| `--poll-interval s` | `0.5` | poll interval in seconds |
| `--no-learning` | off | turn off the learning mode |
| `--learning-log PATH` | `<Archipelago>\logs\MP3Client_learning_<time>.jsonl` | log file of the learning mode |
| `--nogui` | off | without the Kivy window |

Commands in the client:

| Command | Effect |
|---|---|
| `/dolphin` | connection and game state (ingame, world, ItemPercentage), seed check, counts of locations/items/writes |
| `/seed` | result of the seed check |
| `/inventory` | target and current value of every slot the client manages (as of the last poll), blocked/given-up slots |
| `/blocks` | flag blocks found per world (addresses), rejected blocks, number/duration of scans |
| `/learning [on\|off]` | toggle the learning mode or show its status, log file, entries/warnings |
| `/poll [s]` | show/set the poll interval (0.1–5 s) |
| `/missing`, `/received` … | standard CommonClient commands |

## 3. What happens per poll

1. **Dolphin connection** (`memory.MemoryAccess`): hook, the game ID at `0x80000000` must be `RM3P01`. Otherwise a clear
   message ("Wrong game in Dolphin: game ID …"), disconnect at once, read nothing but the game ID, write nothing; next
   attempt after 5 s. The game ID is checked again on every poll and before every write (game switched in a running
   emulator). Any read/write error counts as a lost connection: disconnect, forget everything session-related, retry
   after 5 s.
2. **State** (`game.read_game_state`): ingame ⇔ CPlayer pointer `[[0x805C7570+0x28]+0x2184]` valid **and** vtable
   `0x80595238` (AP_MEMORY_MAP.md, section 6). In the menu/while loading only these pointers are read; blocks,
   debouncing, learning mode and item giving are reset. Ingame: world `[0x80680234]+8`, `ItemPercentage` (slot 21),
   `PowerBeam.capacity` (slot 0, "inventory filled") and the `[0x80680234]` pointer itself (changes on loading).
3. **Seed check** (section 5): build string of `main.dol` from RAM, compared with seed/slot of the server.
4. **Flag block** (`flag_block.FlagBlockFinder`, E8): check the remembered address, rescan at once on a mismatch,
   otherwise at most every 2 s if nothing was found. A scan reads MEM1 (24 MiB in 1 MiB chunks, about 90 ms) and finds
   the blocks of **all** worlds at once. Signature (all mandatory):
   - `W−4 = 0xEAEAEAEA`, `W+0 = MLVL ID`, `W+0x18 = 0x400`;
   - `[W+0x08]` points to a descriptor with `"SAVW"` at +8 and the world's SAVW ID at +16;
   - `[W+0x10]` points to the SAVW object whose list-1 length (`+0x10`) matches the world;
   - plausible: all bytes from the list-1 length on are 0.

   After reading the 1024 bytes the signature is checked once more (the block might have been freed meanwhile).
   SAVW ID and list-1 length per world are in `flag_block.SAVW_INFO` (from the PAL ISO, MLVL `+0x14` and SAVW).
5. **Checks** (`checks`, only with a passed seed check): bytes from `location_flags.py` for the current world; a location
   counts when its byte is set in **2 consecutive polls** (debouncing). AP ID = `0x4D503300 + pickup index`. Each
   location is sent at most once per session; locations the server already reports as checked (`checked_locations`)
   are not sent, and only locations the server knows (`server_locations`) are sent. Locations of earlier worlds are in
   the save and are seen again on the next visit, but not sent twice.
6. **Learning mode** (section 7), independent of the seed check.
7. **Item giving** (section 4, only with a server connection and a passed seed check).
8. **Goal** (section 6, open).

## 4. Item giving (T07, SPEC E9, E11)

Code: `client/inventory.py` (effect table, slot limits, target, write plan), `client/give.py` (per poll: settling,
writing, read-back, throttling).

### 4.1 Target values

There is **no stored index**. On every poll the client computes the target of every slot it manages from

- the starting items (`slot_data["starting_items"]`, else the APWorld's own list), and
- **all** received items (`items_received`, `items_handling = 0b111`, SPEC E10: own items come from the server too).

With `0b111` the server also sends the precollected starting items itself, as starting inventory (location `-2`,
player 0). A starting item therefore only counts as far as it was not received that way (`inventory.effective_items`),
so nothing counts twice. Items given with the `start_inventory` option arrive the same way and do count.

The **effect table** (`inventory.ITEM_EFFECTS`) is the client's own data; each entry lists per stage which slot gets how
much capacity/amount. Origin (also noted in the module):

| Data | Source |
|---|---|
| slot per resource (`RESOURCE_SLOTS`) | Randovania `logic_database/header.json`, `long_name` → `extra.item_id` (= AP_MEMORY_MAP.md 3) |
| amount per pickup | MP3Randomizer `Item.cs` (`capacity`/`amount`): Missile Launcher/Expansion +5, Ship Missile +3, Ship Missile Expansion +1, Suit +5, everything else +1 |
| stages, launcher lock | `data/items.py` (converter T03 from Randovania's `pickup-database.json`) |
| limit and bits per slot (`SLOT_LIMITS`) | `docs/AP_SLOT_LIMITS.md` section 4 (DOL table `0x8057D5F8` = `max_capacity`) |

Every target is clamped to `min(tab_max, 2^bits − 1)` of its slot, so every written value survives saving (T19:
the save keeps `value mod 2^bits`). With the whole pool: Missiles 245/245, Energy Tanks 14/14, Ship Missiles 11/11,
everything else within its limit (test).

### 4.2 Write rules

| Rule | Slots | Behaviour |
|---|---|---|
| `raise` | abilities (1 bit): beams, missile upgrades, grapples, visors, Screw Attack, Boost/Spider Ball, hyper slots 35–39, Ship Grapple 44, starting items | amount and capacity each raised to at least the target, never lowered |
| `ammo` | 4 Missile, 20 Energy Tank, 45 Ship Missile | only if capacity < target: capacity = target and amount raised by the same difference. A lower amount is consumption and stays |
| `suit` | 17 | Hazard Shield: fixed **5/6** (amount is an index, 13 freezes the game; capacity 11 becomes 3 after saving, T11/T19). Amounts 5–7 and capacities 6–7 are left alone, nothing ≥ 8 is ever written. Without Hazard Shield the suit is never touched |
| `cell` | 22–31 | Energy Cell i: Fuse_i amount 1 while received **and** not inserted (Fuse_iUsed, slot 52+i, amount > 0), otherwise nothing. Slot 22 (cells total) = received minus inserted, capacity 9. Only raised; an inserted cell is never given again |
| `exact` | 68 | locked missiles (Stat_TinCanHighScore, T10 test C): 5 per Missile Expansion without launcher, 0 once the launcher is there (the load is moved to slot 4) |

Special cases:

- **Progressive items** give their stages in pool order: the n-th copy gives stage n (Progressive Beam: Plasma, then
  Nova; Progressive Missile: Ice, then Seeker). Visors and hyper items are single items in the pool; the engine would
  handle stages for them the same way.
- **Missile Launcher / Expansions (E15):** the AP patch has missile-required off, so the client models the lock.
  Expansions before the launcher go to slot 68 (5 each, as the game does it, T10), slot 4 stays 0/0. When the launcher
  arrives, slot 4 = 5 + 5 × expansions and slot 68 = 0/0 ("booked over"). Since the target is computed from all
  received items, the order does not matter.
- **Ship Missile Expansions** before the Ship Missile are not booked anywhere (slot 69 is not saved, T19); they count
  as soon as the Ship Missile arrives (3 + 1 per expansion).
- **Hyper items** (Hypermode, Hyper Missile, Hyper Ball, Hyper Grapple) additionally set **slot 36** (HyperModeBeam) to
  1/1: without it the pause menu shows "???" instead of "Hypermode" (T11).
- **Energy cells** always write slot 22 as the counter as well (cells 23–31 alone do not show up, T11).
- The client never writes ItemPercentage (21), 43, 47, 52–61 or 69 (`inventory.READ_ONLY_SLOTS`), and never the third
  word of a slot.

### 4.3 When the client writes

- Only with a server connection (without one `items_received` is empty) and a passed seed check.
- Only ingame (CPlayer vtable) **and** with a filled inventory (`PowerBeam.capacity > 0`), never in the menu, while
  loading or during the intro.
- Every change of the game state (new `PS` or new `[0x80680234]` pointer, e.g. after loading or continue) and every
  menu/loading phase resets the item giver; it then waits for **2 valid polls in a row** before it writes (inventory just
  filled from the save).
- The client cannot read a "dead" state (no address known). Values written during the death animation would simply be
  overwritten by the save on continue, after which the rules above apply. In the live test nothing was written between
  death and continue.

### 4.4 Read-back and throttling

What was written in one poll is read back in the next poll (0.5 s later). If the game changed the value **and** the slot
is below target again, that is a failure: a warning in the log (`… wrote a/c, read back a'/c'. Changed by the game, next
attempt in 5 s.`), and the slot is blocked for 5, 10, 20, 40 s. After 5 failures the slot is not written again until the
next load/menu (error in the log). Consumption right after a write (e.g. a missile fired) is not a failure, because the
slot is not below target. So the client never writes in a loop.

### 4.5 Messages in the client window

- Every received item once: `Received: <item> from <player> (<location>)`, own items `from yourself`, server items
  `from Archipelago (Cheat Console)`, starting inventory `Received: <item> (starting inventory)`. After a reconnect the
  server resends the whole list; entries already announced are not repeated.
- Every write as one line per poll: `Written to the game: Missiles 0/0 -> 15/15, Grapple Lasso 0/0 -> 1/1, …`.
- `/inventory` shows target/current per slot.

### 4.6 Death, continue, older save, reconnect

Death/continue and loading a save reset the inventory to the save byte for byte (T15). Because the target is absolute,
the next comparison gives exactly what is missing compared with the save and nothing twice (live: section 8).
Reconnects and duplicate `ReceivedItems` packets are handled by CommonClient's index (`index 0` = full list, a
mismatching index triggers `Sync`); the target only depends on the resulting list.

## 5. Seed check (T18 part 2)

Code: `client/seed_check.py`. The patch tool writes `patcher.seed_id.make_seed_id(seed_name, slot)` (first 16 bytes of
`SHA-256("metroidprime3-ap\0<seed_name>\0<slot>")`) into bytes 6–22 of the `main.dol` build string
(`AP_PATCH_TOOL.md` 2.2). On every ingame poll the client reads the 57-byte build string (PAL `0x805843A8`), extracts the
ID with `patcher.seed_id.seed_id_from_build_string` (the same function the patch tool uses) and compares it with
`make_seed_id` of the server's `seed_name` (RoomInfo) and its own slot.

| Status | Meaning | Checks / items |
|---|---|---|
| `OK` | ISO belongs to this seed and slot | active |
| `MISMATCH` | ISO of another seed or another slot: `WRONG ISO: the seed ID in the game (…) does not belong to seed …, slot … (expected …)` | none |
| `VANILLA` | original build string (unpatched ISO or not built with the AP patch tool): `NOT AN AP ISO: …` | none |
| `UNREADABLE` | build string not as expected | none |
| `WAITING` | seed/slot unknown (never connected to a server) | none |

Details:

- Without a server connection the client checks against the **last successful connection**
  (`connected_identity`). Locations found offline are noted and sent with the next `Connected`; if the next connection
  is a different seed/slot, CommonClient clears them first.
- Before the very first server connection nothing is noted (the ID cannot be checked yet). Change from T06: the flags
  are in the save, so the locations are detected right after connecting anyway.
- When the status leaves `OK` (other ISO loaded, other slot connected), the client forgets the locations it confirmed
  and resets the item giver.
- Status changes are logged once (errors as `ERROR`); `/seed` shows the current status.

## 6. Goal (open, T17)

`client/goal.py` is the prepared interface: `GoalDetector.reached(memory, state)` is called on every ingame poll with a
passed seed check; on the first `True` the client sends `StatusUpdate` with `CLIENT_GOAL`. How the victory over
"Aurora Unit 313" (`slot_data["goal_event"]`) shows up in memory is **not measured** (T17). Phaaze has no locations and no
flag block in `location_flags.py`, so detecting it without T17 would be a guess. Until then `available = False` and the
client never reports the goal.

## 7. Learning mode (E19)

On by default. When `ItemPercentage` rises (every pickup +1), the client collects all bytes in the current world's
block that went from 0 to non-zero within **8 s before to 2 s after** the rise and writes a JSON line to the log file
2 s after the rise. The window reaches back because for SpecialFunction locations the memory relay can be set at the
start of the sequence. The rise only counts if the inventory was filled before and after (`PowerBeam.capacity > 0`), so
filling the inventory after loading is not a pickup. The learning mode runs regardless of the seed check (it only
writes the local log file).

Example (one line, wrapped here):

```json
{"kind": "pickup", "time": "2026-11-24T19:25:43.512", "world": "Norion", "world_id": "0x6FB8EF2A9523C343",
 "room": "Docking Hub Alpha", "item_percentage": [1, 2], "blocks": ["0x80A13AA0"],
 "bytes": [{"byte": 8, "value": 1, "time": "2026-11-24T19:25:43.010", "role": "location", "location": 4,
            "location_name": "Norion - Docking Hub Alpha - Pickup (Grapple Lasso)", "room": "Docking Hub Alpha",
            "status": "certain"},
           {"byte": 118, "value": 1, "time": "…", "role": "unknown", "location": null, "location_name": null,
            "room": null, "status": null}],
 "warnings": ["byte 118 set, but not assigned to any location"]}
```

(`status` is copied from `location_flags.py`: `certain`, `probable` or `uncertain`.)

| `kind` | Meaning |
|---|---|
| `pickup` | ItemPercentage rose; `bytes` = newly set bytes with role `location` (location per table), `extra` (`other_bytes` of a location) or `unknown` |
| `location_byte_without_pickup` | location byte set without ItemPercentage rising within the window |
| `blocks_disagree` | several valid blocks of the world with different content (byte list, addresses) |

Warnings (also in the client log): "byte X set, but not assigned to any location" and "pickup collected (ItemPercentage
rose) without the expected location byte". The **room** is only known for bytes that belong to a location; the player's
current room is not read (address unknown, AP_MEMORY_MAP.md 7).

For T13/playtests: every `pickup` line without warnings confirms a table location. With `unknown` bytes next to a
`location` byte the location is still confirmed (the block also holds story relays, e.g. Norion 118).

### Assumption about several blocks (T14 checks live)

Re-evaluation of the 22 T10 snapshots (MEM1) with the client code: every snapshot holds blocks of **all 14 worlds with
locations**, even of worlds never visited, told apart by the MLVL ID. "Pirate Homeworld - Command" has two blocks with a
valid header after reloading; one (`0x80A11900`) has bytes 670–1019 set although the world has only 209 memory relays:
garbage, rejected by the plausibility check (`/blocks` shows it as rejected). Snapshot C1 had a second valid copy per
world (`0x811E….`) whose set bytes were a subset of the main block; in C2 it was gone.

**Assumption:** several valid, plausible blocks of the same world are merged with **OR**. Reason: flags are only set
within a save, the copies seen were subsets. Risk: a left-over, still valid block of **another** save could report
locations that are not collected in the loaded save. Differences are logged by the learning mode as `blocks_disagree`.

## 8. Live tests

### T06 (2026-11-24): connection and location checks

PrimeHack, AP-patched PAL ISO, local `MultiServer.py` with an MP3 solo seed, client via the launcher (`--nogui`).

| Step | Result |
|---|---|
| connect with an existing save | location 4 (Norion, byte 8) detected from the save and sent |
| Dolphin closed and restarted twice | "lost connection" → "not found" → "no game" → connected again, no crash, nothing twice |
| new save, pickup 1: Valhalla, Docking Bay 5 | location 11 at the server; learning mode: ItemPercentage 0→1, only byte 1 = location 11 |
| new save, the same pickup again | learning mode byte 1 = location 11, **no** second report to the server |
| world change Valhalla → Bryyo Fire | pausing (loading) → ingame Bryyo Fire, new block |
| pickup 2: Bryyo Fire, Main Lift | location 17 at the server; learning mode: only byte 6 = location 17 |
| save reloaded (without saving), Main Lift again | blocks found again, location 17 still only once at the server |

Findings: Bryyo Fire byte 2 (no location, probably a story/room relay); after reloading Valhalla had two valid blocks
that differ in byte 35 (not a location byte) → T14.

### T07 (2026-11-25): item giving, death/reload, seed check

Setup: PrimeHack v1.0.9, **CPU Clock Override off** (`OverclockEnable = False`), fast disc speed on. Fresh solo seed
`07871388987290967892` (slot 1), ISO built with the patch tool from its `.apmp3` (seed ID
`1fe3386f84236acbf34d8da1d90ed28e`, read back), local `MultiServer.py`, client with GUI through the launcher. Items were
given with `/send`/`/send_multiple` in the server console. New game; the original save was backed up before (outside
the repo). Memory was additionally read with a separate read-only script.

| Time | Step | Result |
|---|---|---|
| 02:39 | ingame Valhalla, Docking Bay 5 | `Seed check OK`, no write (starting inventory complete). Server had sent the 7 starting items as starting inventory (location −2); not counted twice |
| 02:40 | saved at the ship (save S0, no items) | – |
| 02:41:13 | `/send_multiple 2 Samus Missile Expansion` | slot 68 0/0 → 10/10, slot 4 stays 0/0 (lock) |
| 02:41:25 | `/send` Missile Launcher, Energy Tank, Grapple Lasso, Progressive Beam, Energy Cell 1, Hypermode, Hazard Shield | one write: Plasma Beam 1/1, Missiles 0/0 → 15/15, Grapple Lasso 1/1, Suit 0/6 → 5/6, Energy Tanks 1/1, cells total 1/9, Energy Cell 1 1/1, Hypermode 1/1, slot 36 1/1, slot 68 10/10 → 0/0. User: everything visible in HUD/pause menu (15 missiles, tank, Grapple Lasso, Plasma Beam, 1 cell, category "Hypermode", suit changed) |
| 02:42 | saved at the ship (S1), reset, continue | inventory comes from the save, no write needed, user: everything there, no freeze |
| 02:43:53 | 3rd Missile Expansion after the save | Missiles 14/15 → 19/20 (one missile fired stays fired) |
| 02:44–02:45 | Energy Cell 1 inserted at the Docking Bay 5 terminal | not given again (no write) |
| 02:45:38–46 | death (game over) + continue | Missiles 15/15 (save) → 20/20: the expansion received after the save is given again; everything else from the save, cell 1 back (not inserted in S1). User: correct. Nothing written during the death |
| 02:47–02:51 | emulation stopped, S0 (no items) copied back into the NAND, continue | one write restores everything: Missiles 0/0 → 20/20, Plasma, Grapple Lasso, Suit 5/6, Energy Tank, cell 1, Hypermode + slot 36 |
| 02:53:47 | location 11 (Docking Bay 5, own X-Ray Visor) collected | `LocationChecks` → server "Samus found their X-Ray Visor" → `Received: … from yourself` → X-Ray Visor 0/0 → 1/1 |
| 02:54:59 | ISO of another seed (`t05b_duo.iso`, seed ID `7f5dd955…`) started, save continued | `WRONG ISO …`; location 11 collected there again (learning mode saw byte 1): **no check sent, nothing written** (X-Ray Visor stays 0/0 although it is in the target) |
| 03:05 | client restarted (English messages), same ISO | `WRONG ISO …` again, no write |

The user had saved once more in step 02:52 (with the items); that is why the ISO of the other seed showed items from
the save. The client wrote nothing there.

## 9. Tests

```powershell
$env:AP_TEST_WORLDS = "metroidprime3"
.venv\Scripts\python.exe -m pytest worlds/metroidprime3/test/test_client.py worlds/metroidprime3/test/test_client_items.py -q
```

Fake memory: `test/fake_memory.py` (MEM1 as a `bytearray`, counts accesses, creates state pointers, blocks, the starting
inventory of the AP ISO and the PAL build string with a seed ID; simple game rules: insert a cell, load a save with a new
CGameState pointer, reset a slot right after a write).

`test_client.py` (T06): signature search (also across chunk borders, after moving, throttled rescan,
header/SAVW/plausibility checks, OR of several blocks), wrong game ID (no further reads, no writes), menu/loading (only
state pointers read, no scan), newly set byte → exactly one `LocationChecks` with AP ID `1297101572` (location 4), world
change and reload without duplicate checks, server briefly offline / never connected / already checked, lost
connection, learning mode.

`test_client_items.py` (T07):

- effect table against `data/items.py` (all 99 pool items and the starting items, stages, quantities, locks, hyper
  menu), against `header.json` (slot per resource, `max_capacity`) and against the CSV in `AP_SLOT_LIMITS.md` (name,
  limit, bits); the last two only in a repo checkout;
- every pool item on its own, the whole pool, 15 random orders with every prefix: all values within the limit and
  < 2^bits, suit valid, no slot goes down (except slot 68 with the launcher), same end state;
- starting items not counted twice, expansions before the launcher, ammo keeps consumption, suit rule, inserted cell not
  given again, never lowered;
- whole client with real CommonClient packets: messages, settling and gating (menu, intro), reconnect and duplicate
  `ReceivedItems` (sync), death/continue and an older save (nothing twice, nothing missing), inserted cell, whole pool
  in game, location still sent while giving, wrong seed/other slot/vanilla → nothing written or sent (then the correct
  ISO works), seed switch forgets confirmed checks, server offline gives nothing, read-back throttling (no write loop,
  given up after 5 failures, retried after loading), consumption is no failure, `/inventory`.

Optionally against a real memory dump (T10, 24 MiB MEM1):
`$env:MP3_MEM1_SNAPSHOT = "<path>\D2_mem1.bin"` – expects Norion `0x80A13AA0` (locations 3, 4), Valhalla `0x80A49CC0`
(location 11), 14 worlds, the rejected PHC block.

## 10. Known gaps

- **Goal** not detected (T17 open, section 6): the client never sends `CLIENT_GOAL`.
- **Death state** not readable; writes during the death animation are possible (harmless, the save overwrites them).
  The pause menu is not detected either; writes can happen while paused.
- **Items only with a server connection.** Offline the client gives nothing (locations are still noted, section 5).
- **Ship Grapple/Ship Missile** (44/45) effect in game not verified (ship not usable early, T11); locked Ship Missile
  Expansions have no place in the game (slot 69 is not saved), the client books them as soon as the Ship Missile is
  there.
- **Suit:** story suits (PED/Phazon, T15 open) and their indices are unknown. The client leaves amounts 5–7 alone and
  only raises lower values to 5; whether amount 6 or 7 freezes is not tested.
- **Hypermode:** slot 36 is set with every hyper item; the interplay with the story hypermode and corruption in Bryyo,
  slots 40–42 and Phaaze is not tested (T15). Slots 40–42 are never written.
- **Energy cells:** inserting is only tested for cell 1 at the Docking Bay 5 terminal (T15, T07).
- **Read-back** happens one poll later (0.5 s), not immediately after the write.
- **slot_data:** complete for the client, `__init__.py` unchanged. Note: `AP_APWORLD_DEV.md` section 5 says the starting
  items are not sent as received items; with `items_handling = 0b111` the server does send them (location −2). The
  client handles both cases.
- **Several blocks:** OR assumption (section 7), checked in T14. Seen live: two differing Valhalla blocks after reloading
  (T06). If a copy holds a location byte that is not set in the loaded save, the client sends a wrong check. Also open:
  1 h continuous run, Dolphin (not only PrimeHack).
- **Room** of the player unknown (only the location's room in the learning mode).
- **PAL `RM3P01` only.** NTSC-U/J are rejected with "Wrong game".
- **10 SpecialFunction locations** are only "probable" in the table (T12); the learning mode reports differences.
- Dolphin accesses run synchronously in the asyncio loop; a scan blocks for about 0.1 s.
- No tracker/DeathLink part.
