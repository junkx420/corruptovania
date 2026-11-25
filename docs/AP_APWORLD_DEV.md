# APWorld „Metroid Prime 3: Corruption“ – Entwicklung (T04, Patch-Datei/Packen/Launcher T05b)

Stand: 2026-11-25 · Archipelago **0.6.8** · Python 3.12 · MVP nach SPEC E3 (nur Item-Shuffle, Standard-Startort, Ziel fest)

Die APWorld liegt unter `apworld/metroidprime3/`. Sie liest nur die generierten Daten in `apworld/metroidprime3/data/`
(T03/T20, siehe `data/README.md`) und importiert nichts aus `randovania` (SPEC 3a, Test `TestNoRandovania`).

## 1. Entwicklungsumgebung

Archipelago wird **außerhalb** des Repos geklont, z. B. neben `corruptovania`. Der Klon kommt nie ins Repo.

```powershell
cd ..
git clone --depth 1 --branch 0.6.8 https://github.com/ArchipelagoMW/Archipelago.git Archipelago
cd Archipelago
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe ModuleUpdate.py --yes
.venv\Scripts\python.exe -m pip install pytest
```

`ModuleUpdate.py --yes` installiert `requirements.txt` und die Requirements aller mitgelieferten Worlds (sonst fragt
`Generate.py` beim Start danach). Der erste Start kompiliert `_speedups` (braucht MSVC Build Tools, war vorhanden).

### APWorld einbinden

Als **Directory Junction** (Windows, keine Adminrechte nötig). Änderungen im Repo wirken sofort, Archipelago sieht den
Ordner als `worlds/metroidprime3`:

```powershell
cmd /c mklink /J "<Archipelago>\worlds\metroidprime3" "<corruptovania>\apworld\metroidprime3"
```

Linux/macOS: `ln -s <corruptovania>/apworld/metroidprime3 <Archipelago>/worlds/metroidprime3`.

Ohne Junction/Symlink geht auch eine Kopie (danach bei jeder Änderung wiederholen; der Playthrough-Test und
`test_matches_playthrough_sim_logic` werden dann übersprungen, weil `apworld/tools/` fehlt):

```powershell
robocopy "<corruptovania>\apworld\metroidprime3" "<Archipelago>\worlds\metroidprime3" /MIR /XD __pycache__
```

Entfernen der Junction: `cmd /c rmdir "<Archipelago>\worlds\metroidprime3"` (löscht nur den Link, nicht das Repo).

## 2. Seeds generieren

Beispiel-YAML (z. B. `<Archipelago>\Players\mp3.yaml`). Der Spielname enthält einen Doppelpunkt und **muss in
Anführungszeichen** stehen:

```yaml
name: Samus
game: "Metroid Prime 3: Corruption"
description: Beispiel-YAML fuer die MP3-APWorld (MVP, nur Standardoptionen)
"Metroid Prime 3: Corruption":
  progression_balancing: 50
  accessibility: full
```

```powershell
.venv\Scripts\python.exe Generate.py --player_files_path Players --outputpath output
```

Hinweis: Bei einem Fehler wartet `Generate.py` am Ende auf Enter. In Skripten stdin umleiten (`< NUL` bzw. `< /dev/null`).

2-Spieler-Seed: zweite YAML in denselben Ordner, z. B. ChecksFinder (Clique ist seit 0.6.x kein Kernspiel mehr):

```yaml
name: Finder
game: ChecksFinder
ChecksFinder:
  progression_balancing: 50
  accessibility: full
```

Ergebnis T04: 10 Solo-Seeds in Folge fehlerfrei (je ~0,4 s Generierung, ~4 s mit Start), 2-Spieler-Seed
MP3 + ChecksFinder fehlerfrei (124 Items).

Seit T05b enthält die Ausgabe-ZIP je MP3-Slot eine **Patch-Datei** `<Ausgabename>.apmp3` (z. B.
`AP_38224278823687041413_P2_Samus.apmp3`) neben `.archipelago` und Spoiler. Format: `AP_PATCH_TOOL.md` Abschnitt 2.3.
Aus ihr baut der Spieler sein ISO (Abschnitt 6).

## 3. Tests

Aus dem Archipelago-Ordner (`AP_TEST_WORLDS` beschränkt Archipelagos Tests auf diese World):

```powershell
$env:AP_TEST_WORLDS = "metroidprime3"
.venv\Scripts\python.exe -m pytest test/general -m "world or not world" -q
.venv\Scripts\python.exe -m pytest worlds/metroidprime3/test -q
```

Stand T05b: `test/general` 253 bestanden (3 mehr als T04: Archipelagos Manifest-Test läuft, weil es jetzt
`archipelago.json` gibt); eigene Tests 100 bestanden, 2 übersprungen (brauchen `MP3_PAL_EXTRACTED` bzw.
`MP3_MEM1_SNAPSHOT`), ~9 s.

Die eigenen Tests (`apworld/metroidprime3/test/`) laufen nur im Archipelago-Klon (sie importieren `test.bases`,
`BaseClasses`, `Fill`), nicht mit dem pytest des Corruptovania-Repos.

| Datei | Prüft |
|---|---|
| `test_ids.py` | 99 Locations mit ID = Basis + Pickup-Index, Ort 0 fehlt; Item-IDs gegen festen Schnappschuss; jedes Daten-Item hat eine ID; Pool = 99 Items laut `data/items.py` inkl. Hypermode (48 Missile Expansions); Startitems precollected; `slot_data` JSON-fähig; keine `randovania`-Importe |
| `test_logic.py` | Regel-Semantik (and/or, „before event“ = erfüllt, Trick = nie, Progressive Beam, Launcher-Sperre, Energy Cells, Schaden); mit allen Items alle 99 Orte und Ziel erreichbar; einziges fehlendes Event ist „Gel Processing Site Out of Bounds“ (nur per Trick, T20); **Knoten-Sperre**: in 70 Inventaren (alle minus je ein Item, 40 zufällige) gilt an jedem erreichbaren gefährlichen Event-Knoten dessen `escape_requirement`; Kontrollwert Green Lock ↔ Grapple Lasso; Abgleich erreichbarer Knoten/Events mit `playthrough_sim.World.reach(logic=True)` für 40 zufällige Inventare |
| `test_output.py` | `.apmp3` (T05b): Solo-Seed, MP3 + ChecksFinder und MP3 + ChecksFinder + MP3 → genau eine `.apmp3` je MP3-Slot; 99 Orte (1–99), eigene Items = echter Name, fremde (auch vom anderen MP3-Slot) = `Archipelago Item`, Seed-Kennung = `patcher.seed_id.make_seed_id`; gelesen mit dem Patch-Tool und mit `MP3Container`. Patch-Tool: `.apmp3` = gleiche Daten wie JSON, 7 Fehlerfälle, `--dry-run` mit `.apmp3`. Launcher-Helfer (Argumente, Client-Argumente aus dem Manifest, Ausgabepfad, Tools-Ordner), Komponente erkennt `.apmp3`; Settings (Game-ID-Prüfung); `archipelago.json`, `requirements.txt`, Dateiauswahl wie „Build APWorlds“ |
| `test_playthrough.py` | 20 Solo-Seeds mit Archipelagos Fill (`distribute_items_restrictive` + Progression Balancing); die echte AP-Platzierung geht an `playthrough_sim.play` (eager 0 und 0,5); der logiktreue Spieler gewinnt jeden Seed mit 99/99 Orten |

Gegenprobe (einmalig, nicht als Test): Ohne Knoten-Sperre in den Verbindungen gewinnt derselbe Spieler nur 10 der
20 AP-Seeds. Der Playthrough-Test erkennt eine fehlende Sperre also.

Der Simulator brauchte keine neue Schnittstelle: `play(world, placement, rng, eager)` nimmt `{Pickup-Index: Item-Record}`.
Die Adapterfunktion `ap_placement` im Test baut das aus der AP-Platzierung; fremde Items (Multiworld) werden zu einem
Record ohne Wirkung. Kleine Lücke: `World.give` im Simulator kennt die Launcher-Sperre nicht (Expansions geben ohne
Launcher Munition). Für die Logik egal, weil Expansions keine Progression sind.

## 4. Aufbau der World

| Datei | Inhalt |
|---|---|
| `__init__.py` | `MP3World`: Spielname `Metroid Prime 3: Corruption`, Items, Locations, Ziel, `fill_slot_data` |
| `items.py` | Basis-ID, feste Item-Offsets, `MP3Item`, Klassifikation (`progression` aus den Daten, sonst `filler`) |
| `locations.py` | 99 Locations aus `data/locations.py`, Gruppen je Spielregion (`Norion`, `Bryyo - Fire`, …) |
| `rules.py` | Compiler Requirement-Baum → AP-Regel; `StaticState` für die Vorberechnung |
| `regions.py` | Ein AP-Region je Logik-Knoten, Entrances, Event-Locations, Vorberechnung „mit allen Items erreichbar“ |
| `options.py` | `MP3Options` = nur Archipelagos Standardoptionen (E3) |
| `output.py` | `.apmp3`: `MP3Container` (`APPatch`), `displayed_pickups`, `write_patch_file` (T05b) |
| `settings.py` | `MP3Settings` = Abschnitt `metroidprime3_options` der `host.yaml` (Original-ISO, Tools-Ordner, Ausgabeordner) |
| `open_patch.py` | Launcher: `.apmp3` → ISO bauen → Client starten (T05b, Abschnitt 6) |
| `archipelago.json`, `requirements.txt` | Manifest und Abhängigkeit für die gepackte `.apworld` (Abschnitt 7) |

**IDs.** `BASE_ID = 0x4D503300` (= „MP3\0“ in ASCII, 1297101568).
- Location-ID = `BASE_ID + Pickup-Index` (1–99). Ort 0 (`UNPATCHED_LOCATION`) ist weder Location noch Event (E13, E17).
- Item-ID = `BASE_ID + ITEM_OFFSETS[name]`: Pool-Items 1–30, Startitems 101–107. Die Offsets stehen fest in `items.py`;
  neue Items bekommen die nächste freie Nummer, bestehende werden nie umnummeriert (Schnappschuss in `test_ids.py`).

**Regionen.** `Menu` → Startknoten `G.F.S. Valhalla - Docking Bay 5 - Samus Ship` (fest, E3). Jeder Knoten aus
`logic.REGIONS` wird eine Region `"<region> - <area> - <node>"`. Jede Verbindung aus `logic.CONNECTIONS` wird ein
Entrance (mehrere Verbindungen zwischen denselben Knoten per ODER zusammengefasst; Verbindungen, deren Regel konstant
falsch ist, entfallen). Die Knoten-Sperre (E18) steckt bereits im `requirement` der Verbindungen und wird nicht
gesondert behandelt. Die 99 Locations liegen in ihrem Pickup-Knoten, ohne eigene Regel.

**Events.** Jede Quelle eines Events in `logic.EVENTS` wird eine Event-Location `Event: <Name>` (bei mehreren Quellen
`Event: <Name> [k]`) im Quellknoten, Regel = Requirement der Quelle, mit gesperrtem Event-Item `<Name>` (Progression,
ohne ID). Ziel: `state.has("Aurora Unit 313")`.

**Vorberechnung.** Knoten und Event-Quellen, die selbst mit allen Items (ohne Tricks) unerreichbar sind, werden nicht
angelegt (Archipelagos Test verlangt, dass jede Region mit allen Items erreichbar ist). Das sind 8 von 943 Knoten und
1 von 230 Quellen („Gel Processing Site Out of Bounds“). Die Logik ist monoton, also ändert das nichts. Ergebnis
deckungsgleich mit `playthrough_sim` (Test).

**Regeln** (`rules.py`, Semantik wie `data/README.md`):
- `and`/`or` (leer: immer/nie), Templates einmal kompiliert und geteilt, konstante Teilbäume gefaltet.
- `item`: Ressourcenmenge aus den Stufen der gehaltenen Items (n-tes Exemplar gibt Stufe n, letzte wiederholt sich),
  Startitems zählen mit (precollected). Hat eine Ressource genau einen Lieferanten, wird daraus `state.has(item, n)`.
  Launcher-Sperre als Besitz-Logik: Munition eines Items mit `lock.opened_by` = anderes Item zählt nur mit diesem Item.
  Expansions sind `filler` und werden von Archipelago gar nicht in den State gesammelt.
- `event` → `state.has(event)`. `event` mit `negate` („before event X“) = **erfüllt** (E18).
- `trick` = nie erfüllt (MVP). `item` mit `negate` und `node` = nie erfüllt.
- `damage`: `99 + 100 × Energy Tanks > ceil(Reduktion × int(Menge × 1.5))` → Mindestzahl Energy Tanks.
- `misc`/`version`: statisch aus `game.SETTINGS`.

## 5. `slot_data` (Format, `slot_data_version` 1)

Alles, was der Client für den Soll-Zustand braucht (E11: Soll = Startitems + Wirkung aller empfangenen Items).

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

| Schlüssel | Bedeutung |
|---|---|
| `slot_data_version` | Formatversion; bei inkompatiblen Änderungen erhöhen |
| `seed_name` | Archipelagos Seed-Name (für die Seed-Prüfung, T18) |
| `base_id` | Basis der IDs (Location-ID − `base_id` = Pickup-Index) |
| `goal_event`, `start_location` | Ziel-Event und Startknoten (Info, im MVP fest) |
| `starting_items` | Namen der Startitems (Archipelago schickt sie nicht als empfangene Items) |
| `starting_resources` | Ressourcenmengen der Startitems (Namen wie in den Requirements, z. B. `Morph Ball Bomb`) |
| `items` | Alle MP3-Items (Pool und Start): `id`, `stages` (Liste von Stufen, je Stufe `[Ressource, Menge]`; n-tes empfangenes Exemplar gibt Stufe n, die letzte gilt für alle weiteren), `lock` (Launcher-Sperre wie in `data/items.py`, sonst `null`; die Sperre bildet der Client ab, E15) |
| `locations` | Location-ID (als String) → Pickup-Index 1–99 |

Ressourcen → Inventar-Slot (Spielspeicher) ist Sache des Clients (T07, `docs/AP_MEMORY_MAP.md`).

## 6. Patch-Datei öffnen: Launcher (T05b)

Die Launcher-Komponente **„Metroid Prime 3 Client“** (T06) erkennt jetzt `.apmp3` (`file_identifier`). Ohne
`.apmp3` startet sie wie bisher nur den Client.

Wege, eine `.apmp3` zu öffnen:

- Doppelklick auf die `.apmp3`, wenn die Endung mit dem Archipelago-Launcher verknüpft ist (beim installierten
  Archipelago über „Öffnen mit“ → `ArchipelagoLauncher.exe`),
- im Launcher **„Open Patch“** und die Datei wählen, oder die Datei auf das Launcher-Fenster ziehen,
- Kommandozeile: `.venv\Scripts\python.exe Launcher.py <datei.apmp3>` (Client-Argumente nach `--`, z. B. `-- --nogui`).

Ablauf (`open_patch.patch_and_launch`; bei offenem Launcher-Fenster in einem eigenen Prozess):

1. `.apmp3` lesen (`patcher.patch_data.read_container`). Fehler → Meldungsfenster, kein Client.
2. Original-ISO aus der `host.yaml`, `metroidprime3_options.iso_file`. Fehlt die Datei, öffnet sich ein Dateidialog
   („Metroid Prime 3: Corruption ISO (Wii PAL RM3P01, unmodified)“); der gewählte Pfad wird sofort in der `host.yaml`
   gespeichert. Geprüft werden nur die ersten 6 Byte (Game-ID `RM3P01`; `RM3E01`/`RM3J01` mit Warnung des Patch-Tools),
   kein Hash: der würde bei jedem Zugriff auf die Einstellung 4,7 GB lesen.
3. Ziel-ISO `<Name der .apmp3>.iso` neben der `.apmp3` (oder in `output_folder`). Trägt ein vorhandenes ISO dort schon
   die Seed-Kennung dieses Slots, wird nicht neu gepatcht (zweiter Doppelklick startet sofort den Client).
4. Patch-Tool (`patcher.build.patch_iso`, ~40 s). Fortschritt im Log `logs\MetroidPrime3Patch_<Zeit>.txt`; während des
   Patchens ist kein Fenster offen.
5. Metroid Prime 3 Client starten, mit `--connect <server>` (nur wenn die `.apmp3` einen Server enthält, also von der
   WebHost kommt) und `--name <Spielername>`; selbst übergebene Argumente haben Vorrang.

`host.yaml`-Abschnitt (legt Archipelago beim ersten Laden der World an):

```yaml
metroidprime3_options:
  iso_file: "C:\\...\\mp3.iso"   # Original-ISO, wird beim ersten .apmp3 abgefragt
  tools_folder: ""              # Ordner mit MP3Randomizer.exe usw.; leer/ohne EXE: $MP3AP_TOOLS_DIR, sonst Repo
  output_folder: ""             # leer: ISO neben die .apmp3
```

**Geprüft (T05b, Kommandozeile):** `Launcher.py ..\out\AP_38224278823687041413_P2_Samus.apmp3 -- --nogui` mit gesetztem
`iso_file`: ISO gebaut (Seed-Kennung zurückgelesen), danach Client gestartet, mit dem laufenden PrimeHack verbunden
(„Spiel RM3P01 erkannt“). Zweiter Aufruf: „already has seed ID …, not patching again“, Client startet sofort. Kaputte
`.apmp3` → Fehlermeldung, kein Client. **Manuell zu prüfen (GUI):** Dateidialog beim ersten Mal, „Open Patch“, Ziehen
aufs Fenster, Doppelklick mit Dateizuordnung.

## 7. Gepackte `.apworld`

Dateien: `archipelago.json` (Manifest: `game`, `minimum_ap_version` 0.6.8, `world_version` 0.1.0) und
`requirements.txt` (`dolphin-memory-engine>=1.3.0`, wie T06; in der venv ist 1.3.1 installiert).

Packen mit Archipelagos Launcher-Komponente „Build APWorlds“ (nur im Quellcode-Archipelago):

```powershell
.venv\Scripts\python.exe Launcher.py "Build APWorlds" -- "Metroid Prime 3: Corruption" --skip_open_folder
```

Ergebnis `build\apworlds\metroidprime3.apworld` (181 KB, 41 Dateien, entpackt 3,2 MB). Die Komponente nimmt alle
Dateien des Ordners außer `__pycache__`, `*.iso` usw. (`data/GLOBAL.apignore`), schreibt das Manifest samt
`compatible_version`/`version` dazu und folgt der Junction. `test/` ist mit drin (stört nicht).

Installieren: `.apworld` nach `custom_worlds\` (oder Launcher „Install APWorld“). Im Entwicklungs-Klon vorher die
Junction umbenennen, sonst gewinnt der Ordner („already loaded“): `cmd /c rename worlds\metroidprime3 _metroidprime3_dev`
(Ordner mit `_` lädt Archipelago nicht), zurück mit `cmd /c rename worlds\_metroidprime3_dev metroidprime3`.

**Geprüft (T05b):** Mit umbenannter Junction und `custom_worlds\metroidprime3.apworld` lädt Archipelago 0.6.8 die World
aus der ZIP (`zip_path` gesetzt, `v0.1.0` in der Generator-Ausgabe); `Generate.py` mit MP3 + ChecksFinder erzeugt
fehlerfrei einen Seed, die Ausgabe-ZIP enthält `AP_…_P2_Samus.apmp3`.

**Ladezeit** (`python -X importtime`, je 3 Läufe, Python 3.12, alle Worlds geladen):

| Quelle | `data/logic.py` (2,9 MB) | `import worlds` gesamt |
|---|---|---|
| Ordner (Junction, `.pyc` vorhanden) | 0,12–0,13 s | 3,6–3,7 s |
| gepackte `.apworld` (kein `.pyc`, wird bei jedem Start kompiliert) | 0,25 s (davon `compile` 0,12 s) | 3,7–3,8 s |

Die Befürchtung aus T04 (3–5 s) trifft nicht zu: Das Kompilieren der reinen Datenliterale kostet ~0,12 s je Start, die
Gesamtzeit bestimmen die anderen Worlds. Kein Handlungsbedarf (kein `.pyc` in die ZIP nötig).

**Abhängigkeit:** Archipelago 0.6.8 installiert die `requirements.txt` einer gepackten `.apworld` nicht selbst
(`ModuleUpdate.py` liest nur `requirements.txt` von World-Ordnern). `dolphin-memory-engine` ist trotzdem vorhanden: im
installierten Archipelago über die mitgelieferte Wind-Waker-World, im Quellcode-Archipelago über `ModuleUpdate.py --yes`.
Die Hilfsprogramme des Patch-Tools liegen **nicht** in der `.apworld` (`AP_PATCH_TOOL.md` 6.2): `tools_folder` setzen
oder einen Corruptovania-Checkout nutzen.

## 8. Offen

- Tricks als Option (F9). Schadensnäherung (volle Energie je Requirement) bleibt optimistisch (T03).
- Patch-Hilfsprogramme (MP3Randomizer, nodtool, wit) mit dem Release ausliefern oder herunterladen (F10/E20).
- Während des Patchens (~40 s) zeigt der Launcher nichts an (nur Log); ein Fortschrittsfenster fehlt.
- GUI-Weg (Dateidialog, „Open Patch“, Doppelklick) nur beschrieben, nicht von mir geklickt.
