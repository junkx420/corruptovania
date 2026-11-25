# SPEC – Metroid Prime 3 Archipelago (draft)

As of 2026-11-25 · Status: **E1–E20 decided**

## 1. Goal

Metroid Prime 3: Corruption as a playable Archipelago game (multiworld): items of MP3 end up in other worlds, items of other worlds in MP3, progress is synchronised live via an AP server.

Non-goal (for now): further development of Corruptovania as a standalone Randovania fork, macOS builds, Discord bot/server parts of Randovania.

## 2. Starting point (superficial survey)

| Area | Place | Use for AP |
|---|---|---|
| Logic database (regions, rooms, requirements, tricks) | `randovania/games/prime3/logic_database/*.json` | source for regions/locations/rules |
| Pickup database, item pool | `randovania/games/prime3/pickup_database`, `generator/` | source for the item list |
| Export/patch data | `randovania/games/prime3/exporter/` (`patch_data_factory.py`, `game_exporter.py`, `toolchain.py`) | creates the patch JSON for the patcher |
| ISO patcher (C#/.NET 8) | `tools/prime3_patcher/MP3Randomizer` | writes items into the game; needs AP placeholder items |
| Dolphin memory connection | `randovania/game_connection/connector/corruption_remote_connector.py` (152 lines), `executor/dolphin_executor.py` | basis for the AP client (read location checks, give items) |
| Licence | GPLv3 (`LICENSE`) | derived parts must stay GPLv3 |

Findings T01 (details `docs/AP_DEV_SETUP.md`): the patcher must be built as **win-x86** (`lzokay.dll` is 32-bit). No code checks game ID/hash. MP3Update/Deflicker hdiffs only work on NTSC-U. The exporter still uses the checked-in EXE.

Notes: Python ≥ 3.12. There is no Archipelago code at all in the repo. Last commit 2026-08-16. Upstream remote `origin` = Schwork-Corruption/corruptovania (no fork of our own set up).

## 3. Architecture (fixed by E1)

```
Archipelago (generator)                         Player PC
┌────────────────────────────┐                 ┌───────────────────────────────┐
│ apworld "metroidprime3"    │  .apmp3 patch   │ Patch tool                    │
│ - items.py / locations.py  │ ──────────────▶ │  patch JSON → MP3Randomizer   │
│ - regions/rules (generated │                 │  → patched ISO                │
│   from Corruptovania DB)   │                 │                               │
│ - options.py               │                 │ AP client (MP3Client)         │
└────────────────────────────┘                 │  Dolphin memory ⇄ AP server   │
              ▲                                │  (send checks, give items)    │
              │ converter script (once/CI)     └───────────────────────────────┘
   Corruptovania logic_database/*.json
```

Building blocks:
1. **DB converter**: reads Corruptovania JSON, creates AP regions, locations, rules (requirement trees → AP rule lambdas). Trick level as an AP option.
2. **APWorld**: items, locations, options, goal (Dark Samus/Phaaze), filler items, `fill_slot_data`.
3. **Patch path**: AP result → Corruptovania patch JSON → `MP3Randomizer`. Items of other worlds as a neutral "AP item" (model + text) in the game.
4. **Client**: read the world's flag block (location checks, E8), write items into the inventory via target/current reconciliation (E9, E11), check the seed ID (T18), optionally DeathLink.

## 3a. Working rules for workers

- Work happens on branch `archipelago`, remote `origin` = `junkx420/corruptovania`. `upstream` = original repo; never push there.
- Every worker commits only the files released to them and pushes at the end. Several workers share one working tree: commit only your own files, then `git pull --rebase --autostash origin archipelago`, then push. Never stash, reset or check out other workers' changes. Resolve conflicts in STATUS.md without changing other workers' rows.
- Never into the repo: ISOs, game files, Dolphin, personal paths, builds (`build/`, `venv/`).
- Project language is English: code, comments, log messages, tests, docs, SPEC/STATUS (E21). Workers talk to the user in German.
- The APWorld must not depend on Randovania at runtime. The converter creates self-contained Python data.

## 4. Features in order

| # | Feature | Depends on |
|---|---|---|
| F1 | Own fork + working dev environment (Corruptovania generates + exports a seed locally) | – |
| F2 | Document the memory mapping: inventory addresses, pickup/location flags, game state (ingame/menu) | F1 |
| F3 | DB converter Corruptovania → AP data structures | F1 |
| F4 | APWorld skeleton: items, locations, rules, goal; generates a solo seed without errors | F3 |
| F5 | Patch path: AP placement → patched ISO, items of other worlds as AP placeholders | F4 |
| F6 | AP client: send location checks | F2 |
| F7 | AP client: give received items into the game, resumption after restart | F6 |
| F8 | End-to-end test: 2-player multiworld (MP3 + any game) played through to the goal | F5, F7 |
| F9 | Extending options: starting location, starting items, trick level, Energy Cell goal (not in the MVP, see E3) | F8 |
| F10 | DeathLink, in-game messages via DOL hook (received items, warnings), own simple AP model + per-location texts (user wish, like 2s2h), release package + release repo of its own (E20) | F8 |

## 5. Open decisions

| ID | Question | Proposal | Status |
|---|---|---|---|
| E1 | Architecture | **Standalone APWorld**, logic converted from the Corruptovania DB, Corruptovania only as patcher | decided 2026-11-23 |
| E2 | Target platform/game version | **Dolphin only**, only the version the patcher supports today. T01: implicitly NTSC-U RM3E01. PAL RM3P01 works without MP3Update/Deflicker. Trilogy does not work. **PrimeHack** (Dolphin fork with mouse control) counts as a supported emulator, used for testing from T10 on | decided 2026-11-23 |
| E3 | MVP scope | **Item shuffle only, default starting location, fixed goal Dark Samus.** Starting location, trick level, DeathLink only in F9/F10 | decided 2026-11-23 |
| E4 | Repo hosting | **Fork `junkx420/corruptovania`, working branch `archipelago`** (default branch). `main` stays a mirror of upstream. The APWorld lives in the same repo under `apworld/metroidprime3/`, the converter under `apworld/tools/` | decided 2026-11-23 |
| E5 | Licence of the APWorld | **GPLv3** (logic data derived from Corruptovania) | decided 2026-11-24 |
| E7 | MVP region: PAL RM3P01 (available ISO, without MP3Update) or NTSC-U RM3E01 (patcher target version, ISO missing)? | **PAL RM3P01 for the MVP.** Add NTSC-U as soon as a dump is available (addresses of other regions from code, not checked live) | decided 2026-11-23 |
| E6 | Client basis | **AP `CommonClient` + `dolphin-memory-engine`**, addresses from docs/AP_MEMORY_MAP.md; the client lives in the APWorld (`apworld/metroidprime3/client/`) | decided 2026-11-24 |
| E8 | Location checks | Flag block of the world (1024 bytes in the heap): signature search after loading/world change, remember the address, check the signature on every query. No DOL hook in the MVP | accepted 2026-11-23 (F-01) |
| E9 | Item giving | Direct writing of amount/capacity to `PS + 0x54 + slot*0xC`, only when the player is ingame (CPlayer vtable) and `PowerBeam.capacity > 0` | accepted 2026-11-23 (F-01) |
| E10 | Remote items | All 99 locations give nothing locally (`item_type FF FF FF FF`, 0/0). Own items come from the server too, `items_handling = 0b111` | accepted 2026-11-23 (F-01) |
| E11 | Received items | No stored index. Target value per slot = starting items from `slot_data` + effect of all received items, **set absolutely, only raised, limited to `max_capacity` of the DOL table** (the save stores only as many bits per slot as the maximum needs; anything above is cut off). Exceptions (T19): Suit fixed to the valid value from `docs/AP_SLOT_LIMITS.md` (Suit amount 13 freezes the game); Energy Cells: amount = received − inserted (slots 52–61), never give inserted cells again. Death/Continue resets the inventory to the save; the reconciliation gives again afterwards | accepted 2026-11-25 (T19/T15) |
| E12 | Byte↔location table | Generated statically from SAVW + MREA, applies to all seeds, self-contained Python data, checked live by spot check (T12, T13) | accepted 2026-11-23 (F-01) |
| E13 | Number of locations | 99 locations (pickup index 1–99), location 0 is dropped | accepted 2026-11-23 (F-01) |
| E14 | Pickup display | Pickups of other worlds: existing neutral model, one shared text "Archipelago-Item". Own pickups show the real item. Texts per location after the MVP | accepted 2026-11-23 (F-01) |
| E15 | Missile-required | Off in the AP patch, the client reproduces the launcher lock | accepted 2026-11-23 (F-01) |
| E16 | DOL hook | Only if T11 finds an item that does not work via direct writing | accepted; T11: condition not met, no hook in the MVP |
| E17 | Location 0 / pool size | Location 0 (never patched) is according to the DB only reachable after "Aurora Unit 313"; its vanilla item Hypermode is useless for the logic. **Hypermode goes into the AP pool, one Missile Expansion goes out instead; the pool stays 99.** Location 0 is not a location in AP | revised 2026-11-24 (F-02) |
| E18 | "before event X" | Counts as satisfied in the logic. Dangerous is every event that occurs negated somewhere (derived from the data). The converter computes an `escape_requirement` per dangerous event (way back from the event node to the ship in the state "after X", cycle-free: events that require X are replaced by their own requirement) and **attaches it to every connection into the event node** (entering triggers the event). The APWorld needs no special logic for it. The player fixes triggering too early by reloading. No patcher change in the MVP | accepted 2026-11-24 (F-02 + re-check) |
| E19 | Check of the flag table | 89 locations certain, 10 SpecialFunction locations "probable" (T12). Instead of visiting all 10 live: the client has a learning/log mode (when ItemPercentage rises, it logs newly set flag bytes) and reports differences from the table; checking happens in playtests. T13 checks only easily reachable locations | decided 2026-11-24 |
| E20 | Release repo | Until the playtest everything stays in the fork. For the beta release (F10) a repo of its own `junkx420/Prime3AP` (description "Metroid Prime 3: Corruption for Archipelago") with only APWorld, client, patch tool, guide, GPLv3; `.apworld` and EXE as GitHub release assets. The fork stays the source for logic and patcher | decided 2026-11-25 |
| E21 | Project language | **English** for all project content (code, comments, logs, tests, docs, SPEC/STATUS); conversation with the user stays German | decided 2026-11-25 (user) |
| E22 | Dead-end locations (T08 B5: Leviathan cores) | The converter computes for **every pickup node** an `escape_requirement` (path back to the ship/teleporter network, same machinery as E18) and ANDs it onto that location's access rule when it is not trivially satisfied. Logic then never expects a location the player cannot leave. Side effect: the exit item cannot be placed at its own dead end (accepted). Additionally the client warns when the player enters a Leviathan seed without the exit item (T26) | decided 2026-11-25 |
| E23 | Options for the beta (pulled forward from F9, user wish) | (1) **Starting items:** YAML option chooses which of the default starting items the player keeps; Power Beam, Combat Visor and Scan Visor always stay (client needs PowerBeam > 0, scanning is mandatory); removable: Charge Beam, Space Jump Boots, Morph Ball, Morph Ball Bombs. Removed items go into the pool, Missile Expansions leave it (pool stays 99). AP `start_inventory` works on top. (2) **Tricks:** YAML option for a global trick level (off … advanced, Corruptovania levels 0–5) plus optional per-trick overrides; only tricks the converter rates as usable (enough uses in the DB, no unknown requirement types) are offered, marked experimental. (3) **Data independent of the setup:** the converter must not bake starting items or trick levels into `escape_requirement`/E18 gates/E22 rules; starting items appear as normal item requirements, trick leaves stay in the trees and are evaluated by the APWorld per slot. Escape requirements are computed **without tricks** (stricter, always safe). Start location stays fixed (MVP) | decided 2026-11-25 (user wish) |
