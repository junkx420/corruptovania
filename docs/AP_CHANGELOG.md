# Prime3AP v0.4.0

Windows beta for Wii PAL (RM3P01) and NTSC-U (RM3E01) Rev 0 on Dolphin or PrimeHack. Requires Archipelago 0.6.8
or newer and your own clean disc image. [Installation guide](https://github.com/junkx420/Prime3AP/blob/v0.4.0/docs/INSTALL.md)

## Changes since v0.3.0

- Choose which removable starting items to keep with `starting_items`. Enable experimental tricks with
  `trick_level` and `trick_overrides` (E23). New players should leave tricks off.
- Small starting inventories get an opening chain of reachable local progression items so the rest of the seed
  can fill reliably.
- Added NTSC-U support with automatic MP3Update and Deflicker. PAL also applies Deflicker by default.
  Set `metroidprime3_options.mp3update: false` in `host.yaml` to disable the available patches for your region.
- Fixed re-entry after the Vaccine event and access to Flux Control (location 91) after the cover changes.
  The two missable Olympus checks hold only filler, and the client warns while either is open on Olympus (E24).
- Fixed a patcher crash when Morph Ball Bombs appears as an own pickup. Own Charge Beam, Space Jump Boots and
  Morph Ball pickups were also verified on both regions (T40).
- Universal Tracker v0.3.8 can rebuild the slot from seed data, including starting items, tricks and exclusions (T41).
- Use forward slashes in double-quoted `host.yaml` paths, for example `iso_file: "C:/Games/Metroid Prime 3.iso"`.

## Known limitations

- The patch tool runs on Windows. NTSC-J and Metroid Prime Trilogy are unsupported. PAL gets Deflicker only.
- The start stays at G.F.S. Valhalla, Docking Bay 5. The default settings still request early Screw Attack.
  DeathLink is unavailable.
- Received Energy Tanks are empty until you refill energy. Other players' pickups share one model and item text.
- For Leviathan cores, bring the exit item before entering (Bryyo: Hyper Ball, Elysia: Hyper Missile and at least
  four Missiles, Pirate Homeworld: Hyper Grapple and Grapple Voltage). The client warns if you are missing one.
- Bring Seeker Missiles before starting the SkyTown Elysia bomb sequence. Returning to SkyTown Elysia Main with
  only the first bomb component caused a crash in testing. Reload your save if this happens.
- The client checks multiple copies of each world's pickup flags. If a pickup fails to report, try leaving and
  re-entering the room. The host can use `/send_location` if the check is still missing.

## Downloads

| Asset | Use |
|---|---|
| `metroidprime3.apworld` | Install through the Archipelago Launcher. |
| `metroidprime3-example.yaml` | Copy to your player folder and set your slot name. |
| `metroidprime3-tools-win.zip` | Open Patch downloads and verifies this ZIP on first use. Download it manually for offline installs. |
| `wiimms-iso-tools-r8638-src.tar.gz`, `cygwin-3.1.7-1-src.tar.xz` | Corresponding source archives for wit and Cygwin. |
| `SHA256SUMS.txt` | SHA-256 checksums for every asset above. |

The tools ZIP includes licence texts and third-party notices for MP3Randomizer, nod, wit, Cygwin, MP3Update,
HDiffPatch and their dependencies. [APWorld and patcher source](https://github.com/junkx420/corruptovania/tree/archipelago)
