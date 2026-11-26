# APWorld "Metroid Prime 3: Corruption" – development (T04, patch file/packing/launcher T05b)

As of 2026-11-25 · Archipelago **0.6.8** · Python 3.12 · MVP according to SPEC E3 (item shuffle only, default starting location, fixed goal)

The APWorld is in `apworld/metroidprime3/`. It only reads the generated data in `apworld/metroidprime3/data/`
(T03/T20, see `data/README.md`) and imports nothing from `randovania` (SPEC 3a, test `TestNoRandovania`).

## 1. Development environment

Archipelago is cloned **outside** the repo, e.g. next to `corruptovania`. The clone never goes into the repo.

```powershell
cd ..
git clone --depth 1 --branch 0.6.8 https://github.com/ArchipelagoMW/Archipelago.git Archipelago
cd Archipelago
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe ModuleUpdate.py --yes
.venv\Scripts\python.exe -m pip install pytest
```

`ModuleUpdate.py --yes` installs `requirements.txt` and the requirements of all bundled worlds (otherwise
`Generate.py` asks for them at startup). The first start compiles `_speedups` (needs MSVC Build Tools, were available).

### Linking in the APWorld

As a **directory junction** (Windows, no admin rights needed). Changes in the repo take effect at once, Archipelago sees the
folder as `worlds/metroidprime3`:

```powershell
cmd /c mklink /J "<Archipelago>\worlds\metroidprime3" "<corruptovania>\apworld\metroidprime3"
```

Linux/macOS: `ln -s <corruptovania>/apworld/metroidprime3 <Archipelago>/worlds/metroidprime3`.

Without a junction/symlink a copy works too (repeat after every change; the playthrough test and
`test_matches_playthrough_sim_logic` are then skipped because `apworld/tools/` is missing):

```powershell
robocopy "<corruptovania>\apworld\metroidprime3" "<Archipelago>\worlds\metroidprime3" /MIR /XD __pycache__
```

Removing the junction: `cmd /c rmdir "<Archipelago>\worlds\metroidprime3"` (deletes only the link, not the repo).

## 2. Generating seeds

Example YAML (e.g. `<Archipelago>\Players\mp3.yaml`). The game name contains a colon and **must be in
quotes**:

```yaml
name: Samus
game: "Metroid Prime 3: Corruption"
description: Example YAML for the MP3 APWorld (MVP, default options only)
"Metroid Prime 3: Corruption":
  progression_balancing: 50
  accessibility: full
```

```powershell
.venv\Scripts\python.exe Generate.py --player_files_path Players --outputpath output
```

Note: on an error `Generate.py` waits for Enter at the end. In scripts redirect stdin (`< NUL` or `< /dev/null`).

2-player seed: a second YAML in the same folder, e.g. ChecksFinder (Clique is no longer a core game since 0.6.x):

```yaml
name: Finder
game: ChecksFinder
ChecksFinder:
  progression_balancing: 50
  accessibility: full
```

Result T04: 10 solo seeds in a row without errors (~0.4 s generation each, ~4 s with startup), 2-player seed
MP3 + ChecksFinder without errors (124 items).

T29 addresses the rare fill failures seen in T25 with the E22 location rules. With default options,
`local_early_items` asks Archipelago to place Screw Attack among the MP3 player's three starting checks.
Collecting it opens Norion Docking Hub Alpha (3) and Pirate Homeworld Scrapvault (82). Early Grapple Lasso opens
three checks and caused playthrough seed 6 to stall in testing. The default `test_generation.py` run covers
seeds 1–300 in process. Set `MP3_EXTENDED_FILL_TESTS=1` to cover seeds 1–1200.

T31 (E23) adds the options `starting_items`, `trick_level` and `trick_overrides` (player guide `AP_OPTIONS.md`). The
T29 rule is unchanged (only with fully default options). With any starting item removed, `pre_fill` places the
opening chain (`opening.py`) instead: own progression items forward onto own open checks until 8 are open, because two
`local_early_items` (sphere 1 has only checks 4 and 11) still left 0.3–5 % FillErrors. `test_generation.py` runs every
starting item choice for 3 seeds (60 with `MP3_EXTENDED_FILL_TESTS=1`); the full measurement is in `AP_OPTIONS.md`
section 4.

Since T05b the output ZIP contains a **patch file** `<output name>.apmp3` per MP3 slot (e.g.
`AP_38224278823687041413_P2_Samus.apmp3`) next to `.archipelago` and the spoiler. Format: `AP_PATCH_TOOL.md` section 2.3.
The player builds their ISO from it (section 6).

## 3. Tests

From the Archipelago folder (`AP_TEST_WORLDS` limits Archipelago's tests to this world):

```powershell
$env:AP_TEST_WORLDS = "metroidprime3"
.venv\Scripts\python.exe -m pytest test/general -m "world or not world" -q
.venv\Scripts\python.exe -m pytest worlds/metroidprime3/test -q
```

As of T05b: `test/general` 253 passed (3 more than T04: Archipelago's manifest test runs because there is now an
`archipelago.json`); own tests 100 passed, 2 skipped (need `MP3_PAL_EXTRACTED` or
`MP3_MEM1_SNAPSHOT`), ~9 s.

The own tests (`apworld/metroidprime3/test/`) only run in the Archipelago clone (they import `test.bases`,
`BaseClasses`, `Fill`), not with the pytest of the Corruptovania repo.

| File | Checks |
|---|---|
| `test_ids.py` | 99 locations with ID = base + pickup index, location 0 missing; item IDs against a fixed snapshot; every data item has an ID; pool = 99 items according to `data/items.py` incl. Hypermode (48 Missile Expansions); starting items precollected; `slot_data` JSON-serialisable; no `randovania` imports |
| `test_logic.py` | rule semantics (and/or, "before event" = satisfied, trick leaf = slot level ≥ leaf level, default all off (T30), Progressive Beam, launcher lock, Energy Cells, damage); with all items all 99 locations and the goal are reachable; the only missing event is "Gel Processing Site Out of Bounds" (only via trick, T20); **node lock**: in 70 inventories (all minus one item each, 40 random) the `escape_requirement` of every reachable dangerous event node holds there; control value Green Lock ↔ Grapple Lasso; comparison of reachable nodes/events/locations with `playthrough_sim.World.reach(logic=True)` for 70 inventories; **dead-end locations (E22)**: location rules = data (22 non-trivial), the three Leviathan cores are reachable without their exit item but the location is not, the exit item cannot be placed in its own core |
| `test_output.py` | `.apmp3` (T05b): solo seed, MP3 + ChecksFinder and MP3 + ChecksFinder + MP3 → exactly one `.apmp3` per MP3 slot; 99 locations (1–99), own items = real name, foreign ones (also from the other MP3 slot) = `Archipelago Item`, seed ID = `patcher.seed_id.make_seed_id`; read with the patch tool and with `MP3Container`. Patch tool: `.apmp3` = same data as JSON, 7 error cases, `--dry-run` with `.apmp3`. Launcher helpers (arguments, client arguments from the manifest, output path, tools folder), component recognises `.apmp3`; settings (game ID check); `archipelago.json`, `requirements.txt`, file selection as in "Build APWorlds" |
| `test_options.py` | T31 (E23): every starting item choice (pool 99, Missile Expansions out, precollected items, `slot_data`, patch string), fixed items cannot be removed, trick resolution and override schema, regions follow the slot's tricks, opening chain (none with defaults, forward and locked, respects `non_local_items`) |
| `test_playthrough.py` | 20 solo seeds with Archipelago's fill (`distribute_items_restrictive` + progression balancing); the real AP placement goes to `playthrough_sim.play` (eager 0 and 0.5); the logic-faithful player wins every seed with 99/99 locations and is never trapped (dead-end rule, T25). Control: the same seeds without the location rules, played without the rule, strand the player (T25: 20/20, mostly in location 84, twice in the Pirate Homeworld core) |

Counter-check (once, not as a test): without the node lock in the connections the same player wins only 10 of the
20 AP seeds. So the playthrough test detects a missing lock.

The simulator needed no new interface: `play(world, placement, rng, eager)` takes `{pickup index: item record}`.
The adapter function `ap_placement` in the test builds that from the AP placement; foreign items (multiworld) become a
record without effect. Small gap: `World.give` in the simulator does not know the launcher lock (expansions give
ammo without a launcher). Irrelevant for the logic, because expansions are not progression.

## 4. Structure of the world

| File | Content |
|---|---|
| `__init__.py` | `MP3World`: game name `Metroid Prime 3: Corruption`, items, locations, goal, `fill_slot_data` |
| `items.py` | base ID, fixed item offsets, `MP3Item`, classification (`progression` from the data, otherwise `filler`) |
| `locations.py` | 99 locations from `data/locations.py`, groups per game region (`Norion`, `Bryyo - Fire`, …) |
| `rules.py` | compiler requirement tree → AP rule; `StaticState` for the precomputation |
| `regions.py` | one AP region per logic node, entrances, event locations, precomputation "reachable with all items" |
| `options.py` | `MP3Options`: Archipelago's default options plus `starting_items`, `trick_level`, `trick_overrides` (E23, T31; player guide `docs/AP_OPTIONS.md`) |
| `opening.py` | opening chain for small starting inventories (T31): forward placement of own progression items in `pre_fill` until 8 own checks are open |
| `output.py` | `.apmp3`: `MP3Container` (`APPatch`), `displayed_pickups`, `write_patch_file` (T05b) |
| `settings.py` | `MP3Settings` = section `metroidprime3_options` of `host.yaml` (original ISO, tools folder, output folder, regional MP3Update/Deflicker setting) |
| `open_patch.py` | launcher: `.apmp3` → build ISO → start client (T05b, section 6) |
| `archipelago.json`, `requirements.txt` | manifest and dependency for the packed `.apworld` (section 7) |

**IDs.** `BASE_ID = 0x4D503300` (= "MP3\0" in ASCII, 1297101568).
- Location ID = `BASE_ID + pickup index` (1–99). Location 0 (`UNPATCHED_LOCATION`) is neither a location nor an event (E13, E17).
- Item ID = `BASE_ID + ITEM_OFFSETS[name]`: pool items 1–30, starting items 101–107. The offsets are fixed in `items.py`;
  new items get the next free number, existing ones are never renumbered (snapshot in `test_ids.py`).

**Regions.** `Menu` → starting node `G.F.S. Valhalla - Docking Bay 5 - Samus Ship` (fixed, E3). Every node from
`logic.REGIONS` becomes a region `"<region> - <area> - <node>"`. Every connection from `logic.CONNECTIONS` becomes an
entrance (several connections between the same nodes are combined with OR; connections whose rule is constantly
false are dropped). The node lock (E18) is already part of the connections' `requirement` and is not
handled separately. The 99 locations are in their pickup node; their access rule is the `escape_requirement`
from `data/locations.py` (E22, T25: the way back from a dead end, e.g. Hyper Ball for the Bryyo Leviathan Core;
`{"and": []}` for 77 of 99 locations, i.e. no rule). The world compiles it like every requirement, no special logic.

**Events.** Every source of an event in `logic.EVENTS` becomes an event location `Event: <name>` (with several sources
`Event: <name> [k]`) in the source node, rule = requirement of the source, with a locked event item `<name>` (progression,
without ID). Goal: `state.has("Aurora Unit 313")`.

**Precomputation.** Nodes and event sources that are unreachable even with all items (without tricks) are not
created (Archipelago's test requires every region to be reachable with all items). That is 8 of 943 nodes and
1 of 230 sources ("Gel Processing Site Out of Bounds"). The logic is monotonic, so this changes nothing. The result
matches `playthrough_sim` (test).

**Rules** (`rules.py`, semantics as in `data/README.md`):
- `and`/`or` (empty: always/never), templates compiled once and shared, constant subtrees folded.
- `item`: resource amount from the stages of the items held (the n-th copy gives stage n, the last one repeats),
  starting items count too (precollected). If a resource has exactly one supplier, this becomes `state.has(item, n)`.
  Launcher lock as possession logic: ammo of an item with `lock.opened_by` = another item only counts with that item.
  Expansions are `filler` and are not collected into the state by Archipelago at all.
- `event` → `state.has(event)`. `event` with `negate` ("before event X") = **satisfied** (E18).
- `trick`: satisfied when the slot's level for that trick is at least the leaf's level (`RuleCompiler(player, tricks)`,
  T30). The levels come from the YAML options `trick_level`/`trick_overrides` (T31, `options.resolve_tricks`); with
  the default (off) every trick leaf is unsatisfied, as in the MVP. `item` with `negate` and `node` = never satisfied.
- `damage`: `99 + 100 × Energy Tanks > ceil(reduction × int(amount × 1.5))` → minimum number of Energy Tanks.
- `misc`/`version`: static from `game.SETTINGS`.

## 5. `slot_data` (format, `slot_data_version` 1)

Everything the client needs for the target state (E11: target = starting items + effect of all received items).

```json
{
  "slot_data_version": 1,
  "seed_name": "14089154938208861744",
  "base_id": 1297101568,
  "goal_event": "Aurora Unit 313",
  "start_location": ["G.F.S. Valhalla", "Docking Bay 5", "Samus Ship"],
  "starting_items": ["Charge Beam", "Power Beam", "Combat Visor", "Scan Visor", "Space Jump Boots",
                     "Morph Ball", "Morph Ball Bombs"],
  "starting_resources": {"Charge Beam": 1, "Power Beam": 1, "Combat Visor": 1, "Scan Visor": 1,
                         "Space Jump Boots": 1, "Morph Ball": 1, "Morph Ball Bomb": 1},
  "tricks": {},
  "items": {
    "Progressive Beam": {"id": 1297101569, "stages": [[["Plasma Beam", 1]], [["Nova Beam", 1]]], "lock": null},
    "Missile Expansion": {"id": 1297101588, "stages": [[["Missile", 5]]],
                          "lock": {"locked_by": "Missile Launcher", "item": "Missile",
                                   "temporary": "Temporary Missile", "respects_lock": true,
                                   "opened_by": "Missile Launcher"}},
    "...": {}
  },
  "locations": {"1297101569": 1, "1297101570": 2}
}
```

| Key | Meaning |
|---|---|
| `slot_data_version` | format version; increase on incompatible changes |
| `seed_name` | Archipelago's seed name (for the seed check, T18) |
| `base_id` | base of the IDs (location ID − `base_id` = pickup index) |
| `goal_event`, `start_location` | goal event and starting node (info, fixed in the MVP) |
| `starting_items` | names of the slot's starting items (T31: the YAML choice, E23; before T31 always all seven). The client takes its target from them; older slot_data without the key = all seven |
| `starting_resources` | resource amounts of the slot's starting items (names as in the requirements, e.g. `Morph Ball Bomb`) |
| `tricks` | T31, information only: the slot's trick levels `{trick name: 1–3}` the logic expects (`{}` = no tricks) |
| `items` | all MP3 items (pool and start): `id`, `stages` (list of stages, per stage `[resource, amount]`; the n-th received copy gives stage n, the last one applies to all further copies), `lock` (launcher lock as in `data/items.py`, otherwise `null`; the client reproduces the lock, E15) |
| `locations` | location ID (as a string) → pickup index 1–99 |

Resources → inventory slot (game memory) is the client's business (T07, `docs/AP_MEMORY_MAP.md`).

## 6. Opening the patch file: launcher (T05b, T23)

The launcher component **"Metroid Prime 3 Client"** (T06) now recognises `.apmp3` (`file_identifier`). Without an
`.apmp3` it only starts the client, as before.

Ways to open an `.apmp3`:

- double click on the `.apmp3` if the extension is associated with the Archipelago launcher (with an installed
  Archipelago via "Open with" → `ArchipelagoLauncher.exe`),
- in the launcher **"Open Patch"** and choose the file, or drag the file onto the launcher window,
- command line with the GUI disabled: `.venv\Scripts\python.exe Launcher.py <file.apmp3> -- --nogui`.

Sequence (`open_patch.patch_and_launch`; the launcher uses a separate process for GUI patch opens):

1. Read the `.apmp3` (`patcher.patch_data.read_container`). Patch errors go to the log and to an error dialog in GUI mode.
2. Original ISO from the `host.yaml`, `metroidprime3_options.iso_file`. If the file is missing, a file dialog opens
   ("Metroid Prime 3: Corruption ISO (Wii PAL RM3P01, unmodified)"); the chosen path is saved in the `host.yaml` at
   once. Only the first 6 bytes are checked (game IDs `RM3P01` and `RM3E01`; `RM3J01` with a warning from the patch tool),
   no hash: that would read 4.7 GB on every access to the setting. With `--nogui`, set `iso_file` in `host.yaml` before running.
3. Target ISO `<name of the .apmp3>.iso` next to the `.apmp3` (or in `output_folder`). It is reused when the seed
   ID, region and patch setting match. For PAL and NTSC-U, a companion `.iso.mp3update` file records the setting,
   ISO size and modification time. An ISO without this file is rebuilt on its next Open Patch for either region.
4. Patch tool (`patcher.build.patch_iso`, ~40 s). It first finds the helper programs (`patcher.tools.find_tools`,
   `AP_PATCH_TOOL.md` section 3.1): `tools_folder` (only if it contains `MP3Randomizer.exe`, otherwise ignored with a
   log warning), `$MP3AP_TOOLS_DIR`, the cache `<Archipelago>/metroidprime3_tools`, a Corruptovania checkout, a tools
   ZIP placed into the cache by hand, else it downloads `metroidprime3-tools-win.zip` from the Prime3AP release
   (SHA-256 fixed in the code). Download, check and extraction appear in the same window before step 1; errors
   (offline, wrong hash) name the manual steps. A `tkinter` window displays the tool's steps, including step 3 of 7
   when applying PAL Deflicker or both NTSC-U patches, and briefly shows
   `Done` after verification. Archipelago 0.6.8 starts **Open Patch** in a separate launcher process, so this window uses
   the same toolkit as Archipelago's file picker and can run independently of the launcher's Kivy window. The patcher
   runs on a worker thread so the window stays responsive. With `--nogui`, progress and errors go only to the console
   and `logs\MetroidPrime3Patch_<time>.txt`.
5. Start the Metroid Prime 3 Client, with `--connect <server>` (only if the `.apmp3` contains a server, i.e. comes from the
   WebHost) and `--name <player name>`; arguments passed explicitly take precedence.

`host.yaml` section (Archipelago creates it the first time the world is loaded):

```yaml
metroidprime3_options:
  iso_file: "C:/Games/mp3.iso"   # original ISO, asked for at the first .apmp3
  tools_folder: ""              # empty: download once into <Archipelago>/metroidprime3_tools; set only for offline installs
  output_folder: ""             # empty: ISO next to the .apmp3
  mp3update: true                # Deflicker on PAL, MP3Update and Deflicker on NTSC-U
```

The existing `mp3update` key controls the patches available for the region, so existing `host.yaml` files can use
the same switch for both disc versions. `false` skips the regional patches. PAL applies the validated Deflicker patch
directly to `main.dol` and uses the base helper files. NTSC-U applies the packaged diffs through HDiffPatch.

**Troubleshooting a YAML error during generation.** In `host.yaml`, always use `/` in double-quoted paths such as
`"C:/Games/mp3.iso"`. YAML treats backslashes in double quotes as escapes, which can cause generation to fail.

**Checked (T05b, command line):** `Launcher.py ..\out\AP_38224278823687041413_P2_Samus.apmp3 -- --nogui` with
`iso_file` set: ISO built (seed ID read back), then client started, connected to the running PrimeHack
("game RM3P01 detected"). Second call: "already has seed ID …, not patching again", client starts at once. Broken
`.apmp3` → error message, no client.

**T23 GUI check (development clone):** Rename any existing target ISO for the selected `.apmp3` to keep a backup.
Run `.venv\Scripts\python.exe Launcher.py`, select **Open Patch**, and choose the `.apmp3`. Check that the patch window
shows the numbered steps and `Done`, then that the Metroid Prime 3 Client opens.

**Checked (T28, fresh install):** clean Archipelago 0.6.8 copy with only the packed `.apworld` in `custom_worlds`,
`tools_folder: ""`, empty cache: `Launcher.py <x.apmp3> -- --nogui` downloaded the tools ZIP into
`<Archipelago>/metroidprime3_tools/tools-<first 12 hex digits of the ZIP hash>`, built the ISO in 36 s and started the client (details in
section "Release").

## 7. Packed `.apworld`

Files: `archipelago.json` (manifest: `game`, `minimum_ap_version` 0.6.8, `world_version` 0.1.0) and
`requirements.txt` (`dolphin-memory-engine>=1.3.0`, as in T06; 1.3.1 is installed in the venv).

Packing with Archipelago's launcher component "Build APWorlds" (only in the source Archipelago):

```powershell
.venv\Scripts\python.exe Launcher.py "Build APWorlds" -- "Metroid Prime 3: Corruption" --skip_open_folder
```

Result `build\apworlds\metroidprime3.apworld` (181 KB, 41 files, 3.2 MB unpacked). The component takes all
files of the folder except `__pycache__`, `*.iso` etc. (`data/GLOBAL.apignore`), adds the manifest including
`compatible_version`/`version` and follows the junction. `test/` is included (does no harm).

Installing: `.apworld` into `custom_worlds\` (or launcher "Install APWorld"). In the development clone rename the
junction first, otherwise the folder wins ("already loaded"): `cmd /c rename worlds\metroidprime3 _metroidprime3_dev`
(Archipelago does not load folders starting with `_`), back with `cmd /c rename worlds\_metroidprime3_dev metroidprime3`.

**Checked (T05b):** with the renamed junction and `custom_worlds\metroidprime3.apworld`, Archipelago 0.6.8 loads the world
from the ZIP (`zip_path` set, `v0.1.0` in the generator output); `Generate.py` with MP3 + ChecksFinder creates
a seed without errors, the output ZIP contains `AP_…_P2_Samus.apmp3`.

**Load time** (`python -X importtime`, 3 runs each, Python 3.12, all worlds loaded):

| Source | `data/logic.py` (2.9 MB) | `import worlds` total |
|---|---|---|
| folder (junction, `.pyc` present) | 0.12–0.13 s | 3.6–3.7 s |
| packed `.apworld` (no `.pyc`, compiled at every start) | 0.25 s (of which `compile` 0.12 s) | 3.7–3.8 s |

The concern from T04 (3–5 s) does not hold: compiling the pure data literals costs ~0.12 s per start, the
total time is determined by the other worlds. No action needed (no `.pyc` needed in the ZIP).

**Dependency:** Archipelago 0.6.8 does not install the `requirements.txt` of a packed `.apworld` itself
(`ModuleUpdate.py` only reads `requirements.txt` of world folders). `dolphin-memory-engine` is available anyway: in the
installed Archipelago through the bundled Wind Waker world, in the source Archipelago through `ModuleUpdate.py --yes`.
The patch tool's helper programs (31 MB) are deliberately not in the `.apworld`: the patch tool downloads the tools ZIP
of the release on the first patch and caches it (section 6, step 4; `AP_PATCH_TOOL.md` section 3.1). For release
builds use `apworld/tools/release/build_release.py` (section "Release"); it packs like "Build APWorlds" but from a Git
commit.

## 8. Open

- Tricks as an option (F9). The damage approximation (full energy per requirement) stays optimistic (T03).
- ~~Ship the patch helper programs with the release or download them~~: done in T28 (download on first use).
- ~~While patching the launcher shows nothing~~: progress window since T23 (also shows the T28 download).
- ~~GUI path only described~~: "Open Patch" checked manually by the user (T05b, T23).
- Patch tool and helper programs are Windows only; macOS/Linux would need other builds of the helpers.

## CI

The [APWorld Tests workflow](../.github/workflows/apworld-tests.yml) runs on every push to
`archipelago` and every pull request targeting it. Both jobs use Python 3.12 and a pip cache.
The Archipelago 0.6.8 job runs `worlds/metroidprime3/test` and `test/general`. Its symlink
lets tests find the simulator and reference files in the Corruptovania checkout. The tool
job discovers tests under `apworld/tools` and installs Randovania's base dependencies
because the converter uses the Randovania database loader.

To reproduce the APWorld job, set up the Archipelago clone and junction or symlink from
section 1. With its Python 3.12 environment active, run this from the Archipelago root.

```bash
python -m pip install -r requirements.txt -r ci-requirements.txt -r worlds/metroidprime3/requirements.txt
AP_TEST_WORLDS=metroidprime3 python -m pytest -q -rs -m "world or not world" worlds/metroidprime3/test test/general
```

In PowerShell, set `$env:AP_TEST_WORLDS = "metroidprime3"` before the pytest command.
For the tool job, use a separate Python 3.12 environment and run this from the Corruptovania root.

```bash
python -m pip install -c requirements.txt -e . pytest pytest-asyncio
python -m pytest -q -rs apworld/tools
```

Leave `MP3_PAL_EXTRACTED`, `MP3_PAL_DOL` and `MP3_MEM1_SNAPSHOT` unset
to reproduce CI's skips. Pytest reports the fixture-dependent skips with `-rs`.

## Release

Release repo: [junkx420/Prime3AP](https://github.com/junkx420/Prime3AP) (E20). Player guide there:
`README.md`, `docs/INSTALL.md`, example YAML `examples/Metroid Prime 3 Corruption.yaml`. The packed `.apworld` still
contains no helper programs; the patch tool downloads them on first use (T28, `AP_PATCH_TOOL.md` section 3.1,
section 6 step 4).

### Assets

| Asset | Content |
|---|---|
| `metroidprime3.apworld` | `apworld/metroidprime3` packed like "Build APWorlds" (same ignore rules as `data/GLOBAL.apignore` of AP 0.6.8, manifest = `archipelago.json` + `compatible_version` 7 + `version` 7) |
| `metroidprime3-tools-win.zip` | the patch helpers, MP3Update and Deflicker diffs from v0.4.0 onward, `README.txt`, `THIRD-PARTY-NOTICES.txt`, `licenses/` |
| `metroidprime3-example.yaml` | example YAML from the Prime3AP repo (asset names have no spaces: GitHub turns them into dots, which would break `SHA256SUMS.txt`) |
| `wiimms-iso-tools-r8638-src.tar.gz` | corresponding source of `wit.exe` (GPL-2.0): unmodified GitHub archive of [Wiimm/wiimms-iso-tools](https://github.com/Wiimm/wiimms-iso-tools) commit `fc1c0b8` "WIT v3.05a" (`project/revision.sh`: `revision=8638`) |
| `cygwin-3.1.7-1-src.tar.xz` | corresponding source of `cygwin1.dll` (LGPL-3.0+): unmodified Cygwin source package from the official archive `sourceware.org/pub/cygwin-archive/20221123/x86/` (current mirrors only keep recent versions; the source package is the same for x86 and x86_64; SHA-512 matches that folder's `sha512.sum`) |
| `SHA256SUMS.txt` | `sha256sum` format over all files above |

### Build

From the Corruptovania root (plain Python ≥ 3.10, no Archipelago needed):

```powershell
python apworld/tools/release/build_release.py --tag v0.3.0 --fetch-sources
```

- Reads every input as a raw Git blob of `--ref` (default `HEAD`), so uncommitted work of other workers in the shared
  working tree never gets into a release and `core.autocrlf` does not change the bytes. `--worktree` reads from disk
  (development only).
- Fails if `world_version` in `archipelago.json` is not the tag without `v`. `--allow-version-mismatch` only warns
  (draft assets built before the version bump; rebuild before publishing).
- Fails if the tools ZIP hash differs from `TOOLS_ZIP_SHA256` in `patcher/tools.py`. The ZIP is deterministic (sorted
  entries, fixed timestamp 2026-01-01, deflate level 9), so it only changes when an input changes (or with another zlib
  version). After changing a helper program or a licence file: commit, run `--tools-only` (prints the hash), set
  `TOOLS_ZIP_SHA256` (and `TOOLS_RELEASE_TAG` if the ZIP goes to a new release), commit, build again.
- Example YAML: `--example-yaml` (default `../Prime3AP/examples/Metroid Prime 3 Corruption.yaml`).
- Source archives: listed in `apworld/tools/release/source_archives.json` (official URL, pinned SHA-256). Taken from
  `--sources-dir` (default `build/release-sources/`); `--fetch-sources` downloads missing ones from the official URL.
  A wrong hash or a missing archive stops the build (`--no-sources` only for development). `THIRD-PARTY-NOTICES.txt`
  in the tools ZIP names both assets with their SHA-256 (a test checks this).
- Output: `build/release/` (ignored by Git). Tests: `python -m pytest -q apworld/tools/release` (also in CI's tool job).

Draft on GitHub (the tag is created when the draft is published):

```powershell
gh release create v0.3.0 --repo junkx420/Prime3AP --draft --prerelease --title "Prime3AP 0.3.0 (beta)" `
  --notes-file ..\Prime3AP\release-notes\v0.3.0.md build\release\metroidprime3.apworld `
  build\release\metroidprime3-tools-win.zip build\release\metroidprime3-example.yaml `
  build\release\wiimms-iso-tools-r8638-src.tar.gz build\release\cygwin-3.1.7-1-src.tar.xz build\release\SHA256SUMS.txt
```

The releases API sometimes answers HTTP 500 (seen on 2026-11-25, also for a one-line body); repeat the call. If
`gh release create` keeps failing, create the draft with a short body via `gh api`, then `gh release edit --notes-file`
and `gh release upload`.

Assets of a **draft** are not public: the download URL in `tools.py` only works after publishing. Before that, test with
`$MP3AP_TOOLS_URL` (local server) or by putting the ZIP into the cache folder.

### Release procedure (as done for v0.3.0, T32)

1. `git pull --rebase --autostash origin archipelago`; check that no work meant for a later release is committed.
   Set `world_version` in `apworld/metroidprime3/archipelago.json` to the tag without `v`, commit only that file, push,
   wait for green CI.
2. Build from exactly that commit: `python apworld/tools/release/build_release.py --tag vX.Y.Z --fetch-sources`
   (prints `Built from <sha>`). Replace the changed assets in the draft with
   `gh release upload vX.Y.Z --repo junkx420/Prime3AP --clobber <files>`, update the notes with
   `gh release edit vX.Y.Z --notes-file ..\Prime3AP\release-notes\vX.Y.Z.md`, then compare the asset digests
   (`gh release view vX.Y.Z --json assets`) with `SHA256SUMS.txt`.
3. Smoke test in the installed Archipelago: back up the old `.apworld` from `custom_worlds`, copy the new one in,
   generate MP3 + ChecksFinder from the release's example YAML (`ArchipelagoGenerate.exe --player_files_path <folder>
   --outputpath <folder>`, outside the repo), host with `ArchipelagoServer.exe`, Open Patch, PrimeHack (Clock Override
   off), connect. Check: seed check OK, location 11 (Docking Bay 5) reaches the server, `/send <slot> Grapple Lasso`
   in the server console arrives in the game.
4. Publish only after the user's OK: `gh release edit vX.Y.Z --repo junkx420/Prime3AP --draft=false --prerelease
   --target <Prime3AP main sha>` (creates the tag).
5. Public download check: copy of the installed Archipelago (without `custom_worlds`, `host.yaml`, `Players`, `logs`,
   cache) in `%TEMP%`, only the `.apworld` downloaded from the public release URL (checked against the public
   `SHA256SUMS.txt`), minimal `host.yaml` with `iso_file` and `tools_folder: ""`, `MP3AP_TOOLS_DIR`/`MP3AP_TOOLS_URL`
   unset, then `ArchipelagoLauncher.exe <x.apmp3> -- --nogui`.

**Checked (T32, v0.3.0):** world_version 0.3.0 in `3f65f8d`, assets built from it (only `.apworld` and
`SHA256SUMS.txt` changed; tools ZIP, example YAML and source archives byte-identical to the T28 draft), GitHub digests =
`SHA256SUMS.txt`. Smoke test in the installed Archipelago 0.6.8 with PrimeHack: ISO built in 37 s, seed check OK,
location 11 at the server, Grapple Lasso from the server console written to the game. Published as pre-release
(tag `v0.3.0` on Prime3AP `8450cdc`). Fresh copy: tools ZIP downloaded from the public URL into
`metroidprime3_tools/tools-cdd5a5b72789` (hash checked), ISO built in 38 s, SHA-256 identical to the smoke test ISO
of the same seed (`415175c9…`).

### Licences of the shipped programs

All licences allow redistribution. The ZIP carries every licence text and `THIRD-PARTY-NOTICES.txt` (versions, sources).

| File in the ZIP | Component, version | Licence | Obligations when redistributing |
|---|---|---|---|
| `MP3Randomizer.exe` | gollop's MP3Randomizer, modified in this fork (T16, `tools/prime3_patcher`) | MIT (gollop) + GPL-3.0 (fork) | keep the MIT notice; GPL: source is public in this repo |
| (inside `MP3Randomizer.exe`) | .NET 8 runtime 8.0.34 (`Microsoft.NETCore.App.Runtime.win-x86`, self-contained single file) | MIT, third-party notices | keep `LICENSE.TXT` and `THIRD-PARTY-NOTICES.TXT` of the runtime pack (not the SDK installer's licence) |
| `lzokay/lzokay.dll` | lzokay (Jack Andersen) | MIT | keep the notice |
| `nodtool/nodtool.exe` | nod (AxioDL) | MIT | keep the notice |
| `wit/bin/wit.exe` | Wiimms ISO Tools v3.05a r8638 cygwin64 | GPL-2.0 | licence text, corresponding source available (wit.wiimm.de, GitHub `Wiimm/wiimms-iso-tools`, SVN r8638) |
| `wit/bin/cygwin1.dll` | Cygwin 3.1.7 | LGPL-3.0+ with linking exception | LGPL + GPL text, source available (cygwin.com, tag `cygwin-3_1_7-release`) |
| `wit/bin/cygcrypto-1.1.dll` | OpenSSL 1.1.1f | OpenSSL + SSLeay | licence text and the three acknowledgements (in `THIRD-PARTY-NOTICES.txt`) |
| `wit/bin/cygncursesw-10.dll` | ncurses 6.1.20190727 | X11 style | keep the notice |
| `wit/bin/cygz.dll` | zlib 1.2.11 | zlib | none for binaries (notice included anyway) |

Licence texts for the v0.3.0 ZIP: the four of `randovania/data/gollop_mp3_patcher` (`LICENSE`, `lzokay/LICENSE`,
`nodtool/LICENSE`, `wit/gpl-2.0.txt`) plus `apworld/tools/release/licenses/` (GPL-3.0, LGPL-3.0, .NET runtime licence
and notices from the NuGet runtime pack, OpenSSL 1.1.1, ncurses, zlib). Players install Microsoft's Visual C++
redistributable separately. Dolphin needs it too.

GPL-2.0 (wit) and LGPL-3.0 (Cygwin) require the corresponding source to be available. It is attached to the same
release as the tools ZIP (`wiimms-iso-tools-r8638-src.tar.gz`, `cygwin-3.1.7-1-src.tar.xz`, see "Assets"), which
counts as equivalent access from the same place (GPL-2.0 section 3, GPL-3.0 section 6d). The tools ZIP's
`THIRD-PARTY-NOTICES.txt` points to these assets. When the tools ZIP moves to a new release (`TOOLS_RELEASE_TAG`), the
source archives must be attached there too.

### NTSC-U patch redistribution (T34)

The Windows tools ZIP prepared for v0.4.0 includes the following files with their copyright and licence notices.
The v0.3.0 release and its existing ZIP predate this change.

| Files | Licence and evidence |
|---|---|
| Ten `MP3Update/*.hdiff` PAK patches | MIT, copyright MrMiguel211. Every file matches the corresponding entry in the author's [MP3Update v7.2 ZIP](https://github.com/MrMiguel211/MP3Update/releases/download/MP3Update_v7.2/MP3Update_v7.2.zip) byte for byte, including the older `FrontEnd.hdiff` in the release asset. The same archive supplies `MIT-LICENSE.txt`, which expressly grants redistribution with the notice. Its bytes match the checked-in notice in Git. |
| `MP3Update/main.hdiff` (Deflicker) | Same MIT grant. The exact file is included in that licensed v7.2 ZIP and was introduced by MrMiguel211 in [Deflicker DOL Patch](https://github.com/MrMiguel211/MP3Update/commit/20a066020ee829c17dceca21578a48e30c75eebe). |
| `hpatchz.exe` | Exact match for `windows64/hpatchz.exe` in the official [HDiffPatch v4.6.9 Windows release](https://github.com/sisong/HDiffPatch/releases/tag/v4.6.9), SHA-256 `66d1c1427ad34f2e9aa60a06b3d48bfbed296fae3aad396ca4240a1e67bfc254`. The [v4.6.9 MIT notice](https://github.com/sisong/HDiffPatch/blob/v4.6.9/LICENSE) covers HDiffPatch and libdivsufsort and matches the checkout's `LICENSE.txt` after line-ending normalization. The Windows project and the matching source archive list bzip2 1.0.8, libmd5, LZMA SDK 23.01, zlib 1.2.11 and Zstandard 1.5.5 with xxHash. The ZIP includes their permissive notices and uses the BSD terms for Zstandard/xxHash. |

Verification on 2026-11-25 compared the author's actual release asset (SHA-256
`51e3517c2d4f26a015200a78eb8ce8be574a869c07c049c46885380472cda3da`) to the checked-in assets. The byte matches
identify the exact patch build used by T33. The MIT grant covers the author's distributed changes. The tools
ZIP contains binary diffs and helpers. A player supplies a clean game disc image and the tools apply the diffs locally.

T34 prepares a deterministic v0.4.0 tools ZIP with SHA-256
`ae2a7971f8d0d21847d18ebb9c2bd0c2988bba423f89f23404e50b7555e5c12d`.
Until v0.4.0 is published, use the helper folder from a checkout or build a local ZIP with
`python apworld/tools/release/build_release.py --tools-only` and place it into the Archipelago tools cache.

### Checked (T28)

Simulated fresh PC: only `apworld/metroidprime3/patcher` copied into an empty folder outside the repo (no
Corruptovania checkout reachable), `MP3AP_TOOLS_DIR` unset, `PATH` = `C:\Windows\System32;C:\Windows`, empty cache,
tools ZIP served by `python -m http.server` and `MP3AP_TOOLS_URL`: one download, hash checked, extracted, ISO built
from `AP_38224278823687041413_P2_Samus.apmp3` in 40 s, seed ID `7f5dd955…` read back; the ISO is SHA-256-identical
to the T05b/T23 builds (`e3cf4d7e…`). Second call: no download. Offline (refused port) and the not-yet-public GitHub
URL (404): error with the manual steps. ZIP placed into the cache by hand: extracted without network.
