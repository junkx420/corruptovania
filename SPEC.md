# SPEC – Metroid Prime 3 Archipelago (Entwurf)

Stand: 2026-11-23 · Status: **E1–E4, E7 entschieden; E5, E6 offen**

## 1. Ziel

Metroid Prime 3: Corruption als spielbares Archipelago-Spiel (Multiworld): Items von MP3 landen in fremden Welten, fremde Items in MP3, Fortschritt wird live über einen AP-Server synchronisiert.

Nicht-Ziel (vorerst): Weiterentwicklung von Corruptovania als eigenständiger Randovania-Fork, macOS-Builds, Discord-Bot/Server-Teile von Randovania.

## 2. Ausgangsbasis (oberflächliche Sichtung)

| Bereich | Ort | Nutzen für AP |
|---|---|---|
| Logik-Datenbank (Regionen, Räume, Requirements, Tricks) | `randovania/games/prime3/logic_database/*.json` | Quelle für Regionen/Locations/Regeln |
| Pickup-Datenbank, Item-Pool | `randovania/games/prime3/pickup_database`, `generator/` | Quelle für Item-Liste |
| Export/Patch-Daten | `randovania/games/prime3/exporter/` (`patch_data_factory.py`, `game_exporter.py`, `toolchain.py`) | Erzeugt Patch-JSON für den Patcher |
| ISO-Patcher (C#/.NET 8) | `tools/prime3_patcher/MP3Randomizer` | Schreibt Items ins Spiel; braucht AP-Platzhalter-Items |
| Dolphin-Speicheranbindung | `randovania/game_connection/connector/corruption_remote_connector.py` (152 Zeilen), `executor/dolphin_executor.py` | Basis für den AP-Client (Location-Checks lesen, Items geben) |
| Lizenz | GPLv3 (`LICENSE`) | Abgeleitete Teile müssen GPLv3 bleiben |

Befunde T01 (Details `docs/AP_DEV_SETUP.md`): Patcher muss als **win-x86** gebaut werden (`lzokay.dll` ist 32-bit). Kein Code prüft Game-ID/Hash. MP3Update-/Deflicker-hdiffs funktionieren nur auf NTSC-U. Exporter nutzt noch die eingecheckte EXE.

Hinweise: Python ≥ 3.12. Im Repo gibt es keinerlei Archipelago-Code. Letzter Commit 2026-08-16. Upstream-Remote `origin` = Schwork-Corruption/corruptovania (kein eigener Fork eingerichtet).

## 3. Architektur (festgelegt durch E1)

```
Archipelago (Generator)                         Spieler-PC
┌────────────────────────────┐                 ┌───────────────────────────────┐
│ apworld "metroidprime3"    │  .apmp3 Patch   │ Patch-Tool                    │
│ - items.py / locations.py  │ ──────────────▶ │  Patch-JSON → MP3Randomizer   │
│ - regions/rules (generiert │                 │  → gepatchtes ISO             │
│   aus Corruptovania-DB)    │                 │                               │
│ - options.py               │                 │ AP-Client (MP3Client)         │
└────────────────────────────┘                 │  Dolphin-Memory ⇄ AP-Server   │
              ▲                                │  (Checks senden, Items geben) │
              │ Konverter-Skript (einmalig/CI) └───────────────────────────────┘
   Corruptovania logic_database/*.json
```

Bausteine:
1. **DB-Konverter**: liest Corruptovania-JSON, erzeugt AP-Regionen, Locations, Regeln (Requirement-Bäume → AP-Rule-Lambdas). Trick-Level als AP-Option.
2. **APWorld**: Items, Locations, Optionen, Ziel (Dark Samus/Phaaze), Füllitems, `fill_slot_data`.
3. **Patch-Pfad**: AP-Ergebnis → Corruptovania-Patch-JSON → `MP3Randomizer`. Fremde Items als neutrales „AP-Item“ (Modell + Text) im Spiel.
4. **Client**: Dolphin-Speicher lesen (welche Pickups eingesammelt), Items ins Inventar schreiben, Item-Index im Spielstand persistieren, optional DeathLink.

## 4. Features in Reihenfolge

| # | Feature | Abhängig von |
|---|---|---|
| F1 | Eigener Fork + lauffähige Dev-Umgebung (Corruptovania generiert + exportiert ein Seed lokal) | – |
| F2 | Speicher-Mapping dokumentieren: Inventar-Adressen, Pickup-/Location-Flags, Spielzustand (Ingame/Menü) | F1 |
| F3 | DB-Konverter Corruptovania → AP-Datenstrukturen | F1 |
| F4 | APWorld-Grundgerüst: Items, Locations, Regeln, Ziel; generiert solo-Seed ohne Fehler | F3 |
| F5 | Patch-Pfad: AP-Platzierung → gepatchtes ISO, fremde Items als AP-Platzhalter | F4 |
| F6 | AP-Client: Location-Checks senden | F2 |
| F7 | AP-Client: empfangene Items ins Spiel geben, Wiederaufnahme nach Neustart | F6 |
| F8 | Ende-zu-Ende-Test: 2-Spieler-Multiworld (MP3 + beliebiges Spiel) durchgespielt bis Ziel | F5, F7 |
| F9 | Optionen-Ausbau: Startort, Starting Items, Trick-Level, Energy-Cell-Ziel (nicht im MVP, siehe E3) | F8 |
| F10 | DeathLink, Hinweise im Spiel, Release-Paket | F8 |

## 5. Offene Entscheidungen

| ID | Frage | Vorschlag | Status |
|---|---|---|---|
| E1 | Architektur | **Eigenständige APWorld**, Logik aus Corruptovania-DB konvertiert, Corruptovania nur als Patcher | entschieden 2026-11-23 |
| E2 | Zielplattform/Spielversion | **Nur Dolphin**, nur die Version, die der Patcher heute unterstützt. T01: implizit NTSC-U RM3E01. PAL RM3P01 funktioniert ohne MP3Update/Deflicker. Trilogy geht nicht | entschieden 2026-11-23 |
| E3 | MVP-Umfang | **Nur Item-Shuffle, Standard-Startort, festes Ziel Dark Samus.** Startort, Trick-Level, DeathLink erst in F9/F10 | entschieden 2026-11-23 |
| E4 | Repo-Hosting | **Fork `junkx420/corruptovania`, Arbeitsbranch `archipelago`** (Standardbranch). `main` bleibt Spiegel von Upstream. APWorld liegt im selben Repo unter `apworld/metroidprime3/`, Konverter unter `apworld/tools/` | entschieden 2026-11-23 |
| E5 | Lizenz der APWorld: GPLv3 (wegen abgeleiteter Logikdaten) | GPLv3 | offen |
| E7 | MVP-Region: PAL RM3P01 (vorhandenes ISO, ohne MP3Update) oder NTSC-U RM3E01 (Patcher-Zielversion, ISO fehlt)? | **PAL RM3P01 für den MVP.** NTSC-U nachziehen, sobald ein Dump vorliegt (Adressen anderer Regionen aus Code, nicht live geprüft) | entschieden 2026-11-23 |
| E6 | Client-Basis: AP-`CommonClient` + `dolphin-memory-engine` (wie MP1-APWorld) oder Corruptovania-Connector wiederverwenden? | AP-CommonClient + dolphin-memory-engine, Adressen aus Corruptovania-Connector übernehmen | offen |
