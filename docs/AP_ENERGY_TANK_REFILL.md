# T27: Energy Tank refill in PrimeHack (PAL RM3P01)

On PAL Rev 0, current energy is a big-endian IEEE 754 binary32 (`>f`) at `CPlayerState + 0x0C`.
The stock AP client increased slot 20 from `0/0` to `1/1` while current energy stayed at `94.0`.
One four-byte write brought energy to `199.0` and displayed a full tank, matching the normal PAL pickup.
Subsequent damage remained until the player used the ship. NTSC-U RM3E01 energy addresses and behavior are unconfirmed.

## Setup

- 2026-11-27, PrimeHack 1.0.9. The AP run began in a previously empty slot on the G.F.S. Valhalla. The player
  made a separate pre-delivery savestate while injured. The comparison used the G.F.S. Olympus on the unmodified
  PAL disc, after the AP server and client were stopped.
- Prime3AP world/client 0.4.0 and Archipelago 0.6.8. A local solo seed was generated with default MP3 options and
  generator seed `270027`. The AP seed name was `91933537214420383970`, slot 1 `T27Samus`, ISO seed ID
  `c1521cb9a420640bb05425493946793d` (verified from the ISO and matched by the live client).
- PAL ISO built with the regional patches disabled. The private server listened on `127.0.0.1:38287`.
  The first Energy Tank was a single server-console `/send T27Samus Energy Tank`, delivered through the regular
  `ReceivedItems` and inventory reconciliation path.
- Probe samples were read every 0.2 s and checked against the user's HUD. The recorded times below are local.
  See [T08 B1 and B4](AP_PLAYTEST_T08.md#findings), [PAL player state and inventory](AP_MEMORY_MAP.md#2-field-table-pointer-chains),
  [ship save behavior](AP_SLOT_LIMITS.md#5-t15-do-capacities-drop-through-game-events) and
  [client reconciliation](AP_CLIENT.md#4-item-giving-t07-spec-e9-e11).

## Address and maximum energy

Square brackets indicate a big-endian 32-bit pointer dereference. Re-resolve the chain for each sample.

| PAL chain / check | Value at the refill |
|---|---|
| `GS = [0x80680234]` | `0x80A214C0` |
| `PS = [GS + 0x24]` | `0x80995B20` |
| `PS + 0x0C`, current energy, `>f` | `0x80995B2C` |
| `PS + 0x144`, slot 20, `>II` amount/capacity | `0x80995C64`, `1/1` |
| `[0x805C7570 + 0x28]`, CPlayer holder | `0x80A16800` |
| `[holder + 0x2184]`, CPlayer with vtable `0x80595238` | `0x80B8A5C0` |

The PAL DOL routine at `0x80191F38` loads the **amount** at `PS + 0x144` (`lwz` at `0x80191F44`) and computes
`99.0 + 100.0 * amount`. The sampled slot 20 values `0/0` and `1/1` give maxima of 99 and 199. The normal energy
adjustment routine at `0x80191FA4` reads and stores the float at `PS + 0x0C` (`lfs` at `0x80191FC8`, `stfs` at
`0x80191FE4`) and clamps it using that maximum. The tank branch in the pickup code at `0x801921E0` adds 9,999
through the slot-18 energy path. This explains the game-side full refill on the normal pickup path. A direct slot 20 write
updates the inventory without executing this path. Slot 18's stored amount/capacity stayed `0/0` throughout the AP
test. The neighboring float at `PS + 0x08` stayed `99.0` through damage, healing and the manual refill, then read
`199.0` after the regular save was loaded.

## Live measurements

The HUD shows the current bar and the tank indicators. With one full tank it shows 99 plus the filled tank, while
the float records the total. Values in the slot columns are amount/capacity.

| Time | Action | HUD after action | Current energy before → after | Slot 20 before → after |
|---|---|---|---|---|
| 16:02:21 | Fresh AP game | 99, 0 tanks | `99.0` (`42c60000`) | `0/0` |
| 16:03:43 | Damage | 97, 0 tanks | `99.0 → 96.5` (`42c10000`) | `0/0 → 0/0` |
| 16:04:12 | Heal by saving at the ship | 99, 0 tanks | `96.5 → 99.0` | `0/0 → 0/0` |
| 16:05:30–34 | Two hits, followed by the pre-delivery savestate | 94, 0 tanks | `99.0 → 96.5 → 94.0` (`42bc0000`) | `0/0 → 0/0` |
| 16:06:56 | One tank received from the AP server (B1) | One tank added | `94.0 → 94.0` | `0/0 → 1/1` |
| 16:07:20 | One explicit refill, with successful read-back | Full with 1 tank | `94.0 → 199.0` (`43470000`) | `1/1 → 1/1` |
| 16:07:51–54 | Two more hits | 94, 1 tank | `199.0 → 196.5 → 194.0` (`43420000`) | `1/1 → 1/1` |
| 16:08:29 | Regular ship save with the delivered tank | Full with 1 tank | `194.0 → 199.0` | `1/1 → 1/1` |
| 16:10:28 | Load the regular ship save from the game selection menu | Full with 1 tank | `199.0` | `1/1` |
| 16:12:37 | Load the injured pre-delivery savestate | — | `199.0 → 94.0` | `1/1 → 0/0` |
| 16:12:38 | Client restores the already received tank (B4) | 94, 1 empty tank | `94.0 → 94.0` | `0/0 → 1/1` |

After the refill the damage remained for about 35 seconds, until the ship save healed the player. The client stayed
connected throughout and the probe issued a single write. The ship save independently demonstrated the same
`199.0` full-energy value reached by the probe, using the game's own healing.

During the regular load, the probe lost the active CPlayer. It then resolved `GS = 0x80A3BD20`, holder
`0x80998DC0` and CPlayer `0x80B89B20`. The resulting `PS` remained `0x80995B20`, so the same field offset read
the saved tank and full energy through a newly resolved chain. Persistence of injured energy in a regular save
remains unconfirmed because the ship itself heals.

The older savestate restored `GS = 0x80A214C0`, CPlayer `0x80B8A5C0`, zero tanks and the saved injury without an
invalid-player sample at the 0.2 s cadence. The client logged the same `Energy Tanks 0/0 -> 1/1` write as it did at
initial delivery. Only the original delivery produced a receipt, and it was the only tank the server sent. This
shows why the inventory write or read-back by itself is insufficient to authorize a health write. This older
state changed `GS` back to its pre-load value, while [T08 B6](AP_PLAYTEST_T08.md#findings) also observed
same-pointer savestate jumps.

### Normal Energy Tank pickup

The read-only probe saw the original PAL build string and the G.F.S. Olympus world ID `0x37A9E86F0A0CAF6F`.
At the Ventilation Shaft pickup, it resolved `GS = 0x80A214C0`, CPlayer `0x80B8D2A0` and `PS = 0x80995B20`.

| Time | Sample | HUD | Current energy (raw bytes) | Slot 20 | Slot 18 |
|---|---|---|---|---|---|
| 17:16:35 | Before picking up the first tank | 98, 0 tanks | `97.44999694824219` (`42c2e666`) | `0/0` | `0/1` |
| 17:17:07 | After picking up the tank | Full with 1 tank | `199.0` (`43470000`) | `1/1` | `0/1` |

Both the normal pickup and the AP test write reached the same float and full HUD. The neighboring float at
`PS + 0x08` remained `99.0` across the pickup.

## Repeat the measurement

With `dolphin-memory-engine` installed, run the [probe](../apworld/tools/live/energy_probe.py) with Python from the repo
root. Use `read` for one sample or `watch` for changes. For the one-time write, use a disposable AP test save and keep
the player safe and stationary. Supply the verified AP seed ID, the two observed slot readings and the exact current
energy read from memory. The probe checks the disc revision, DOL build, active player and initialized inventory,
requires the expected live values, and reads back immediately. It writes four bytes of current energy only.

```powershell
venv\Scripts\python.exe -I apworld\tools\live\energy_probe.py read
venv\Scripts\python.exe -I apworld\tools\live\energy_probe.py watch
venv\Scripts\python.exe -I apworld\tools\live\energy_probe.py refill --seed-id c1521cb9a420640bb05425493946793d --before 0 0 --after 1 1 --energy 94
```

## Recommendation for client integration

Keep the absolute inventory targets and reload restoration from E11. Track a separate, one-shot refill entitlement
for each newly accepted AP Energy Tank receipt. For a conservative first implementation, establish the initial
`ReceivedItems` history as the baseline for the verified seed/team/slot and arm refills for validated appends from
that same live connection. Use the position in the accepted history as the receipt identity. An identical
`NetworkItem` tuple can occur twice with console sends, and a full sync can replay existing positions.

Only arm the health write when reconciliation actually increases slot 20 capacity and amount for an eligible
receipt. Require matching read-back of the new inventory, the verified seed, a settled live player state, and
positive finite health at or below the new maximum. If several eligible tanks land together, use the confirmed
new amount for one refill. Consume the entitlement once, including if energy is already full, and let subsequent
damage stand.
Recheck the player-state chain at the point of the write. Inventory restoration alone performs the ordinary E11
write and carries no refill entitlement, even when the pointers stay the same across a savestate load.

Treat reconnect and resync snapshots as history unless the client can match their prefix against a known receipt
history for that seed/team/slot. Decide how to handle delivery while offline or while the game is unavailable in the
integration task. A stable receipt identity allows deduplication across reconnects within a process. Exactly-once
behavior across a client restart would require durable receipt bookkeeping and a policy for interruption between
the RAM write and recording its completion. A pending refill spanning a reload also needs an explicit cancel or
revalidation rule because the process cannot detect every savestate transition from pointers alone.

Live coverage is limited to a first tank, ordinary energy, one regular ship save/load and one older savestate,
all on PAL Rev 0 in PrimeHack. Multi-tank deliveries, death or Hypermode during delivery, and the proposed receipt
tracking across reconnects and restarts remain unconfirmed.
