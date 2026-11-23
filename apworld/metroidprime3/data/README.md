# APWorld-Daten (generiert)

Diese Dateien erzeugt `apworld/tools/convert_db.py` aus der Corruptovania-Datenbank (Preset „Starter Preset“).
**Nicht von Hand ändern.** Sie sind eigenständige Python-Daten: keine Importe, kein Zugriff auf `randovania`
(SPEC 3a). Jede Datei lässt sich mit `import` oder `ast.literal_eval` auf den Wertteil lesen.

## Erzeugen

Im Repo-Root:

```powershell
venv/Scripts/python.exe apworld/tools/convert_db.py
```

Optional `--out <Ordner>` (Standard: dieser Ordner). Die Ausgabe ist deterministisch und unabhängig von
`PYTHONHASHSEED` (Test). Prüfen:

```powershell
venv/Scripts/python.exe -m pytest apworld/tools/test_convert_db.py -s
```

Der Test `test_committed_data_is_up_to_date` schlägt fehl, wenn die eingecheckten Dateien nicht zur Datenbank passen.
`__init__.py` und diese README schreibt der Konverter nicht.

## Dateien

### `locations.py`

| Name | Inhalt |
|---|---|
| `LOCATIONS` | Liste von genau 99 Orten, sortiert nach `id` (1–99) |
| `UNPATCHED_LOCATION` | Pickup-Index 0 (Olympus, MedLab Delta). Der Patcher fasst ihn nie an (E13), er ist **keine** AP-Location |

Ein Ort: `{"id", "name", "region", "area", "node", "category"}`.
- `id` = Pickup-Index des Corruptovania-Loaders = Nummerierung des Patchers. Das ist die AP-Location-ID.
- `name` = `"<region> - <area> - <node>"`, eindeutig. Der Regionsname enthält teils selbst ein „ - “ (z. B. `SkyTown, Elysia - Main`).
- `region`/`area`/`node` adressieren den Knoten in `logic.REGIONS`. `category` = `major` oder `minor`.

### `items.py`

| Name | Inhalt |
|---|---|
| `ITEMS` | Der AP-Pool: ein Eintrag je Itemname mit `count`. Summe aller `count` = **99** (= Anzahl Locations) |
| `STARTING_ITEMS` | Startitems laut Preset (Charge Beam, Power Beam, Combat Visor, Scan Visor, Space Jump Boots, Morph Ball, Morph Ball Bombs) |
| `LOCATION_0_ITEM` | Item, das Ort 0 vanilla behält (**Hypermode**, laut `original_locations` der Pickup-DB). Es ist **nicht** im AP-Pool (E17) |

Ein Item: `{"name", "category", "location_category", "count", "progression", "progressive", "is_expansion", "unlocks_lock", "lock", "stages"}`.
- `category`: GUI-Kategorie (`beam`, `missile`, `energy_tank`, `energy_cell`, `hypermode`, …).
- `stages`: Liste von Stufen, je Stufe eine Liste `(Ressourcenname, Menge)`. Das n-te erhaltene Exemplar gibt Stufe n
  (das letzte gilt für alle weiteren). Nicht progressiv = eine Stufe. Ressourcennamen sind die Namen, die in den Requirements
  (`type: "item"`) stehen. Randovanias reinen Zähler „Item Percentage“ lässt der Konverter weg.
- `progressive`: mehr als eine Stufe. `Progressive Beam` = Plasma Beam, dann Nova Beam. `Progressive Missile` = Ice Missile, dann Seeker Missile.
- `progression`: `True`, wenn das Item eine Ressource gibt, die irgendein Requirement abfragt. Ausnahme: Expansions, deren
  freischaltendes Item den höchsten geforderten Wert schon allein liefert (Missile Launcher gibt 5, gefordert wird höchstens 5;
  Ship Missile gibt 3, gefordert 1). Das sind Missile Expansion und Ship Missile Expansion (`False`).
- `lock` (Launcher-Sperre, sonst `None`): `{"locked_by", "item", "temporary", "respects_lock", "opened_by"}`. Ohne das Hauptitem
  `opened_by` landet die Munition (`item`) nur in `temporary` und zählt nicht. Das Hauptitem (`unlocks_lock = True`) bucht
  die Zwischenmenge um. `respects_lock` ist im Preset an (E15: im AP-Patch aus, der Client bildet die Sperre ab).
  Hinweis: In Randovanias Prime-3-Daten wird die Ressource `locked_by` von keinem Item gesetzt. Randovania selbst lässt Expansions
  nach dem Launcher daher weiter in `temporary` laufen. Für AP gilt die Besitz-Logik: Wer `opened_by` hat, bekommt die Munition.
  Die Logik braucht höchstens 5 Missiles bzw. 1 Ship Missile, das ändert also keine Erreichbarkeit.

### `logic.py`

| Name | Inhalt |
|---|---|
| `REGIONS` | `{region: {"areas": {area: {"nodes": {node: info}}}}}`. `info["type"]` ist `generic`, `dock`, `pickup`, `event` oder `teleporter_network`, dazu `heal`. Pickup: `pickup_index`, `category`. Event: `event`. Dock: `dock_type`, `weakness`, `target`, optional `lock`. Teleporter: `network`, `is_unlocked`, `requirement_to_activate` |
| `CONNECTIONS` | Liste von `{"from", "to", "kind", "requirement"}` (Knoten als Tupel `(region, area, node)`). `kind` = `area`, `dock` oder `teleporter_network`. Gerichtet. `from` muss erreicht sein, `requirement` erfüllt |
| `EVENTS` | `{event: {"kind", "sources": [{"node", "requirement"}]}}`. Ein Event gilt als erreicht, sobald ein `node` erreichbar ist und dessen `requirement` erfüllt ist. `kind`: `db` (Event-Knoten), `dock_lock` (Blast Shields als `Dock Lock: <region> - <area> - <node>`), `teleporter_network` (`Teleporter Network: <netz>`) |
| `TEMPLATES` | `{name: requirement}`, aufgelöst über `{"type": "template", "name": ...}` |
| `NODE_TYPES` | Anzahl der Knoten je Typ (Kontrolle) |

**Requirement-Baum:**
- `{"and": [...]}`, `{"or": [...]}` (leeres `and` = immer erfüllt, leeres `or` = nie).
- `{"type": "template", "name"}`
- `{"type": "item"|"event"|"trick"|"damage"|"misc"|"version", "name", "amount"}` und optional `"negate": True`.
  - `item`: Besitzmenge ≥ `amount` (Mengen aus `stages`, plus Startitems).
  - `event`: Event in `EVENTS` erreicht.
  - `trick`: Trick-Level ≥ `amount`. Level aus `game.SETTINGS["trick_level"]` (Preset: alle 0 = aus).
  - `damage`: siehe `game.SETTINGS["damage"]`.
  - `misc`/`version`: statische Schalter aus `game.SETTINGS` (`misc_resources`, `version_resources`); `negate` heißt „Wert < amount“.
- `{"type": "node", "node": ...}` kommt derzeit nicht vor.

**Nicht unterstützt (MVP: gilt als nicht erfüllt):** `event` mit `negate: True` („before event X“, 54×, nicht monoton), `item` mit
`negate` („no item“, 0×) und `node` (0×). Sie bleiben in den Daten, damit eine spätere Version sie auswerten kann.
Folge: Unter diesen Annahmen sind alle 25 Orte in SkyTown Elysia unerreichbar (siehe `STATUS.md`, T03).

### `game.py`

| Name | Inhalt |
|---|---|
| `VICTORY_REQUIREMENT` | Siegbedingung, ein Requirement: Event `Aurora Unit 313` |
| `START_LOCATION` | Startknoten `(region, area, node)` = Valhalla, Docking Bay 5, Samus Ship |
| `SETTINGS` | Preset-Einstellungen, die die Logik betreffen (unten) |
| `TRICKS` | `{Trickname: {"short_name"}}`, 18 Tricks |
| `TRICK_LEVEL_NAMES` | `{0: "disabled", … 5: "hypermode"}` |
| `REQUIREMENT_KINDS` | Zählung aller Requirement-Arten im Baum (Kontrolle) |
| `UNSUPPORTED_KINDS` | Nicht auswertbare Arten mit `count` und Grund |

`SETTINGS`:
- `trick_level`: `minimal_logic` (aus), `default_level`, `levels` = `{Trickname: Level}` (alle 0).
- `damage`: `strictness` 1.5, `starting_energy` 99, `energy_per_tank` 100, `reductions` = `{Schadensart: [(Item oder None, Faktor)]}` (derzeit leer).
  Ein `damage`-Requirement mit Menge `a` ist erfüllt, wenn `99 + 100 × Energy Tanks > ceil(Reduktion × int(a × strictness))`
  (Reduktion = kleinster Faktor der besessenen Items, sonst 1.0). Randovania rechnet Schaden entlang des Pfads mit Heilknoten
  (`heal`); das lässt sich in AP nicht abbilden. Die Näherung (volle Energie je Requirement) ist optimistisch.
- `misc_resources`: `Skipping Energy Cells`, `Entrance Randomizer`, `Phaaze Skip`, `MP3Update` (alle 0). `version_resources`: nur `NTSC` = 1.
- `other`: `teleporters`, `skip_final_bosses`, `dock_rando` (vanilla), `available_locations` (full), `start_with_corrupted_hypermode`, `MP3Update`, `disable_deflicker` (nur zur Information).

## Verwendung durch die APWorld (T04)

1. Je `LOCATIONS`-Eintrag eine AP-Location (ID = `id`), im Raum `(region, area)`.
2. Je `ITEMS`-Eintrag `count` Items. `progression` steuert die AP-Klasse.
3. Hypermode (`LOCATION_0_ITEM`) hat der Spieler, sobald Ort 0 im Spiel erreicht ist. Die Logik muss das Item an der Stelle von Ort 0 (`UNPATCHED_LOCATION`) vergeben.
4. Requirement-Bäume in Regeln übersetzen, nicht unterstützte Arten als „nicht erfüllt“.
