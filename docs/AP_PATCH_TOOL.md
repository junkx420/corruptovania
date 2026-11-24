# AP-Patch-Tool: AP-Patchdaten + Original-ISO → gepatchtes ISO (T05a)

Stand: 2026-11-24. Code: `apworld/metroidprime3/patcher/`, Tests: `apworld/metroidprime3/test/test_patcher.py`.
Grundlage: `AP_PATCHER_CHANGES.md` (T16, `--ap-mode`, APItem), `AP_PATCHER_NOTES.md` (T09), `AP_DEV_SETUP.md` (T01).

> **Kurzfassung**
> - Eingabe: eine JSON-Datei „AP-Patchdaten“ (Abschnitt 2) und das unveränderte PAL-ISO `RM3P01`.
> - Ablauf wie der Corruptovania-Exporter (entpacken, Attract-Videos ersetzen, Paks patchen, ISO bauen), aber
>   MP3Randomizer läuft **immer mit `--ap-mode`**, **ohne** MP3Update/Deflicker (E7), und die **Seed-Kennung** wird in
>   die Build-Info der `main.dol` geschrieben (T18 Teil 1).
> - Nur Standardbibliothek: keine Laufzeit-Abhängigkeit zu Randovania oder Archipelago. Die Buchstaben-Tabelle und die
>   Prüfsumme sind eigene Kopien, ein Test vergleicht sie mit dem Randovania-Original.
> - Die eingecheckte `randovania/data/gollop_mp3_patcher/MP3Randomizer.exe` ist jetzt der T16-Stand (win-x86, eine Datei).

## 1. Aufruf

Im Archipelago-Klon (APWorld per Junction eingebunden, `AP_APWORLD_DEV.md` Abschnitt 1):

```powershell
.venv\Scripts\python.exe -m worlds.metroidprime3.patcher --patch <datei.json> --iso <original.iso> --out <ziel.iso>
```

Ohne Archipelago (beliebiges Python ≥ 3.10, z. B. die Repo-venv), aus der Repo-Wurzel:

```powershell
venv\Scripts\python.exe apworld\metroidprime3\patcher --patch <datei.json> --iso <original.iso> --out <ziel.iso>
```

(`python -m metroidprime3.patcher` geht außerhalb von Archipelago nicht, weil dabei `metroidprime3/__init__.py`
geladen würde, das Archipelago braucht. Der Ordner-Aufruf lädt nur das Paket `patcher`.)

| Option | Bedeutung |
|---|---|
| `--patch` | AP-Patchdaten (JSON, Abschnitt 2) |
| `--iso` | Original-ISO, unverändert (`RM3P01`; `RM3E01`/`RM3J01` gehen mit Warnung, ungetestet) |
| `--out` | Ziel-ISO (wird überschrieben). Darf nicht das Eingabe-ISO sein |
| `--tools` | Ordner mit den Hilfsprogrammen (Standard: `$MP3AP_TOOLS_DIR`, sonst `randovania/data/gollop_mp3_patcher` dieses Repos) |
| `--temp-dir` | Ort für die Entpackung (Standard: `%TEMP%`; braucht ca. 2 × ISO-Größe frei) |
| `--no-verify` | Game-ID und Seed-Kennung im Ziel-ISO nicht zurücklesen |
| `--dry-run` | nur `--patch` prüfen und die Daten für MP3Randomizer ausgeben |
| `--read-seed-id <iso\|dol>` | Seed-Kennung eines ISOs oder einer `main.dol` ausgeben und beenden |

Beispiel (Beispieldatensatz aus dem Repo, Ausgabe gekürzt):

```
.venv\Scripts\python.exe -m worlds.metroidprime3.patcher --patch worlds/metroidprime3/patcher/example_patch.json --iso ..\mp3.iso --out ..\out\t05a_example.iso
[1/6] Extracting ISO...
[2/6] Removing attract videos...
[3/6] Copying paks...
[4/6] Randomizing paks (MP3Randomizer --ap-mode)...
[5/6] Writing seed ID into main.dol...
[6/6] Building ISO...
Done: ..\out\t05a_example.iso
  game ID   RM3P01 (Wii PAL)
  seed ID   fab57b6dbb249239b0a72671053cdd40 (read back from the ISO)
  player    Samus (slot 1, seed T05aExample)
```

Exit-Code 0 = Erfolg, 1 = Fehler (Meldung auf stderr: ungültige Patchdaten, falsches Spiel, fehlende Hilfsdatei,
Fehler eines Hilfsprogramms mit dessen Ausgabe). Temporäre Ordner werden in jedem Fall gelöscht.

Aus Python (z. B. für einen späteren Launcher-Eintrag):

```python
from worlds.metroidprime3.patcher import build, patch_data
data = patch_data.load("x.json")
build.patch_iso(data, iso, out)          # -> PatchResult(output, game_id, dol_version, seed_id, layout)
```

## 2. Format „AP-Patchdaten“ (Version 1)

Eine JSON-Datei je MP3-Slot. T05b erzeugt sie in `generate_output` mit
`patcher.patch_data.build_patch_data(seed_name, slot, player_name, pickups)` und `patch_data.dump(data, path)`.

```json
{
  "format": "metroidprime3-ap-patch",
  "version": 1,
  "seed_name": "T05aExample",
  "slot": 1,
  "player_name": "Samus",
  "seed_id": "fab57b6dbb249239b0a72671053cdd40",
  "pickups": {
    "1": "Archipelago Item",
    "2": "Missile Expansion",
    "11": "Screw Attack",
    "...": "...",
    "99": "Energy Tank"
  },
  "starting_items": "custom 0000000010010000000001100100100000000010000",
  "starting_location": "custom c133f919c108bdf9 d8cf355d3e9e3741"
}
```

| Feld | Pflicht | Inhalt |
|---|---|---|
| `format` | ja | immer `"metroidprime3-ap-patch"` |
| `version` | ja | `1`. Andere Werte werden abgelehnt |
| `seed_name` | ja | Seed-Name von Archipelago (`multiworld.seed_name`), nicht leer |
| `slot` | ja | Slot-Nummer (Ganzzahl ≥ 1) |
| `player_name` | ja | Spielername des Slots (nur Information/Ausgabe) |
| `seed_id` | nein | 32 Hex-Ziffern (16 Byte). **Muss** `make_seed_id(seed_name, slot)` sein (sonst Fehler); fehlt es, wird es daraus berechnet |
| `pickups` | ja | genau die Schlüssel `"1"` … `"99"` (Pickup-Index = AP-Location-ID − Basis, SPEC E13). Wert = Name des **angezeigten** Items: eigenes Item → sein Itemname (wie in `data/items.py`, z. B. `"Progressive Beam"`, `"Energy Cell 3"`), Item einer anderen Welt → `"Archipelago Item"` (Buchstabe `A`, T16) |
| `starting_items` | nein | Startinventar im Patcher-Format `custom <43 Hex-Ziffern>`. Standard = Starter-Preset (siehe unten) |
| `starting_location` | nein | Startort `custom <Welt-Asset-ID> <Raum-Asset-ID>` (hex). Standard = G.F.S. Valhalla, Docking Bay 5 |
| `_…` | nein | Schlüssel mit `_` am Anfang sind Kommentare und werden ignoriert. Alle anderen unbekannten Schlüssel → Fehler |

Erlaubte Itemnamen: jeder Name, der in der Buchstaben-Tabelle genau einen Buchstaben hat (`layout.DISPLAYABLE_ITEMS`),
außer `Power Beam` und `CannonBall` (der C#-Decoder kennt `0` und `L` nicht, `AP_PATCHER_NOTES.md` 1.5). Alle Pool-Items
der APWorld sind erlaubt (Test). Ort 0 steht nicht in den Patchdaten (E13/E17); das Tool setzt dort sein Vanilla-Item
Hypermode ein, der Patcher fasst Ort 0 ohnehin nie an.

Fest (nicht im Format, E3/E7/E15): Cosmetics (keine zufälligen Tür-/Schweißfarben, Standard-Suit), keine Phaaze-Abkürzung,
kein MP3Update/Deflicker, Missile-/Ship-Missile-required aus (setzt `--ap-mode` ohnehin), `--hyper-hints --fast-flying`
wie im Exporter.

**Standardwerte = Starter-Preset**, so wie Randovanias `patch_data_factory` sie für Seed IVG2J7OR erzeugt hat
(`build/seed/t01.patcher.json`): `starting_items` gibt Power Beam, Charge Beam, Morph Ball Bombs, Scan Visor, Morph Ball,
Space Jump Boots und `HyperModeOriginal = 1` (kein korrumpierter Hypermodus). Combat Visor hat das Spiel immer, er steht
nicht im String. Ein Test dekodiert den String mit Randovanias `STARTING_ITEMS_ORDER` und vergleicht mit
`data/items.py STARTING_ITEMS`.

### 2.1 Übersetzung für MP3Randomizer

`PatchData.randomizer_patch_data()` liefert dieselben Schlüssel wie Randovanias Patch-JSON (`layout patcher-data`), mit
festen AP-Werten und zusätzlich `"ap_mode": true`:

| Schlüssel | Wert |
|---|---|
| `seed` | Layout-String: `"00"` + 100 Buchstaben (Index 0 = Hypermode `z`, 1–99 aus `pickups`) + 5 Hex-Zeichen SHA-256 |
| `starting_items`, `starting_location` | aus den Patchdaten |
| `random_door_colors`, `random_welding_colors`, `missile_required_mains`, `ship_missile_required_mains`, `phaaze_skip`, `mp3_update`, `disable_deflicker` | `false` |

Kommandozeile (`build.randomizer_command`), gleich `game_exporter._build_randomizer_command` plus `--ap-mode`:

```
MP3Randomizer.exe --input-path <paks>\ --output-path <DATA\files>\ --layout <seed> --starting-items custom <hex>
  --starting-location custom <welt> <raum> --hyper-hints --fast-flying --ap-mode
```

### 2.2 Seed-Kennung (T18)

- Wert: `make_seed_id(seed_name, slot)` = die ersten 16 Byte von `SHA-256("metroidprime3-ap\0<seed_name>\0<slot>")`.
  Deterministisch, damit der Client sie aus `seed_name` (RoomInfo) und seinem Slot nachrechnen kann, ohne `slot_data`.
- Ort: Build-String der `main.dol`, Bytes 6–22 (im Original `roidBuildInfo!#$`), wie die Layout-UUID bei Randovania
  (`AP_MEMORY_MAP.md`, Zeile „Layout-UUID“). Reine Daten, kein Code liest den String.
- Adressen (eigene Kopie aus open-prime-rando `dol_versions.py`, `patcher/seed_id.py`):

| Version | Game-ID | Build-String-Adresse | Seed-Kennung im RAM | PAL-DOL-Dateioffset |
|---|---|---|---|---|
| Wii NTSC | RM3E01 | `0x805822B0` | `0x805822B6`–`0x805822C5` | – |
| Wii PAL | RM3P01 | `0x805843A8` | `0x805843AE`–`0x805843BD` | Build-String `0x580488` (Datensektion 11), Kennung `0x58048E` |
| Wii NTSC-J | RM3J01 | `0x80587C2C` | `0x80587C32`–`0x80587C41` | – |

- Schreiben: `seed_id.write_seed_id_to_dol_file(main_dol, seed_id)` (findet die Version über den Build-String, rechnet
  Adresse → Dateioffset über den DOL-Kopf, ändert genau 16 Byte).
- **Lesen (für den Client, T18 Teil 2):**

```python
from worlds.metroidprime3.patcher import seed_id
version = seed_id.version_for_game_id("RM3P01")
raw = dolphin.read_bytes(version.build_string_address, len(version.build_string))
found = seed_id.seed_id_from_build_string(raw, version)   # None = ungepatchtes/Nicht-AP-ISO
ok = found == seed_id.make_seed_id(room_seed_name, my_slot)
```

  `seed_id_from_build_string` wirft `ValueError`, wenn die Bytes gar nicht der Build-String dieser Version sind.
  Aus Dateien: `seed_id.read_seed_id(dol_bytes)`, `read_seed_id_from_dol_file(path)`, `build.read_seed_id_from_iso(iso)`
  (holt nur `sys/main.dol` per `wit EXTRACT --files +sys/main.dol`).

## 3. Voraussetzungen

- **Windows** (die Hilfsprogramme sind `.exe`). Python ≥ 3.10, nur Standardbibliothek.
- Hilfsprogramme im Tools-Ordner (alle im Repo eingecheckt unter `randovania/data/gollop_mp3_patcher/`):
  `MP3Randomizer.exe` (T16-Build, siehe 4), `lzokay/lzokay.dll` (32-bit), `nodtool/nodtool.exe`, `wit/bin/wit.exe`,
  `dummy_attract/attract01.thp`, `dummy_attract/Attract02.thp`. Fehlt eine Datei, bricht das Tool vor dem Entpacken ab.
  Randovania selbst (Python-Paket, venv) wird nicht gebraucht.
- Original-ISO PAL `RM3P01` (Rev 0, MD5 `f4c734a1e191c45e9ac037d92e14485d`). Trilogy wird abgelehnt.
- Freier Platz: ca. 2 × ISO-Größe in `--temp-dir` plus das Ziel-ISO (≈ 4,5 GB). Dauer ca. 1 Minute.

## 4. Eingecheckte MP3Randomizer-EXE (T16-Build)

`randovania/data/gollop_mp3_patcher/MP3Randomizer.exe` ist jetzt der Quelltext-Stand von T16
(`tools/prime3_patcher/MP3Randomizer`, Commit `f348f00bf`), als **eine** self-contained win-x86-Datei
(32 266 413 Byte, keine .NET-Installation nötig). Begleitdatei bleibt `lzokay/lzokay.dll` (unverändert).

```bash
export PATH="/c/Program Files/dotnet:$PATH" DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
dotnet publish tools/prime3_patcher/MP3Randomizer/MP3Randomizer.csproj -c Release -r win-x86 --self-contained true \
  -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -p:DebugType=none \
  --artifacts-path build/mp3r-single -o build/mp3r-single/publish
cp build/mp3r-single/publish/MP3Randomizer.exe randovania/data/gollop_mp3_patcher/MP3Randomizer.exe
```

Warum eine Datei: Der normale self-contained Build (`AP_DEV_SETUP.md` 3) sind ~220 Dateien / 67 MB; die Single-File-EXE
ist eine Datei mit 32 MB. `lzokay.dll` findet sie weiter über `AppContext.BaseDirectory` (= Ordner der EXE,
`Compression.cs`). Die alte EXE (242 KB, .NET-Framework-Build) brauchte keine Runtime; das gilt für die neue auch.

**Gegenprobe ohne `--ap-mode`** (Seed IVG2J7OR, Flags des Starter-Presets inkl. `--require-launcher
--require-ship-missile`, Eingabe = unverändertes PAL-`DATA/files`): alte eingecheckte EXE gegen neue Single-File-EXE,
**alle 13 Dateien SHA-256-gleich** (11 gepatcht, Logbook und MiscData unverändert). Ein voller Export mit
Randovania (Abschnitt 5) bestätigt das.

## 5. Ergebnisse (Abnahme T05a)

Siehe `STATUS.md` T05a. Details:

1. **Tests** (`test_patcher.py`, 20 Tests, im Archipelago-Klon):
   Buchstaben-Tabelle, Reihenfolge, Rückwärts-Tabelle, `AP_ITEM` und der Syntaxbaum von `layout_string_for_items`
   identisch zum Randovania-Quelltext (per `ast` gelesen, ohne `randovania` zu importieren); 50 Zufallsplatzierungen geben
   denselben String wie die Original-Funktion; Patchdaten von Seed IVG2J7OR → exakt Randovanias Layout-String
   `00kk44g44…kc602b`; Beispieldatensatz (gemischt) = Original-Funktion; Standard-Startwerte = Randovanias Patch-JSON des
   Starter-Presets; Validierung (13 Fehlerfälle); `--ap-mode` im Befehl, keine optionalen Flags; Paket nutzt nur die
   Standardbibliothek; Seed-Kennung schreiben/lesen auf Schein-DOLs aller drei Versionen und auf einer **Kopie der echten
   PAL-DOL** (`MP3_PAL_EXTRACTED`, sonst übersprungen): genau 16 Byte ab `0x58048E` ändern sich.
   Bestehende Tests: APWorld 84 bestanden (+ je ein Skip ohne Umgebungsvariable), `test/general` 250 bestanden.
2. **Beispiel-ISO**: `patcher/example_patch.json` (Platzierung IVG2J7OR, jeder dritte Ort `Archipelago Item`, 33 fremd /
   66 eigen, Ort 11 = Screw Attack) → `..\out\t05a_example.iso`, Game-ID `RM3P01`, Seed-Kennung zurückgelesen.
3. **Live-Test** (PrimeHack 1.0.9, „Emulated CPU Clock Override“ aus, neues Spiel): ISO bootet nach Valhalla; im RAM
   Game-ID `RM3P01` und Seed-Kennung `fab57b6dbb249239b0a72671053cdd40`. Ort 11 (Docking Bay 5) zeigt beim Einsammeln
   „Screw Attack acquired“; danach Screw Attack (Slot 16) weiter 0/0, nur ItemPercentage (Slot 21) 0/100 → 1/101, im
   Valhalla-Flag-Block nur Byte 1: 0 → 1.
4. **Normaler Export** ohne `--ap-mode`: alte und neue EXE geben für IVG2J7OR 13/13 identische Dateien; ein kompletter
   Randovania-Export (Starter-Preset) mit der neuen EXE ist SHA-256-gleich zum T01-ISO (`e63643aa…`).

## 6. Bekannte Lücken

1. **Nur Windows.** macOS/Linux bräuchten die Hilfsprogramme des Exporters für diese Plattformen (Randovanias
   macOS-Toolchain liegt nicht im Repo) und einen Linux-Build von MP3Randomizer.
2. **Hilfsprogramme kommen aus dem Repo** (`randovania/data/gollop_mp3_patcher`). Für eine verteilbare `.apworld` (T05b /
   Release, F10) müssen sie mitgeliefert oder heruntergeladen werden (`--tools`/`MP3AP_TOOLS_DIR` sind dafür vorbereitet).
3. **Kein Launcher-Eintrag / keine `.apmp3`-Datei**: Das Tool liest JSON; Einpacken in eine AP-Patch-Datei und Aufruf aus
   dem AP-Launcher macht T05b.
4. **Texte**: fremde Pickups zeigen alle „Archipelago-Item“ (E14); Spieler-/Itemname je Ort fehlt (nach dem MVP).
   Nur Englisch (wie alle Patcher-Texte).
5. **Nur PAL getestet.** NTSC-U/J werden mit Warnung akzeptiert, Adressen nur aus open-prime-rando.
6. Die Seed-Kennung prüft niemand, bevor der Client (T18 Teil 2) sie liest.
7. Startort und Startitems sind als Patcher-Strings im Format; strukturierte Startitems kommen mit F9 (Optionen).
8. Die EXE ist 32 MB und liegt als Binärdatei in Git (jede neue Version vergrößert die Historie).
