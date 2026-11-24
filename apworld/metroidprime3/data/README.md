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

Playthrough-Simulator (nur auf diesen Daten, ohne Randovania; siehe „Knoten-Sperre“ unten):

```powershell
venv/Scripts/python.exe apworld/tools/playthrough_sim.py --seeds 100 --eager 0.5
```

## Dateien

### `locations.py`

| Name | Inhalt |
|---|---|
| `LOCATIONS` | Liste von genau 99 Orten, sortiert nach `id` (1–99) |
| `UNPATCHED_LOCATION` | Pickup-Index 0 (Olympus, MedLab Delta). Der Patcher fasst ihn nie an (E13), er ist **keine** AP-Location und kein Teil der AP-Logik (E17). `vanilla_item` = `Hypermode` (nur zur Information: das gibt Ort 0 im Spiel lokal) |

Ein Ort: `{"id", "name", "region", "area", "node", "category"}`.
- `id` = Pickup-Index des Corruptovania-Loaders = Nummerierung des Patchers. Das ist die AP-Location-ID.
- `name` = `"<region> - <area> - <node>"`, eindeutig. Der Regionsname enthält teils selbst ein „ - “ (z. B. `SkyTown, Elysia - Main`).
- `region`/`area`/`node` adressieren den Knoten in `logic.REGIONS`. `category` = `major` oder `minor`.

### `items.py`

| Name | Inhalt |
|---|---|
| `ITEMS` | Der AP-Pool: ein Eintrag je Itemname mit `count`. Summe aller `count` = **99** (= Anzahl Locations): Standard-Pool (100) **minus eine Missile Expansion** (48 statt 49). **Hypermode ist im Pool** (E17 revidiert) |
| `STARTING_ITEMS` | Startitems laut Preset (Charge Beam, Power Beam, Combat Visor, Scan Visor, Space Jump Boots, Morph Ball, Morph Ball Bombs) |

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
| `CONNECTIONS` | Liste von `{"from", "to", "kind", "requirement"}` (Knoten als Tupel `(region, area, node)`). `kind` = `area`, `dock` oder `teleporter_network`. Gerichtet. `from` muss erreicht sein, `requirement` erfüllt. Verbindungen in den Knoten eines gefährlichen Events haben zusätzlich `escape_gate` = Eventname; ihr `requirement` ist dann immer `{"and": [<Requirement aus der DB>, <escape_requirement>]}` (Knoten-Sperre, unten) |
| `EVENTS` | `{event: {"kind", "sources": [{"node", "requirement"}]}}`. Ein Event gilt als erreicht, sobald ein `node` erreichbar ist und dessen `requirement` erfüllt ist. `kind`: `db` (Event-Knoten), `dock_lock` (Blast Shields als `Dock Lock: <region> - <area> - <node>`), `teleporter_network` (`Teleporter Network: <netz>`). Gefährliche Events (22) haben zusätzlich `node` (ihr einziger Event-Knoten), `escape_requirement` und `escape_inlined_events` (unten) |
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

**Nicht unterstützt:** `item` mit `negate` („no item“, 0×) und `node` (0×) gelten als nicht erfüllt.
`event` mit `negate: True` („before event X“, 54×, 22 Events, nicht monoton) gilt in der Logik als **erfüllt** (E18);
die Falle dahinter fängt die Knoten-Sperre ab. Alle bleiben in den Daten.

**Knoten-Sperre (E18).** Gefährlich ist jedes Event, das irgendwo negiert vorkommt (aus den Daten abgeleitet, 22).
Im Spiel löst schon das Betreten seines Event-Knotens das Event aus; danach ist „before X“ falsch und manche Wege sind zu.
`escape_requirement` ist die Bedingung, unter der man vom Event-Knoten im Zustand „nach X“ („before X“ = nicht erfüllt,
Event X = erfüllt) zu einem Schiff kommt (Knoten vom Typ `teleporter_network`, dessen `is_unlocked` gilt), nur mit den
Items, die man beim Betreten hat. Der Konverter hängt es per AND an **jede** Verbindung in den Event-Knoten. Die APWorld
wertet die Daten wie gewohnt aus und braucht **keine Sonderlogik**.
- Form: ODER von minimalen UND-Termen, Blätter nur `item`, `damage` und `event` (ohne `negate`).
  `{"and": []}` = immer erfüllt, `{"or": []}` = nie.
- Tricks, `misc` und `version` sind mit den Preset-Werten fest eingerechnet (Tricks aus). Mit Tricks ist die Sperre
  dadurch strenger als nötig, nie zu locker.
- Andere „before Y“ gelten auf dem Rückweg als erfüllt (wie überall in der Logik).
- **Zyklenfrei:** Events, die mit allen Items ohne X nicht erreichbar sind (`escape_inlined_events`), stehen nicht als
  Blatt im Baum, sondern sind durch ihr eigenes Requirement vom Event-Knoten aus ersetzt, rekursiv (z. B. Gandrayda:
  „Proving Grounds Barrier Removed“). Alle anderen Events bleiben `event`-Blätter.
- Kontrollwerte (Test; ohne Tricks, Knoten mit minimalen Items betreten): Gateway Green Lock → Grapple Lasso fehlt,
  Imperial Crypt Ice Floor → Screw Attack, Xenoresearch Power Outage → Seeker Missile, Gandrayda → Grapple Voltage,
  Flux Control Tunnel Cover → Spider Ball oder X-Ray Visor. Aurora Chamber Vaccine und Spire Bomb: keine Falle.
- Mit allen Items, ohne Tricks und mit Sperre sind Ziel, alle 99 Orte und 21 der 22 gefährlichen Events erreichbar.
  „Gel Processing Site Out of Bounds“ geht nur per Trick (auch ohne Sperre); mit allen Tricks sind es alle 22.
- Löst der Spieler ein Event gegen die Logik zu früh aus, hilft Neuladen (E18; ob das im Spiel klappt: T21).

**Playthrough-Simulator** (`apworld/tools/playthrough_sim.py`, nur auf diesen Daten): zufällige Füllung nach AP-Art
(Progression einzeln auf Orte, die mit allen restlichen Progressionsitems erreichbar sind, dann Füller) und ein Spieler,
der der Logik folgt. Einen gefährlichen Event-Knoten betritt er nur, wenn dessen `escape_requirement` gilt; das Event
löst aus, er steht danach am Knoten und kommt nur über echte Wege weiter („before X“ falsch, Verbindungen ohne Sperre).
`World.reach(..., logic=True)` = AP-Logik, `logic=False` = Spielphysik, `gated=False` = Logik ohne Sperre.
Test (Seeds 0–99, erlaubte Events zur Hälfte sogar vor dem Einsammeln): 100/100 gewonnen, jeweils alle 99 Orte.
Ohne Sperre bleibt derselbe Spieler hängen (Kontrolltest).

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
3. Ort 0 (`UNPATCHED_LOCATION`) ist keine Location und kommt in der Logik nicht vor. Hypermode ist ein normales Pool-Item.
4. Requirement-Bäume in Regeln übersetzen: „before event“ = erfüllt, „no item“ und `node` = nicht erfüllt.
   Die Knoten-Sperre steckt schon in `CONNECTIONS` (`escape_gate` nur zur Information).
