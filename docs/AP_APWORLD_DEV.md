# APWorld „Metroid Prime 3: Corruption“ – Entwicklung (T04)

Stand: 2026-11-24 · Archipelago **0.6.8** · Python 3.12 · MVP nach SPEC E3 (nur Item-Shuffle, Standard-Startort, Ziel fest)

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
MP3 + ChecksFinder fehlerfrei (124 Items). Die Ausgabe-ZIP enthält im MVP nur Multidata und Spoiler, noch keine
Patch-Datei (`.apmp3`, kommt mit T05).

## 3. Tests

Aus dem Archipelago-Ordner (`AP_TEST_WORLDS` beschränkt Archipelagos Tests auf diese World):

```powershell
$env:AP_TEST_WORLDS = "metroidprime3"
.venv\Scripts\python.exe -m pytest test/general -m "world or not world" -q
.venv\Scripts\python.exe -m pytest worlds/metroidprime3/test -q
```

Stand T04: `test/general` 250 bestanden; eigene Tests 39 bestanden (~6 s).

Die eigenen Tests (`apworld/metroidprime3/test/`) laufen nur im Archipelago-Klon (sie importieren `test.bases`,
`BaseClasses`, `Fill`), nicht mit dem pytest des Corruptovania-Repos.

| Datei | Prüft |
|---|---|
| `test_ids.py` | 99 Locations mit ID = Basis + Pickup-Index, Ort 0 fehlt; Item-IDs gegen festen Schnappschuss; jedes Daten-Item hat eine ID; Pool = 99 Items laut `data/items.py` inkl. Hypermode (48 Missile Expansions); Startitems precollected; `slot_data` JSON-fähig; keine `randovania`-Importe |
| `test_logic.py` | Regel-Semantik (and/or, „before event“ = erfüllt, Trick = nie, Progressive Beam, Launcher-Sperre, Energy Cells, Schaden); mit allen Items alle 99 Orte und Ziel erreichbar; einziges fehlendes Event ist „Gel Processing Site Out of Bounds“ (nur per Trick, T20); **Knoten-Sperre**: in 70 Inventaren (alle minus je ein Item, 40 zufällige) gilt an jedem erreichbaren gefährlichen Event-Knoten dessen `escape_requirement`; Kontrollwert Green Lock ↔ Grapple Lasso; Abgleich erreichbarer Knoten/Events mit `playthrough_sim.World.reach(logic=True)` für 40 zufällige Inventare |
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

## 6. Offen

- Kein `archipelago.json`-Manifest (Archipelagos Manifest-Test ist ohne Datei übersprungen; erst für das Release-Paket).
- Keine Patch-Ausgabe (`generate_output`) – T05.
- Tricks als Option (F9). Schadensnäherung (volle Energie je Requirement) bleibt optimistisch (T03).
- Import der 2,9 MB großen `data/logic.py` dauert beim ersten Mal ~3–5 s (danach `.pyc`). In einer gepackten
  `.apworld` (ZIP) wird kein `.pyc` geschrieben; dort ggf. später prüfen.
