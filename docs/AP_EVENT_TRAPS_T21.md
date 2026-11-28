# T21 event traps and reload behavior

## Test setup

- PrimeHack 1.0.9, Wii PAL `RM3P01` Rev 0, CPU Clock Override disabled. The ISO uses the default PAL patch options. The NTSC-U MP3Update route variants are outside this run.
- Archipelago 0.6.8 and MP3 APWorld 0.4.0. Solo slot `T21Samus`, generator input `210021`, generated seed `87892535925681712698`, seed ID `1907c1b0c3de38481eb768f70eae8206` read back from the patched ISO.
- The generated spoiler lists `off` for the global trick level and no overrides. The standard starting inventory is Power Beam, Charge Beam, Combat Visor, Scan Visor, Space Jump Boots, Morph Ball, and Morph Ball Bombs. The slot has no additional starting items.
- On 2026-11-28, the ISO booted in a fresh PrimeHack profile with its own Wii saves and savestates. The AP client matched the running ISO to the local solo slot. Inventory readings confirmed the control items after the initial grants and again after restoring the baseline savestates.

## Gateway Green Lock

The graph puts the trigger at the green Bomb Slot in Gateway, reached with Morph Ball, Morph Ball Bombs, and Space Jump Boots after the orange lock. The expected cut is the pre-Green-Lock route back toward the orange slot. The route to the ship goes through Gateway Hall, where the return crossing from the Gateway side requires Grapple Lasso with tricks off. The intended control adds only Grapple Lasso and follows Gateway Hall back to the Cliffside Airdock ship. [Bryyo room graph](../randovania/games/prime3/logic_database/Bryyo%20-%20Reptilicus.txt)

The operator flew from G.F.S. Valhalla to Cliffside Airdock and saved at the ship at 00:52 local time. The regular save was backed up separately before going to Gateway. A read-only inventory snapshot on Bryyo confirmed the seven starting items, no pickups, and Grapple Lasso at `0/0` (amount/capacity).

After activating the orange slot, the operator saved PrimeHack slot 2 in Gateway in front of the still-inactive green Bomb Slot. Activating the green slot with the same inventory opened the locked door. The operator saw the obstruction move from the right side to the left platform. On the route back toward Cliffside Airdock through Gateway Hall, the operator stopped at the Grapple Lasso obstruction. The Wii save still matched the backed-up ship save byte for byte before leaving for the menu.

The operator quit to the game menu without manually saving and loaded the same slot. The game spawned at Cliffside Airdock. On returning to Gateway without touching either slot, the door was closed and the obstruction was back on the right. The regular save still matched the pre-event copy byte for byte. The event did not persist in the regular slot on this route and build.

Loading PrimeHack slot 2 independently restored the position at the green Bomb Slot with orange activated and green still inactive. The savestate recovered the later pre-event position, while the regular slot had returned the operator to the ship.

For the control, the operator reloaded at Cliffside Airdock. The local AP server sent Grapple Lasso as the only added item, and the client confirmed `0/0 → 1/1`. The operator made a new regular ship save, loaded the pre-Green-Lock state from slot 2, and waited for AP to reapply Grapple Lasso. The operator saved that state separately in slot 3 before activating the green slot again. With Lasso, the operator cleared the same obstruction and reached the ship in Cliffside Airdock. The Wii save still matched the control's pre-event ship save at that point. The blocked route and successful matching control agree with the E18 Grapple Lasso gate.

The control's regular menu reload left the Gateway door closed again. The ship save still matched its pre-event copy. Slot 3 also restored the pre-green state with the door closed and Grapple Lasso present.

## Gandrayda

The graph puts the trigger at defeating Gandrayda in Proving Grounds. It predicts the post-fight barrier will close the route to Transit Station 1-B. Grapple Voltage is required to remove the barrier. The graph also lists a post-fight Proving Grounds Lift exit with MP3Update enabled. PAL needs a live check of both doors, and the control needs the same pre-fight inventory plus Grapple Voltage. [Pirate Homeworld room graph](../randovania/games/prime3/logic_database/Pirate%20Homeworld%20-%20Research.txt)

The operator flew to the Research Facility and saved at the Landing Site Alpha ship at 01:13 local time. The approach without Voltage went through Scrapvault Lift, Scrapvault, Processing Access, Metroid Processing, Airshaft, and Craneyard. The local AP server supplied Plasma Beam, 25 Missiles, Ice Missile, Seeker Missile, X-Ray Visor, Screw Attack, Hazard Shield, six Energy Tanks, Boost Ball, Spider Ball, and Hypermode on top of the Gateway control inventory.

PrimeHack slot 4 was saved at the bottom of Proving Grounds Lift. The live inventory reader confirmed Grapple Lasso `1/1`, Grapple Voltage `0/0`, Missiles `20/25`, and zero pickups. The Wii save still matched the backed-up Landing Site Alpha save.

On that direct Research Facility approach, the operator found the lift inactive and no Federation trooper in the room. The vanilla sequence has the trooper radio Samus in Security Air Lock before the meeting at the lift. The first approach skipped the Command Center, so the missing encounter was observed before any attempt to defeat Gandrayda. [Prima game guide](https://metroiddatabase.com/old_site/mp3/mp3_primaguide.pdf)

The operator reloaded the regular Landing Site Alpha save, flew to the Command Center and crossed Security Air Lock. Re-entering the air lock from Defense Access still produced no radio call or mission update. The detour collected checks 89 and 86, yielding one additional Energy Tank and a Ship Missile Expansion. The cause of the missing story trigger was unresolved at that point.

The operator made a new regular save at Landing Site Alpha at 01:36, then used PrimeHack Noclip to pass the landing-site barrier. Noclip was disabled before the arena approach. The operator rode the train from Transit Station 1-A to 1-B and saved PrimeHack slot 5 before shooting the door into Proving Grounds. The read-only inventory showed Grapple Voltage `0/0`, Grapple Lasso `1/1`, Seeker Missile `1/1`, Missiles `25/25`, and seven Energy Tanks. This setup bypasses the landing-site entry barrier, which limits the live result to the fight and exit behavior after staging.

Opening the arena door from Transit Station 1-B started the fight. The operator defeated Gandrayda with Voltage still at `0/0` and left the boss pickup untouched. The energy field blocked the return to Transit Station 1-B and the coupling's scan called for Grapple Voltage. The lift in the arena also remained inactive. The Wii save still matched the pre-fight ship save after the victory.

The operator quit through the game menu without saving and loaded the regular slot. It spawned at Landing Site Alpha and the save bytes still matched. After crossing the landing-site barrier again for staging with Noclip and turning it off, opening the arena door from Transit Station 1-B restarted the fight. The victory did not persist in the tested regular slot.

Loading PrimeHack slot 5 independently restored Transit Station 1-B in front of the unopened arena door, before the fight. Grapple Voltage was still absent.

For the control, the operator returned to the Landing Site Alpha save and the local AP server sent Grapple Voltage as the only added item. The client confirmed `0/0 → 1/1`. The operator made a new regular ship save, restored slot 5, waited for AP to reapply Voltage, and saved at the same arena door in slot 6. The live reader confirmed the same missile count and Energy Tank capacity as the baseline, with Voltage now `1/1`.

After the second victory, the operator used Grapple Voltage on the coupling with the boss pickup still untouched. The door to Transit Station 1-B and the lift both became usable. The operator followed the transit route through 1-B and 1-A to the Landing Site Alpha ship with Noclip off. The save bytes still matched at the ship, before any new save. The blocked exits and successful control agree with the E18 Grapple Voltage gate on this PAL build.

The ordinary lift approach remains open for verification. The missing evidence is a pre-fight state on this build in which the Federation trooper appears and activates Proving Grounds Lift without a staging bypass.

## Reload evidence

Each attempt had a normal ship save and a separate pre-event savestate. The absent-item attempts exercised both recovery paths in order. The regular slot returned the operator to the ship and reset the gate or boss encounter. The savestate returned the operator to the later position just before the trigger. Gateway's control also exercised both load paths. Gandrayda's control checked the save bytes through the return to the ship. The autosave observations cover those event windows and menu reloads on this seed and PAL build.

## B9 SkyTown Elysia bomb sequence

T08 records a reported crash after collecting only the first bomb part without Seeker Missile and returning to SkyTown Elysia - Main. An older savestate restored play. The exact failing room and crash signature were not captured, and releasing location 97 on the server afterward did not exercise the sequence. [T08 playtest, B9](AP_PLAYTEST_T08.md#findings)

The room graph orders Turbine Chamber part 1, Concourse part 2, Transit Hub part 3, then bomb preparation at Spire Dock. Parts 2 and 3 require Seeker Missile. The candidate route back to Main crosses from Skytram East to Skytram West. T08 did not establish which room or transition failed. [SkyTown Pod room graph](../randovania/games/prime3/logic_database/SkyTown%20Elysia%20-%20Pod.txt) · [SkyTown Main room graph](../randovania/games/prime3/logic_database/SkyTown%20Elysia%20-%20Main.txt)

**Reproduction unconfirmed.** The operator had no compatible pre-part-1 test save. The missing evidence is a seed-matched save and savestate before Turbine Chamber part 1 with Boost Ball, Morph Ball, and Ship Grapple but no Seeker Missile, followed by a recorded return to Main, the last room and crash or successful transition, and the state after recovery. The regular-sequence comparison still needs the same baseline with Seeker Missile and the three parts completed in order.

## Scope of the logic comparison

E18 adds the post-event escape requirement to every graph edge entering a dangerous event. In this live run, both events still triggered without the corresponding escape item and both item controls restored a way to the ship. The regular and savestate reloads support E18's suggested recovery for these two tested events. E22 covers the one-way pickup exits seen in T08 B5, including Bryyo's Leviathan Core without Hyper Ball. E24 covers post-event re-entry costs, including Vaccine and Flux Control. [Decisions E18, E22, and E24](../SPEC.md#5-open-decisions) · [Generated logic notes](../apworld/metroidprime3/data/README.md)
