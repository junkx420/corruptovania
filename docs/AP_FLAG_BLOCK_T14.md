# T14 live flag blocks

On PAL in PrimeHack, the Valhalla block at `0x80A4A720` was the first and only candidate observed gaining the
flag for Docking Bay 5 (location 11, byte 1). A word in the current GameState's world table points to that
block and distinguishes it from the two other plausible copies. The OR output agreed with the known pickup
state through the tested reloads. The checks below cover one pickup, one regular save and one older savestate.

## Setup and method

- 2026-11-27, PrimeHack 1.0.9, Wii PAL `RM3P01` Rev 0, CPU Clock Override disabled. A fresh emulator profile
  held a separate Wii save made at the Valhalla ship before collecting the pickup. A separate emulator
  savestate was made in front of the pickup before collecting it.
- Archipelago 0.6.8 with the repo APWorld and client, local solo generator seed `140014`, AP seed
  `63252288025812576431`, slot 1 `T14Samus`. The patched ISO and client both verified seed ID
  `fc5bd5afa8aff2ee059b38255be661a6`. Docking Bay 5 awarded Grapple Swing through the local AP server.
- The stock client's `/blocks` reports the cached MEM1 candidates, implausible tails and scan counts.
  `blocks_disagree` records disagreements for the current world as seen by the stock client. Fresh probe
  snapshots across MEM1 and MEM2 used the same signature and SAVW tail checks and retained all 1024 bytes
  of each valid or tail-rejected candidate. The fast pickup trace used the normal MEM1 finder at a nominal
  0.1 s interval. Every candidate address below is `W`, the address of its MLVL ID. Bytes are indexed from
  `W + 0x1C`. [SAVW mapping](AP_SAVW_FORMAT.md#5-mapping-location--byte)

## Pickup, reloads and world change

Times are local (CET). In this table, `A = 0x80A4A720`, `B = 0x8117DC60`, and `C = 0x8119CEC0` are Valhalla
candidates. `N = 0x809ED1C0`, `P = 0x8117C2E0`, and `Q = 0x8119B540` are Norion candidates. Values in each
tuple follow the listed address order. `ItemPercentage` is the sampled in-game pickup counter.

| Time | Emulator and event | Valhalla copies and byte 1 values | Norion copies | Other differing bytes | ItemPercentage and OR |
|---|---|---|---|---|---|
| 17:33:21 | PrimeHack, initial Valhalla at the ship | `A (00)` | `N` | None | `0`, no checks |
| 17:34:18 | PrimeHack, before pickup, after creating savestate | `A/B/C (00/00/00)` | `N/P/Q` | Valhalla byte 35 `01/01/00` | `0`, no checks |
| 17:35:01.390 | PrimeHack, first poll with the pickup flag | `A/B/C (01/00/00)` | `N/P/Q` in the preceding scan | Valhalla byte 35 `01/01/00` | `1`, location 11 |
| 17:35:18 | PrimeHack, settled after pickup | `A/B/C (01/00/00)` | `N/P/Q` | Valhalla byte 35 `01/01/00` | `1`, location 11 |
| 17:35:38 | PrimeHack, during departure for the game menu | `A (01)` | `N` in the rescan | None in Valhalla | `1`, location 11 |
| 17:37:05 | PrimeHack, loaded older ship save | `A (00)` | `N` | None | `0`, no checks |
| 17:37:36 | PrimeHack, same pickup collected again | `A (01)` | `N` | None | `1`, location 11, already checked at server |
| 17:38:18 | PrimeHack, loaded older savestate, pickup visible again | `A/B/C (00/00/00)` | `N/P/Q` | Valhalla byte 35 `01/01/00` | `0`, no checks |
| 17:39:55 | PrimeHack, Norion after travel from Valhalla | `A/C (00/00)` | `N/Q` | Valhalla byte 35 `01/00` | `0`, no checks |
| 18:05:40 | PrimeHack, fresh snapshot during the Norion polling run | `A/C (00/00)` | `N/Q` | Valhalla byte 35 `01/00` | `0`, no checks |

Byte 35 is a Valhalla memory relay without an AP location. Norion's compared copies were zero-filled at every
checkpoint. Across the settled snapshots, the complete 1024-byte comparisons found disagreements only in
Valhalla at the indices above. The location byte in the merge matched the known pickup state. On the first
pickup, the 0.1 s trace saw byte 1 only in `A` and confirmed it on the next poll at 17:35:01.492. The stock client logged
`blocks_disagree` on byte 35 before the pickup and on bytes 1 and 35 at 17:35:01.702. The server logged one
Grapple Swing award at 17:35:02. The secondary Valhalla copies still had byte 1 clear in the settled snapshot
about 17 s after the first change.

The ordinary reload passed through the menu and returned with byte 1 clear. The player confirmed that the
pickup was available again, then collected it once more with the AP server already aware of location 11.
Loading the older savestate restored the three candidates and cleared byte 1 in each. The fresh scan saw all
three, while the stock client kept its valid singleton cache through the savestate. A later transition to
Norion included a brief interval without a CPlayer and caused a fresh scan. Neither the fresh-scan OR nor the
stock client's observed OR contained a location absent from the known loaded state. That comparison uses the
raw flags, independently of the server suppressing another submission of location 11.

### Candidates by world

The first address in each row appeared at every settled checkpoint. The first and second additional copies were
both present before and after the first pickup and after the older savestate load. The second additional copy
remained on arrival at Norion. The initial ship snapshot, ordinary reload and repeat pickup each had only the
first address in each row. This gives totals of 14, 41 and 28 valid candidates for the respective layouts. There
were zero tail-rejected candidates at each of these checkpoints. Search hits that failed the client's header
checks were outside its candidate lists. The addresses beginning `0x811` are within MEM1, whose upper bound
is `0x81800000`. Extending the fresh snapshots into MEM2 surfaced no additional valid or tail-rejected blocks.

| World | First address | First additional copy | Second additional copy | Offset of first address in GameState table |
|---|---|---|---|---|
| Pirate Homeworld - Research | `0x80A2D800` | — | `0x81199BC0` | `+0x014` |
| G.F.S. Olympus | `0x80A04700` | `0x8117B1E0` | `0x8119A440` | `+0x084` |
| Pirate Homeworld - Command | `0x80A02DE0` | `0x8117B620` | `0x8119A880` | `+0x0BC` |
| Norion | `0x809ED1C0` | `0x8117C2E0` | `0x8119B540` | `+0x164` |
| SkyTown, Elysia - Seed | `0x80A07E40` | `0x8117CB60` | `0x8119BDC0` | `+0x1D4` |
| Bryyo - Fire | `0x80A270C0` | `0x8117CFA0` | `0x8119C200` | `+0x20C` |
| Bryyo - Reptilicus | `0x80A21FA0` | `0x8117D3E0` | `0x8119C640` | `+0x244` |
| Bryyo - Ice | `0x80A4A2E0` | `0x8117D820` | `0x8119CA80` | `+0x27C` |
| G.F.S. Valhalla | `0x80A4A720` | `0x8117DC60` | `0x8119CEC0` | `+0x2B4` |
| SkyTown, Elysia - Main | `0x80A4AB60` | `0x8117E0A0` | `0x8119D300` | `+0x2EC` |
| Bryyo - Seed | `0x80A18560` | `0x8117E4E0` | `0x8119D740` | `+0x324` |
| Pirate Homeworld - Mines | `0x80A189A0` | `0x8117E920` | `0x8119DB80` | `+0x35C` |
| Pirate Homeworld - Seed | `0x80A18DE0` | `0x8117ED60` | `0x8119DFC0` | `+0x394` |
| SkyTown, Elysia - Pod | `0x80A2F6C0` | `0x8117F1A0` | `0x8119E400` | `+0x3CC` |

## References from the current GameState

The PAL global `0x80680234` resolved to `GS = 0x80A48860`. Reading the big-endian word at `GS + 0x20`
gave `0x80A20F00`. The PAL DOL routine at `0x800BB64C` loads the count from `GS + 0x18`, loads the table
from `GS + 0x20`, and searches `0x38`-byte records by their first eight bytes (the MLVL ID). The live table
at Norion had count and capacity 19 and included all 14 worlds tracked by the client. Each of those records
held exactly one matching valid block address at `entry + 0x14`. For Valhalla the slot at `0x80A211B4` reads
`0x80A4A720`, matching the pickup observation. After the ordinary reload the same chain selected the expected
clear flag. The same table base and offsets survived loading the older savestate and changing to Norion.
Norion's slot at `0x80A21064` read `0x809ED1C0` on arrival.

An aligned RAM search also found unrelated references to some candidates. In Valhalla, `0x809A0454` also
referred to `A`, `B` had no exact reference, and `0x81199A14` referred to `C`. In Norion, `0x80A65CF4`
also referred to `N`, and `0x811998C4` referred to `Q`. A reference count would therefore classify secondary
copies as referenced too. The GameState root gives a reproducible discriminator for these samples. The run
reused the same GameState and table addresses across the measured reloads, so relocation is still unverified.
The two game-controlled save variants tested here did not produce a stale location byte in a plausible copy.
The original NTSC-U DOL has the same count, table pointer, stride and MLVL comparison in the lookup at
`0x800BB258`. The NTSC-U flag pointer and its live behavior still need checking.

## Extended polling

The operator requested 30 minutes in PrimeHack and omitted Dolphin. The PrimeHack session stayed on Norion
with CPU Clock Override disabled. A read-only watcher used the stock MEM1 finder at a nominal 0.5 s interval
alongside the local AP client. The 18:05:40 fresh scan across both banks independently reproduced the same
28 valid addresses, zero rejected candidates, byte contents and references as the arrival snapshot. The
watcher counted polls with recognized game state and valid flag data. Remote input and in-game dialogs were
outside the measurement.

| Emulator | Time with Clock Override off | Polling and scan behavior | Block changes, deviations and interruptions |
|---|---|---|---|
| PrimeHack 1.0.9 | 17:40:49–18:10:49, 1,800.015 s | 3,593 polls with valid Norion flags, one initial scan in 0.093 s, zero missing reads. `/blocks` stayed at four scans in the already-running client. | Norion remained at `0x809ED1C0` and `0x8119B540`, with no tail rejects, differing bytes, OR checks, or connection loss. The observer was stopped at the agreed cutoff. |
| Dolphin | Omitted at the operator's request | — | Dolphin stability and flag behavior remain unmeasured in T14. |

## Remaining verification before a client change

- Re-resolve the chain after cold boots and after loads that move GameState or the table. Confirm the table
  layout and limits independently and verify the chain on NTSC-U. Check mismatched MLVL IDs, missing candidates,
  menu/loading races and changes to the pointer while reading. Do the same comparison with game progression in
  more than one world, including a Norion pickup and a save where the flag was persisted as set.
- Try two different ordinary saves with intentionally different flags, including a new client or another AP
  room with an unchecked location. Compare the rooted copy, each secondary copy and the OR before server
  deduplication. Keep same-pointer savestate restores, death/continue and fast world changes in coverage.
- Verify that detection remains correct if a valid cached block survives a savestate while other candidates
  appear or disappear. Fresh scans and `/blocks` answer different questions when the cache stays valid.

## Reproduction

Run the read-only probe from the Archipelago checkout with the MP3 world linked in and
`dolphin-memory-engine` installed. Keep one emulator running at a time. The probe requires the expected
16-byte seed ID and emits JSON lines on stdout. Store the output outside the repo.
[T14 probe](../apworld/tools/live/flag_block_probe.py)

```powershell
$probe = '<Corruptovania checkout>\apworld\tools\live\flag_block_probe.py'
$runner = 'import runpy,sys; runpy.run_path(sys.argv.pop(1), run_name="__main__")'
$seed = 'fc5bd5afa8aff2ee059b38255be661a6'
.venv\Scripts\python.exe -B -c $runner $probe --seed-id $seed --emulator PrimeHack snapshot pre-pickup --references --mem2
.venv\Scripts\python.exe -B -c $runner $probe --seed-id $seed --emulator PrimeHack watch --interval 0.1 --seconds 900
.venv\Scripts\python.exe -B -c $runner $probe --seed-id $seed --emulator PrimeHack watch --interval 0.5 --seconds 1800
```

Use `/blocks` and the client's learning log alongside the snapshots. A `watch` session records scan durations,
changes to the current world's candidate bytes and the locations selected by the client's OR and debouncer.
`--references` additionally searches for aligned big-endian references to the current candidates and checks
the observed GameState table for valid candidate addresses from every known world.
