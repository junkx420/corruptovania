# Player options (v0.4.0, T31)

As of 2026-11-26 · world version 0.4.0 · decision E23

Metroid Prime 3: Corruption has three game-specific YAML options on top of Archipelago's standard options
(`progression_balancing`, `accessibility`, `start_inventory`, …). All three default to the behaviour of v0.3.0, so
an old YAML keeps working and gives the same seeds.

| Option | Default | What it does |
|---|---|---|
| `starting_items` | all four removable items | which of the removable starting items you keep |
| `trick_level` | `off` | **experimental**: global trick level the logic may expect |
| `trick_overrides` | `{}` | **experimental**: per-trick levels that replace `trick_level` |

## Local patch settings (`host.yaml`)

When you open your `.apmp3`, Archipelago uses `mp3update: true` by default. On PAL (`RM3P01`) this disables the game's
vertical deflicker filter for a sharper image. On NTSC-U (`RM3E01`) it also applies MP3Update. To keep the original
PAL filter or skip both patches on NTSC-U, edit `host.yaml` in your Archipelago folder and set the following value
under the existing `metroidprime3_options` section. Reopen the `.apmp3` to rebuild the ISO.

```yaml
metroidprime3_options:
  mp3update: false
```

**Troubleshooting a YAML error during generation.** Always write double-quoted paths in `host.yaml` with `/`, for
example `iso_file: "C:/Games/Metroid Prime 3.iso"`. YAML interprets backslashes inside double quotes as escapes and
can reject the file when you generate a seed.

## 1. Starting items

By default you start at G.F.S. Valhalla, Docking Bay 5, with Power Beam, Charge Beam, Combat Visor, Scan Visor,
Space Jump Boots, Morph Ball and Morph Ball Bombs (Randovania's starter preset). Four of them can be removed:

- Charge Beam
- Space Jump Boots
- Morph Ball
- Morph Ball Bombs

`starting_items` lists the ones you **keep**. Power Beam, Combat Visor and Scan Visor are always kept (the client needs
the Power Beam to recognise the game, and scanning is mandatory). Every removed item is shuffled into the item pool;
one Missile Expansion leaves the pool for it, so there are still 99 items. The patched game really starts without
the removed items: you get them like any other item, from a pickup in your world or from another player through the
server.

Archipelago's `start_inventory` still works on top of this: it adds items to the start (a removed item given there
is also still in the pool once, as with every `start_inventory` item).

### Small starts: the opening chain

With all removable items kept, three checks are in logic at the start, and (with default options) the world asks
Archipelago to put the Screw Attack on one of them, as in v0.3.0. With any item removed only two checks are left
(G.F.S. Valhalla - Docking Bay 5 and Norion - Docking Hub Alpha), and each further item opens just a few more.
Archipelago's fill cannot cope with such a narrow opening on its own (measured: 3–58 % of the seeds failed,
depending on what was removed; with the best two `local_early_items` still 0.3–5 %).

So before the main fill the world places a short **opening chain** in your own world: one of your own progression
items (or two, when only a pair opens something, such as Morph Ball + Bombs) on one of your open checks, then the next,
until eight of your checks are open. The items are picked at random, weighted by how much they open, and the checks
are random too; every item is placed where the logic already reaches it, so the chain never blocks you. Typically
3–12 of your first checks are decided this way. The rest of the world (and every other player's) is filled by
Archipelago as usual.

Every one of the 16 choices generates reliably (Archipelago's own fill, 300 seeds per choice, see section 4).

### Examples

Default (same as v0.3.0, the line can be left out):

```yaml
'Metroid Prime 3: Corruption':
  starting_items: ['Charge Beam', 'Space Jump Boots', 'Morph Ball', 'Morph Ball Bombs']
```

Only Space Jump (no Charge Beam, no Morph Ball, no Bombs at the start):

```yaml
'Metroid Prime 3: Corruption':
  starting_items: ['Space Jump Boots']
```

Only Morph Ball and Space Jump (no Charge Beam, no Bombs):

```yaml
'Metroid Prime 3: Corruption':
  starting_items: ['Morph Ball', 'Space Jump Boots']
```

Everything except the Morph Ball:

```yaml
'Metroid Prime 3: Corruption':
  starting_items: ['Charge Beam', 'Space Jump Boots', 'Morph Ball Bombs']
```

## 2. Tricks (experimental)

The logic can expect tricks from Corruptovania's database. Only the tricks the converter rates as usable are offered
(enough uses in the database, makes something reachable earlier, nothing the APWorld cannot evaluate), each up to a
maximum level:

| Trick | Highest level |
|---|---|
| Bomb Jump | advanced |
| Slope Jump | advanced |
| Knowledge | advanced |
| Movement | advanced |
| Bomb/Spring Space Jump | advanced |
| Invisible Objects | intermediate |
| Terminal Fall Abuse | advanced |
| Open Barriers from Behind | intermediate |
| Combat | advanced |

`trick_level` (`off`, `beginner`, `intermediate`, `advanced`) sets every offered trick at once, capped at its highest
level (`advanced` gives Invisible Objects and Open Barriers from Behind at `intermediate`). `trick_overrides` sets
single tricks; a value is `off`, `beginner`, `intermediate` or `advanced` (or 0–3), at most the trick's highest level.
Anything else (an unknown trick, a level above the maximum) stops generation with an error.

What the levels mean in the game is described in Randovania's trick documentation for Metroid Prime 3. The way out of
a dead end (getting back from a Leviathan core, for example) is always computed **without** tricks, so tricks never
trap you; they only let the logic put items behind trick routes. The trick option is experimental: the database's
trick data for Metroid Prime 3 is young, and the AP logic checks damage requirements with full energy, which is
optimistic for the Knowledge and Combat tricks.

### Examples

Beginner tricks everywhere:

```yaml
'Metroid Prime 3: Corruption':
  trick_level: beginner
```

Intermediate tricks, but no Combat tricks and advanced Movement:

```yaml
'Metroid Prime 3: Corruption':
  trick_level: intermediate
  trick_overrides:
    Combat: 'off'
    Movement: advanced
```

Only Bomb Jumps (everything else off):

```yaml
'Metroid Prime 3: Corruption':
  trick_overrides:
    Bomb Jump: advanced
```

A bare `off` works too (YAML reads it as `false`, which the world accepts as `off`).

## 3. Compatibility

- Old YAMLs (v0.3.0) without these options generate exactly the same placements as before.
- The client reads the starting items from the seed (`slot_data`). Seeds generated with v0.3.0 have no choice there
  and keep all seven starting items; a v0.4.0 client plays them as before.
- A seed with removed starting items needs a patched ISO from that seed's `.apmp3` (v0.4.0 patch tool). An ISO patched
  for another seed still has the old starting items; the client's seed check refuses it anyway (T18).

### Universal Tracker

The Metroid Prime 3 APWorld supports Universal Tracker v0.3.8 starting with the v0.4.0 release. Connect UT to your
slot with the updated APWorld installed. UT can rebuild the slot from the seed's starting-item choice, trick level,
per-trick overrides and excluded locations without a player YAML. It tracks starting inventory and pickups received
from the server, including items placed by the opening chain. The Olympus exclusions are part of the rebuilt world.

Older seeds use any starting-item and effective trick data they recorded, with defaults for missing options.
User-configured location exclusions are available for seeds generated with this support.

## 4. Fill check (T31)

Archipelago's own fill (`distribute_items_restrictive` + progression balancing, in process, solo). The "with chain"
and simulator columns were measured on the T36 data (and gave the same fill counts on the data before T36); "before"
and "best early pair" on the data before T36 (only the chain went into the world). "Before" = without the opening chain and without early items; "best early pair" = the best two
`local_early_items` found by a search over the removed items, Screw Attack, Missile Launcher, Grapple Lasso/Swing and
Progressive Beam (seeds 1–300). "With chain" = the shipped world. Simulator = `playthrough_sim.play` with the real AP
placement (seeds 1–50, eager 0 and 0.5): won with 99/99, never trapped.

| Removed starting items | Before (seeds 1–60) | Best early pair (1–300) | With chain, no tricks (1–300) | With chain, tricks advanced (1–100) | Chain length | Simulator |
|---|---|---|---|---|---|---|
| none (default) | 0 (T29 early Screw Attack) | – | 0 / 1200 (unchanged, no chain) | 0 / 100 (no chain) | 0 | 100/100 |
| Charge Beam | 0 | 0 (Missile Launcher + Lasso) | 0 | 0 | 2–8 | 100/100 |
| Space Jump Boots | 2 | 0 (SJB + Prog. Beam) | 0 | 0 | 3–9 | 100/100 |
| Morph Ball | 2 | 0 (MB + Lasso) | 0 | 0 | 3–9 | 100/100 |
| Morph Ball Bombs | 4 | 0 (Bombs + Prog. Beam) | 0 | 0 | 3–8 | 100/100 |
| Charge Beam, Space Jump Boots | 0 | 0 (SJB + Lasso) | 0 | 0 | 3–10 | 100/100 |
| Charge Beam, Morph Ball | 1 | 1 | 0 | 0 | 5–11 | 100/100 |
| Charge Beam, Morph Ball Bombs | 2 | 1 | 0 | 0 | 3–9 | 100/100 |
| Space Jump Boots, Morph Ball | 1 | – (40/40 in the search) | 0 | 0 | 6–10 | 100/100 |
| Space Jump Boots, Morph Ball Bombs | 4 | – (40/40 in the search) | 0 | 0 | 5–11 | 100/100 |
| Morph Ball, Morph Ball Bombs | 5 | 3 | 0 | 0 | 6–11 | 100/100 |
| Charge Beam, Space Jump Boots, Morph Ball | 22 | 2 | 0 | 0 | 6–12 | 100/100 |
| Charge Beam, Space Jump Boots, Morph Ball Bombs ("only Morph Ball") | 6 | – (40/40 in the search) | 0 | 0 | 5–11 | 100/100 |
| Charge Beam, Morph Ball, Morph Ball Bombs ("only Space Jump") | 7 | 12 | 0 | 0 | 6–11 | 100/100 |
| Space Jump Boots, Morph Ball, Morph Ball Bombs | 30 | no pair passes 40 seeds | 0 | 0 | 7–12 | 100/100 |
| all four | 35 | no pair passes 40 seeds | 0 | 0 | 7–12 | 100/100 |

Numbers are failed seeds (FillError, unfilled locations or unbeatable). "–" = the pairs that passed the 40-seed
search were not run on 300 seeds. Full start with `trick_level` beginner, intermediate or advanced (T29's early Screw
Attack only applies to fully default options): 0 / 300 each. Simulator with tricks advanced (seeds 1–30, both eager
settings): 60/60 for none, "only Space Jump", "Charge Beam + Space Jump Boots + Morph Ball" removed and all four
removed. A chain target of 5 or 6 open checks instead of 8 left 1 failure in 1500 seeds each.

`Generate.py` with the example YAMLs of this guide (default, "only Space Jump", "Morph Ball + Space Jump", the trick
example, plus ChecksFinder in one multiworld): 5/5 seeds.
