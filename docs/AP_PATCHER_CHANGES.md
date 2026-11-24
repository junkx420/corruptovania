# AP-Patcher-Änderungen: APItem und AP-Modus „nur anzeigen“ (T16)

Stand: 2026-11-24. Umsetzung von SPEC E10, E14, E15 im Patcher `MP3Randomizer` (C#) und im Python-Encoder.
Grundlage: `AP_PATCHER_NOTES.md` (T09), Messverfahren aus `AP_LIVE_TESTS.md` (Test D), Flag-Tabelle
`apworld/metroidprime3/location_flags.py` (T12).

> **Kurzfassung**
> - Neues Item **`APItem`** (Zeichen `A`): neutrales Modell, Text „Archipelago-Item“, gibt nie etwas.
> - Neuer Schalter **`--ap-mode`**: Jeder Pickup zeigt nur sein Item (Modell, Jingle, HUD-Text) und gibt nichts:
>   `item_type FF FF FF FF`, Menge/Kapazität 0/0, keine Progressive- oder Main-required-Relais. Missile- und
>   Ship-Missile-required sind dabei immer aus.
> - Ohne `--ap-mode` ist die Ausgabe **byte-identisch** zum Stand vorher.
> - Live (PrimeHack, Clock Override **aus**): APItem und ein eigenes echtes Item (Progressive Beam) ließen sich einsammeln,
>   Modell und Text stimmten, je ein Flag-Byte wurde gesetzt (Ort 11 → Byte 1, Ort 4 → Byte 8). Im Inventar änderte sich
>   außer dem Zähler ItemPercentage (Slot 21, +1 je Pickup) nichts.

## 1. Änderungen

### 1.1 C#-Patcher (`tools/prime3_patcher/MP3Randomizer/`)

| Datei | Änderung |
|---|---|
| `ItemName.cs` | neuer Eintrag `APItem` **am Ende** des Enums (bestehende Werte unverändert; `X`…`)` im Decoder hängen am Wert 0) |
| `MP3Randomizer/Item.cs` | Konstanten `AP_ITEM_MEMO_ID = 0xABCDABCDABCD000A` (nächste freie synthetische ID nach `…0009`) und `AP_ITEM_TEXT = "Archipelago-Item"`; neuer `case ItemName.APItem` (Tabelle 1.2) |
| `MP3Randomizer/STRGModificationData.cs` | neue STRG `AP_ITEM_MEMO_ID` mit dem englischen Text „Archipelago-Item“. Sie landet nur in einem Pak, wenn ein Pickup sie als Abhängigkeit hat (`PAK.gather_resources`) |
| `MP3Randomizer/MP3Dependencies.cs` | Eintrag `AP_ITEM_MEMO_ID` ohne Abhängigkeiten (wie die anderen synthetischen STRGs) |
| `MP3Randomizer/MP3Permalink.cs` | Decoder: Zeichen `A` → `ItemName.APItem` |
| `MP3Randomizer/Configuration.cs` | Flag `--ap-mode` (auch `-ap-mode`) → `ap_mode`. Ist es gesetzt, werden am Ende des Parsens `require_launcher` und `require_ship_missile` auf `false` gesetzt (E15), egal in welcher Reihenfolge die Flags stehen. Hilfetext ergänzt |
| `MP3Randomizer/MP3Randomizer.cs` | reicht `ap_mode` an `Patches.add_patches` weiter |
| `MP3Randomizer/Patches.cs` | `add_patches(..., bool ap_mode = false)` → `PickupPatches.add_pickup_patches(..., display_only: ap_mode)` |
| `MP3Randomizer/PickupPatches.cs` | Schalter `display_only`: direkt nach `Item.get_item_data` ruft er `apply_display_only(item)` auf: `item_type = FF FF FF FF`, `amount`/`capacity` = 0, `is_progressive = false`, Progressive- und Conversion-IDs leer. Modell, Charakter, Scan, Effekt, Jingle (STAU) und HUD-Text (MEMO) bleiben. Gilt für `Pickup`- und `SpecialFunction`-Orte (dort für das zweite PCKP `percentage_pickup_id`), für APItem und für echte Items |
| `MP3Randomizer.Tests/ApModeTests.cs` | 15 neue xUnit-Tests (Abschnitt 3.1) |

Nicht geändert: Fake-Pickups (`add_fake_pickup_patches`, zeigen nur das Modell), Startinventar, Ort 0 (wird weiterhin
nie gepatcht), die eingecheckte `randovania/data/gollop_mp3_patcher/MP3Randomizer.exe` (Austausch macht T05).

### 1.2 Das APItem

| Feld | Wert | Herkunft |
|---|---|---|
| `item_type` | `FF FF FF FF` | kein Inventar-Item (wie Progressive Items) |
| `amount`, `capacity`, `percent` | 0 | – |
| `model` (CMDL) | `31EF1551AF0D30D8` | statisches Energy-Cell-Modell (`Item.cs`, Fuse1–9). Keine Animation |
| `character` / `default_animation` | `FF…FF` / `FFFFFFFF` | wie Energy Cell (kein CHAR) |
| `scan` | `FF…FF` | **kein Scan**, damit kein irreführender Scan-Text erscheint |
| `pickup_effect` (PART) | `6BCBBA792CEA4332` | Standard-Effekt der meisten Items |
| `streamed_audio` (STRM) | `A832FC0C74651F24` | Expansion-/Energy-Cell-Jingle |
| `memo` (STRG) | `ABCDABCDABCD000A` | neu, Text „Archipelago-Item“ (nur Englisch, wie alle Patcher-Texte) |

„Neutral“ ist relativ: Das Spiel hat kein eigenes Platzhalter-Modell. Das Energy-Cell-Modell wurde gewählt, weil es
statisch ist (kein CHAR/ANIM) und schon in `MP3Dependencies` steht. Ein anderes Modell braucht nur neue Werte in
`case ItemName.APItem`. Das APItem gibt auch **ohne** `--ap-mode` nichts.

### 1.3 Python (`randovania/games/prime3/patcher/`)

| Datei | Änderung |
|---|---|
| `corruption_items.py` | Konstante `AP_ITEM = "Archipelago Item"` (Python-Name des APItems) |
| `gollop_corruption_patcher.py` | `LETTER_TO_ITEM_MAPPING["A"] = [AP_ITEM]` (vorher auskommentiert: `HyperModeBeam`, kein Pickup-Slot). `ITEM_NAME_TO_LETTER_MAPPING` leitet `AP_ITEM → "A"` daraus ab. Neu: `AP_MODE_FLAG = "--ap-mode"` und `ap_mode_arguments(ap_mode) -> tuple[str, ...]` (leer ohne AP-Modus) |

`patch_data_factory.py` und `game_exporter.py` sind **nicht** geändert. Der Randovania-Export kennt keinen AP-Modus und
bleibt unverändert. Den Schalter übergibt der Aufrufer selbst (Abschnitt 2), für T05 also das Patch-Tool der APWorld.

## 2. AP-Modus aufrufen

Layout-String wie bisher bauen, fremde Items als `AP_ITEM`, eigene Items mit ihrem normalen Namen:

```python
from randovania.games.prime3.patcher import gollop_corruption_patcher as g
from randovania.games.prime3.patcher.corruption_items import AP_ITEM

names = [...]                      # 100 Einträge, Index = Pickup-Index 0-99 (0 wird nie gepatcht)
names[11] = AP_ITEM                # fremdes Item
layout = g.layout_string_for_items(names)
extra = g.ap_mode_arguments(True)  # ("--ap-mode",)
```

Kommandozeile (alle übrigen Flags wie beim normalen Export, `game_exporter._build_randomizer_command`):

```
MP3Randomizer.exe --input-path <paks>\ --output-path <DATA\files>\ --layout <layout> \
  --starting-items custom <hex> --starting-location custom <welt> <raum> \
  --hyper-hints --fast-flying --ap-mode
```

`--require-launcher`/`--require-ship-missile` darf man mitgeben, sie werden mit `--ap-mode` ignoriert. Der Patcher erwartet
`Standard.ntwk` schon im Ausgabeordner (beim echten Export ist das so, `IO.write_b` öffnet mit `FileMode.Open`).

Build (win-x86, wie `AP_DEV_SETUP.md` Abschnitt 3): `build/mp3r/publish/MP3Randomizer.exe` plus `lzokay/lzokay.dll`.

## 3. Tests und Ergebnisse

### 3.1 Automatische Tests

- `dotnet test tools/prime3_patcher/MP3Randomizer.Tests/MP3Randomizer.Tests.csproj --artifacts-path build/mp3r-tests`:
  **17 bestanden** (2 alte + 15 neue). Neu geprüft: `--ap-mode` standardmäßig aus und schaltet Missile-required ab (beide
  Reihenfolgen); APItem-Daten; STRG-Text und Abhängigkeit; Decoder `A`; `apply_display_only` für Plasma Beam, Progressive
  Beam, Main-required-Expansion, Converter-Launcher, Energy Cell (Visuals bleiben, Itemfelder leer); `add_pickup_patches`
  mit `display_only` schreibt in **alle 99** PCKP `FF FF FF FF`/0/0, inklusive der **10 SpecialFunction-Orte** (9, 34, 42, 43,
  62, 70, 73, 79, 89, 93; zweites PCKP), und legt bei Progressive Beam keine Relais oder Verbindungen an; ohne Schalter gibt
  jeder Pickup weiter sein Item.
- `venv/Scripts/python.exe -m pytest test/games/prime3`: **24 bestanden** (19 alte + 5 neue in
  `test/games/prime3/patcher/test_gollop_corruption_patcher.py`: Buchstabe `A`, Layout-String mit APItem, Layout-String des
  Seeds IVG2J7OR unverändert, `ap_mode_arguments`, jeder Python-Buchstabe ist im C#-Decoder bekannt außer den alten Lücken
  `0` und `L`).
  Hinweis: Die GUI-Tests in `test/games/prime3/gui` brauchen die generierten Qt-Dateien (`*_ui.py`, per `.gitignore`
  ausgeschlossen). `setup.py build_ui` scheiterte in dieser venv (pyqt_distutils `TypeError`). Erzeugt wurden sie mit
  `pyside6-uic` für jeden Eintrag aus `pyuic.json`.

### 3.2 Byte-Gleichheit ohne AP-Modus

Patcher vor der Änderung (Quelltext-Stand `a556fc588`, win-x86-Build, gleich der eingecheckten EXE) gegen den neuen Build,
Seed IVG2J7OR (`build/seed/t01.patcher.json`), Eingabe = unverändertes PAL-`DATA/files`:

| Lauf | Ergebnis |
|---|---|
| mit `--require-launcher --require-ship-missile` (Starter-Preset) | alle **11** Ausgabedateien SHA-256-gleich |
| ohne Missile-required | alle **11** Ausgabedateien SHA-256-gleich |
| alter Build gegen eingecheckte EXE (Kontrolle) | gleich |

Mit `--ap-mode` und dem Test-Seed unten ändern sich Metroid1/3/4/5/7.pak. FrontEnd, Metroid6/8, UniverseArea, Worlds und
`Standard.ntwk` bleiben gleich. Der Text „Archipelago-Item“ steht in Metroid1.pak und Metroid5.pak, also in den Paks mit
den APItem-Orten.

### 3.3 Live-Test

**Umgebung:** PrimeHack v1.0.9, **CPU Clock Override aus** (vom Nutzer per Screenshot bestätigt, 100 %), VBI-Override aus,
PAL RM3P01, neues Spiel (Normal, Wegwerf-Speicherplatz). Messung mit `dolphin-memory-engine` wie `AP_LIVE_TESTS.md` Test D:
vor und nach jedem Pickup alle 70 Inventar-Slots (`PS + 0x54 + slot*0xC`) und der Flag-Block der Welt (Anker Welt-ID +
`0x400` bei `+0x18` + `0xEAEAEAEA` bei `−4`). Es gab jeweils genau einen Flag-Block.

**Test-ISO** (außerhalb des Repos, `..\out\t16_ap.iso`): Seed IVG2J7OR mit drei geänderten Orten, exportiert mit dem neuen
Build und `--ap-mode` (Missile-required aus):
`00kk44}44xtk9A4sdk444Cko{4rk^44}{4D447h44444444448uy44vk4Ik4444II44IIp4qk444B444kzII}44e#I4Ak44H4k4n4k63e2f`

| Ort | Item im Seed | Rolle |
|---|---|---|
| 11, G.F.S. Valhalla – Docking Bay 5 (Startraum) | APItem | fremdes Item |
| 4, Norion – Docking Hub Alpha (Grapple-Lasso-Ort) | Progressive Beam | eigenes echtes Item, nur anzeigen (prüft auch das Weglassen der Relais) |
| 89, Piratenheimatwelt – Command Courtyard (SpecialFunction) | APItem | optional, nicht angelaufen |

**Ergebnis** (2026-11-24):

| Ort | Modell (Nutzer) | Text / Jingle (Nutzer) | Inventar-Diff, 70 Slots | Flag-Block |
|---|---|---|---|---|
| 11 (16:52:47 → 16:54:19) | Energy Cell | „Archipelago-Item“, Jingle | nur Slot 21 ItemPercentage 0/100 → 1/101 | Valhalla `0x80A20180`: **Byte 1** 0 → 1, sonst nichts (vorher gesetzt: 35) |
| 4 (16:56:29 → 16:56:56) | Plasma Beam | „Progressive Beam acquired!“, Jingle | nur Slot 21 1/101 → 2/102. Plasma Beam (Slot 1) bleibt 0/0 | Norion `0x80A042C0`: **Byte 8** 0 → 1, sonst nichts (vorher gesetzt: 1, 6, 118) |

- Beide Pickups ließen sich einsammeln, kein Absturz. Die Flag-Bytes stimmen mit `location_flags.py` überein (11 → 1, 4 → 8).
- **Abweichung von „Inventar-Diff leer“:** **ItemPercentage (Slot 21) steigt je Pickup um 1**, wie bei jedem Pickup im
  Normalspiel. Ein Item gibt der Pickup nicht. Bewusst so gelassen: Der Lern-/Logmodus des Clients (E19) erkennt neue
  Pickups gerade am Anstieg von ItemPercentage. Der Wert liegt nicht im AP-Pool und stört die Soll/Ist-Vergabe (E11) nicht.
- Zwischen den Pickups änderte sich nur Slot 63 (Spielstatistik, Schüsse), das hat mit dem Pickup nichts zu tun.

**SpecialFunction-Ort live: nicht getestet.** Mit den Startitems ist kein SpecialFunction-Ort erreichbar
(Playthrough-Simulator, physikalischer Modus: nur Orte 4, 11, 84). Der nächste ist Ort 89 (Command Courtyard, braucht den
Plasma Beam, den man per Speicher-Schreiben geben könnte). Der Nutzer hat den Zusatzweg nach dem Pflichtteil abgelehnt.
Der Patcher-Teil ist per Unit-Test abgedeckt (3.1). Live bleibt das für T13 bzw. den Lernmodus im Playtest (E19).

## 4. Offene Punkte

1. **T05:** eingecheckte EXE durch diesen Build ersetzen und den Aufruf mit `--ap-mode` im Patch-Tool der APWorld bauen.
   Die APWorld darf zur Laufzeit nicht von Randovania abhängen. Sie braucht also eigene Kopien von `LAYOUT_LETTERS`, der
   Buchstaben-Tabelle und der Prüfsumme (`layout_string_for_items`).
2. Live-Test eines `FF FF FF FF`-Pickups an einem SpecialFunction-Ort (z. B. Ort 89), mit dem Flag-Byte (laut Tabelle Byte 10,
   „wahrscheinlich“). Der Test-ISO hat dort bereits ein APItem.
3. Ob ItemPercentage im AP-Modus unterdrückt werden soll, entscheidet der Client-Entwurf (E19 braucht den Anstieg).
4. Texte nur Englisch (wie alle Patcher-Texte). Auf PAL in einer anderen Systemsprache ungeprüft.
5. Speichern/Neuladen nach den AP-Pickups wurde in T16 nicht geprüft. Für MRLY-Bytes ist das aus T10 bekannt.
