# SPEC – Metroid Prime 3 Archipelago (Entwurf)

Stand: 2026-11-23 · Status: **E1–E4, E7–E16 entschieden (E11 unter Vorbehalt T15); E5, E6 offen**

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
4. **Client**: Flag-Block der Welt lesen (Location-Checks, E8), Items per Soll/Ist-Abgleich ins Inventar schreiben (E9, E11), Seed-Kennung prüfen (T18), optional DeathLink.

## 3a. Arbeitsregeln für Worker

- Gearbeitet wird auf Branch `archipelago`, Remote `origin` = `junkx420/corruptovania`. `upstream` = Original-Repo; nie dorthin pushen.
- Jeder Worker committet nur die Dateien, die ihm freigegeben sind, und pusht am Ende. Vorher `git pull --rebase origin archipelago` ausführen. Konflikte in STATUS.md lösen, ohne fremde Zeilen zu ändern.
- Nie ins Repo: ISOs, Spieldateien, Dolphin, persönliche Pfade, Builds (`build/`, `venv/`).
- Die APWorld darf zur Laufzeit nicht von Randovania abhängen. Der Konverter erzeugt eigenständige Python-Daten.

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
| E2 | Zielplattform/Spielversion | **Nur Dolphin**, nur die Version, die der Patcher heute unterstützt. T01: implizit NTSC-U RM3E01. PAL RM3P01 funktioniert ohne MP3Update/Deflicker. Trilogy geht nicht. **PrimeHack** (Dolphin-Fork mit Maus-Steuerung) gilt als unterstützter Emulator, wird ab T10 zum Testen genutzt | entschieden 2026-11-23 |
| E3 | MVP-Umfang | **Nur Item-Shuffle, Standard-Startort, festes Ziel Dark Samus.** Startort, Trick-Level, DeathLink erst in F9/F10 | entschieden 2026-11-23 |
| E4 | Repo-Hosting | **Fork `junkx420/corruptovania`, Arbeitsbranch `archipelago`** (Standardbranch). `main` bleibt Spiegel von Upstream. APWorld liegt im selben Repo unter `apworld/metroidprime3/`, Konverter unter `apworld/tools/` | entschieden 2026-11-23 |
| E5 | Lizenz der APWorld: GPLv3 (wegen abgeleiteter Logikdaten) | GPLv3 | offen |
| E7 | MVP-Region: PAL RM3P01 (vorhandenes ISO, ohne MP3Update) oder NTSC-U RM3E01 (Patcher-Zielversion, ISO fehlt)? | **PAL RM3P01 für den MVP.** NTSC-U nachziehen, sobald ein Dump vorliegt (Adressen anderer Regionen aus Code, nicht live geprüft) | entschieden 2026-11-23 |
| E6 | Client-Basis: AP-`CommonClient` + `dolphin-memory-engine` (wie MP1-APWorld) oder Corruptovania-Connector wiederverwenden? | AP-CommonClient + dolphin-memory-engine, Adressen aus Corruptovania-Connector übernehmen | offen |
| E8 | Location-Checks | Flag-Block der Welt (1024 Byte im Heap): Signatur-Suche nach Laden/Weltwechsel, Adresse merken, Signatur bei jeder Abfrage prüfen. Kein DOL-Hook im MVP | angenommen 2026-11-23 (F-01) |
| E9 | Item-Vergabe | Direktschreiben von Anzahl/Kapazität in `PS + 0x54 + slot*0xC`, nur wenn Spieler ingame (CPlayer-vtable) und `PowerBeam.capacity > 0` | angenommen 2026-11-23 (F-01) |
| E10 | Remote-Items | Alle 99 Orte geben lokal nichts (`item_type FF FF FF FF`, 0/0). Auch eigene Items kommen vom Server, `items_handling = 0b111` | angenommen 2026-11-23 (F-01) |
| E11 | Empfangene Items | Kein gespeicherter Index. Soll-Kapazität je Slot = Startitems aus `slot_data` + Wirkung aller empfangenen Items, nur anheben. Hängt an T15 . T11: Kapazitäten werden im Spielstand mit begrenzter Bitbreite gespeichert (Suit-Max 11 → 3 nach Laden); Soll-Werte müssen im gültigen Bereich je Slot liegen | angenommen unter Vorbehalt T15 |
| E12 | Byte↔Ort-Tabelle | Statisch aus SAVW + MREA erzeugt, gilt für alle Seeds, eigenständige Python-Daten, live per Stichprobe geprüft (T12, T13) | angenommen 2026-11-23 (F-01) |
| E13 | Anzahl Orte | 99 Orte (Pickup-Index 1–99), Ort 0 entfällt | angenommen 2026-11-23 (F-01) |
| E14 | Pickup-Darstellung | Fremd-Pickups: vorhandenes neutrales Modell, ein gemeinsamer Text „Archipelago-Item“. Eigene Pickups zeigen das echte Item. Texte je Ort nach dem MVP | angenommen 2026-11-23 (F-01) |
| E15 | Missile-required | Im AP-Patch aus, die Launcher-Sperre bildet der Client ab | angenommen 2026-11-23 (F-01) |
| E16 | DOL-Hook | Nur falls T11 ein Item findet, das per Direktschreiben nicht wirkt | angenommen; T11: Bedingung nicht erfüllt, kein Hook im MVP |
| E17 | Ort 0 / Pool-Größe | Ort 0 (nie gepatcht) ist laut DB erst nach „Aurora Unit 313“ erreichbar, sein Vanilla-Item Hypermode ist für die Logik nutzlos. **Hypermode kommt in den AP-Pool, dafür eine Missile Expansion raus; Pool bleibt 99.** Ort 0 ist in AP keine Location | revidiert 2026-11-24 (F-02) |
| E18 | „before event X“ | Gilt in der Logik als erfüllt. Gefährliche Events (alle, die negiert vorkommen) zählen logisch erst, wenn der Rückweg vom Event-Knoten zum Schiff mit vorhandenen Items gesichert ist (`escape_requirement`, vom Konverter vorberechnet). Zu frühes Auslösen behebt der Spieler durch Neuladen. Kein Patcher-Eingriff im MVP | angenommen 2026-11-24 (F-02) |
