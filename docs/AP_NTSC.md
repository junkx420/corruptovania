# Wii NTSC-U support (T33)

Compared original standalone Wii discs PAL `RM3P01` Rev 0 and NTSC-U `RM3E01` Rev 0. The first six bytes of the NTSC-U
ISO are ASCII `RM3E01`. Disc number and revision are both zero. Trilogy `R3ME01` is a different game ID.

## PAL and NTSC-U comparison

Addresses below are Wii virtual addresses unless marked as DOL file offsets. `[X]` means a big-endian pointer read at
address `X`. `GSP` is the global GameState pointer slot, `GS = [GSP]`, `CSM` is the CStateManager global, and
`PS = [GS + 0x24]`. The NTSC-U globals from open-prime-rando 0.15.1 were checked against mapped code or data in the
original DOL. `corruption_remote_connector.py` supplies the field names and pointer chains.

| Field | PAL `RM3P01` | NTSC-U `RM3E01` | NTSC-U evidence |
|---|---|---|---|
| Game ID | `RM3P01` | `RM3E01` | ISO bytes `[0:6]`. The client reads six bytes at `0x80000000`. |
| Build info | `0x805843A8`, DOL `0x580488` | `0x805822B0`, DOL `0x57E390` | Unique `!#$MetroidBuildInfo!#$` text followed by `2007/07/27 13:13 Build v3.436 (MP3)`. Mapped using the DOL section header. |
| Seed ID | `0x805843AE`, DOL `0x58048E` | `0x805822B6`, DOL `0x57E396` | Build string slice `[6:22]`. The default and optional-patch builds returned the expected identifier when read back from the ISO. |
| GameState pointer slot (`GSP`) | `0x80680234` | `0x8067DC0C` | `0x80006510`/`0x80006514` initialize `r13` to `0x806801C0`. `0x802BAE70` is `lwz r3,-0x25B4(r13)` (`806DDA4C`), followed by `blr`. Stores including `0x802F127C` target the same SDA slot. The PAL getter at `0x802BC2F4` loads from `r13-0x258C`. |
| World ID (`u64`) | `GS + 0x08` | `GS + 0x08` | Matching GameState constructors at PAL `0x800B704C` and NTSC-U `0x800B6C58`. NTSC-U `0x800B6C8C` (`9103000C`) and `0x800B6C9C` (`90C30008`) store the lower and upper words at `+0x0C` and `+0x08`. |
| CPlayerState (`PS`) | `[GS + 0x24]` | `[GS + 0x24]` | NTSC-U constructor calls `0x8018F340` at `0x800B6CD0` and stores its result at `+0x24` at `0x800B6CD8` (`907E0024`). PAL has the matching store at `0x800B70CC`. |
| Inventory | `PS + 0x54 + slot × 0xC` | `PS + 0x54 + slot × 0xC` | `add_power_up` at `0x8019111C` matches the PAL function at `0x80191E2C`. At `0x80191148` it multiplies the slot by 12 and adds it to `PS`. It loads capacity at `0x80191158` (`+0x58`) and amount at `0x80191180` (`+0x54`). |
| CStateManager global (`CSM`) | `0x805C7570` | `0x805C4F70` | The accessor at NTSC-U `0x800E3A9C` returns the address using `lis r3,0x805C` and `addi r3,r3,0x4F70`. The matching PAL accessor is at `0x800E3F70`. |
| CPlayer pointer | `[[CSM + 0x28] + 0x2184]` | `[[CSM + 0x28] + 0x2184]` | `0x80017028`/`0x8001702C` (`80650028 80632184`) load both fields in order. PAL has the same instructions at `0x80016FF0`/`0x80016FF4`. |
| CPlayer vtable | `0x80595238` | `0x80592C78` | `0x8014A5A0`/`0x8014A5A4` load the address and `0x8014A5AC` stores it at object offset `0`. The same constructor sequence is at PAL `0x8014B06C`. |
| Item hash → slot table | `0x80584AB8`, DOL `0x580B98` | `0x805829C0`, DOL `0x57EAA0` | The unique 472-byte match to the 59 PAL `(u32 hash, u32 slot)` records contains exactly the same pairs in the same order. The lookup at `0x802D8E88`/`0x802D8E8C` loads the NTSC-U base and `0x802D8E90` loads 59. |
| Powerup slot table (T19) | `0x8057D5F8`, DOL `0x5796D8` | `0x8057B568`, DOL `0x577648` | Searched for a pointer to the `PowerBeam` C string followed by the big-endian words `1, 0xC0000000`. Dereferencing name pointers gives identical names, maxima and flags in all 70 entries. The `lis`/`addi` pair at `0x8019114C`/`0x80191150` also loads that base. |
| Generated location flag table | 99 locations | Same 99 locations | `build_location_flags.py --check` succeeds on both original extracts. Freshly generated files have identical SHA-256 `b05ca1f99416163c4502c5c862ec8853b3d7d41b5f53660859c732c611bfb4b0`. This includes `LOCATION_FLAGS`, `LOCATION_DETAILS` and `WORLD_NAMES`. |
| Heap flag block | MLVL ID at `W`, flags at `W + 0x1C` | Same signature in the client | All 14 SAVW IDs match when read from MLVL `+0x14`. The SAVW list-1 count differs only for Norion (149 → 148) and Valhalla (212 → 198). Block addresses are allocated at runtime. |

The equal powerup tables support using the same inventory limits. The saved-bit behaviour measured in T19 was tested
on PAL. See [AP_SLOT_LIMITS.md](AP_SLOT_LIMITS.md) for those tests.

## Reproduce the offline comparison

Extract each disc outside the repo and set both environment variables to the directories containing `DATA/files` and
`DATA/sys/main.dol`. Run these commands from the repo root.

```powershell
venv\Scripts\python.exe -I apworld\tools\build_location_flags.py $env:MP3_PAL_EXTRACTED --check
venv\Scripts\python.exe -I apworld\tools\build_location_flags.py $env:MP3_NTSC_EXTRACTED --check
venv\Scripts\python.exe -m pytest apworld\tools\test_savw_parser.py -v
```

For DOL pattern searches, read the 18 big-endian section offsets, virtual addresses and sizes at header offsets
`0x00`, `0x48` and `0x90`. Within a section, the virtual address is the section base plus the byte position relative
to that section. Search for the build string or the full PAL hash table in the NTSC-U data sections. For the slot
table, find `PowerBeam` with its terminating zero and map the string to its virtual address. Scan for that pointer
followed by `00000001 C0000000`, read 70 `>III` records and compare the dereferenced names, maxima and flags with
`SLOT_TABLE` in `apworld/tools/live/slot_probe.py`. Compare PowerPC words in the text sections at the addresses above.

## ISO builds

- The T33 NTSC-U build without MP3Update from a fresh Archipelago 0.6.8 solo seed (`64406527113896098792`, slot 1) returned game ID
  `RM3E01` and seed ID `6a837c358cfdf26f11bde78160b301cd` on read-back.
- The same NTSC-U build with `--mp3-update --disable-deflicker` also passed ISO and seed-ID read-back. Compared with
  the build without the patches, the extracted result has the same 99 primary flag tuples. Its generated details
  record a longer activation path for location 72 and an extra relay (byte 15) for location 76.
- The PAL example ISO built before and after T33 with the same original, patch JSON and helper binaries has matching
  SHA-256 `66b9e9c310c2031f5423c73f535a9a806bcd6b092aef529b4e9ebeb53372272a`.

### NTSC-U defaults and tools package (T34)

MP3Update needs `hpatchz.exe` and ten files in `MP3Update/` (`FrontEnd.hdiff`, `InGameAudio.hdiff`, `NoARAM.hdiff`,
`Metroid1.hdiff`, `Metroid3.hdiff`, `Metroid4.hdiff`, `Metroid5.hdiff`, `Metroid6.hdiff`, `Metroid7.hdiff` and
`UniverseArea.hdiff`). Disable Deflicker uses the same executable with `MP3Update/main.hdiff`. The patcher applies
the selected diffs to the extracted workspace before randomizing and stamping the seed ID.

Open Patch applies both patches by default to `RM3E01`. Set `metroidprime3_options.mp3update: false` in `host.yaml`
to skip both, or use `--no-mp3-update` on the CLI. PAL `RM3P01` uses the original six build steps.
The tools ZIP prepared for v0.4.0 includes the eleven diffs, `hpatchz.exe` and the licence notices.
See [AP_APWORLD_DEV.md](AP_APWORLD_DEV.md#ntsc-u-patch-redistribution-t34) for provenance.

T34 rebuilt seed `64406527113896098792`, slot 1, from its `.apmp3` through Archipelago 0.6.8 Open Patch with the
new tools ZIP installed and hash-checked. The build showed all seven steps and verified game ID `RM3E01` and seed
ID `6a837c358cfdf26f11bde78160b301cd` on read-back. The output and a separate Open Patch build with
`mp3update: false` matched the SHA-256 of the corresponding T33 builds (`6b7cee6b…` with both patches,
`41f4a7f3…` with both off). The real PAL rebuild matched the pre-T33 SHA-256 above.

## Live smoke test

On 2026-11-25, the T33 build without MP3Update booted in PrimeHack and a new game reached G.F.S. Valhalla, Docking Bay 5. The local
Archipelago 0.6.8 server and client agreed on the expected seed ID. A read-only RAM probe found `GS = 0x80A46080`,
world `0xC133F919C108BDF9`, `PS = 0x809934C0` with `PowerBeam.capacity = 1`, and CPlayer `0x80B87B80` with vtable
`0x80592C78`. The client found all 14 worlds' flag blocks, including Valhalla at `0x809F11E0` with 198 relays.

The user collected location 11. The learning log recorded `ItemPercentage` 0 → 1 and Valhalla byte 1 set to `1`.
The server received the Docking Bay 5 check and returned the seed's Grapple Voltage, which the client wrote as `1/1`.
The server console then ran `/send Samus Grapple Lasso`. The client logged receipt and slot 7 changed from `0/0`
to `1/1`. A read-only probe confirmed the new values and the user confirmed Grapple Lasso in the pause menu.

The build with both MP3Update and Disable Deflicker passed the same smoke test in a new PrimeHack game and fresh
server session. The client found Valhalla's flag block at `0x809F11E0` and the seed ID matched. Collecting location 11
set byte 1, the server returned Grapple Voltage, and the client applied the `/send` Grapple Lasso at `1/1`. The user
confirmed the Lasso in the pause menu. This was a Docking Bay 5 check of the combined options.

## Automated tests

The APWorld and Archipelago general suites passed 448 tests with the real PAL and NTSC-U extracts available. The
extended fill test passed separately for all 900 additional seeds. The existing PAL T10 memory snapshot test was
skipped because the snapshot was unavailable. The APWorld tool suite passed 56 tests with both extracts.
