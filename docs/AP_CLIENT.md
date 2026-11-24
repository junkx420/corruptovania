# Metroid Prime 3 Client (T06: Verbindung und Location-Checks)

Stand: 2026-11-24 · Archipelago 0.6.8 · nur **PAL `RM3P01`** (SPEC E7) · Dolphin oder PrimeHack

Der Client liest den Spielspeicher über `dolphin-memory-engine`, erkennt eingesammelte Orte am Flag-Block der aktuellen
Welt (SPEC E8, E12) und meldet sie per `LocationChecks` an den Server. **Items gibt er noch nicht** (T07). Er schreibt in
T06 nichts in den Spielspeicher.

Code: `apworld/metroidprime3/client/`, Tests: `apworld/metroidprime3/test/test_client.py`.

## 1. Start

Voraussetzungen: Archipelago-Klon mit eingebundener APWorld wie in `docs/AP_APWORLD_DEV.md` (Abschnitt 1),
`dolphin-memory-engine >= 1.3.0` in der venv (kommt mit `ModuleUpdate.py --yes` über die Wind-Waker-World mit, sonst
`.venv\Scripts\python.exe -m pip install "dolphin-memory-engine>=1.3.0"`).

1. Dolphin oder PrimeHack starten, gepatchtes PAL-ISO laden (z. B. T16-ISO mit `--ap-mode`).
2. Client starten, entweder im Launcher (**„Metroid Prime 3 Client“**) oder direkt:

   ```powershell
   .venv\Scripts\python.exe Launcher.py "Metroid Prime 3 Client"
   ```

   Ohne GUI, direkt verbunden:

   ```powershell
   .venv\Scripts\python.exe Launcher.py "Metroid Prime 3 Client" -- --nogui --connect localhost:38281 --name Samus
   ```

3. Im Client `/connect <host:port>` eingeben (falls nicht per `--connect`), dann den Slot-Namen.

Reihenfolge egal: Der Client verbindet sich alle 5 s neu mit Dolphin, bis es klappt. Orte, die er vor der
Server-Verbindung erkennt, merkt er vor (`locations_checked`); CommonClient sendet sie beim `Connected` mit.

Lokaler Testserver: Seed erzeugen (`AP_APWORLD_DEV.md`, Abschnitt 2), dann
`.venv\Scripts\python.exe MultiServer.py output\AP_<seed>.zip` (Port 38281).

## 2. Konfiguration

| Option (Kommandozeile) | Standard | Bedeutung |
|---|---|---|
| `--connect host:port`, `--password`, `--name` | – | Server, Passwort, Slot-Name (wie CommonClient) |
| `url` (positional) | – | `archipelago://name:pass@host:port` (Launcher-Links) |
| `--poll-interval s` | `0.5` | Abfrage-Intervall in Sekunden |
| `--no-learning` | aus | Lernmodus ausschalten |
| `--learning-log PFAD` | `<Archipelago>\logs\MP3Client_learning_<Zeit>.jsonl` | Logdatei des Lernmodus |
| `--nogui` | aus | ohne Kivy-Oberfläche |

Befehle im Client:

| Befehl | Wirkung |
|---|---|
| `/dolphin` | Verbindungs- und Spielzustand (ingame, Welt, ItemPercentage, Anzahl erkannter Orte) |
| `/blocks` | gefundene Flag-Blöcke je Welt (Adressen), verworfene Blöcke, Anzahl/Dauer der Suchläufe |
| `/learning [on\|off]` | Lernmodus schalten bzw. Status, Logdatei, Anzahl Einträge/Warnungen |
| `/poll [s]` | Polling-Intervall anzeigen/setzen (0,1–5 s) |
| `/missing`, `/received` … | Standardbefehle von CommonClient |

## 3. Ablauf je Abfrage

1. **Dolphin-Verbindung** (`memory.MemoryAccess`): Hook, Game-ID an `0x80000000` muss `RM3P01` sein. Sonst klare
   Meldung („Falsches Spiel in Dolphin: Game-ID …“), sofort trennen, nichts lesen außer der Game-ID, nichts schreiben;
   neuer Versuch nach 5 s. Die Game-ID wird bei jeder Abfrage erneut geprüft (Spielwechsel im laufenden Emulator).
   Jeder Lese-/Schreibfehler gilt als Verbindungsabbruch: trennen, alles Sitzungsbezogene vergessen, nach 5 s neu.
2. **Zustand** (`game.read_game_state`): ingame ⇔ CPlayer-Zeiger `[[0x805C7570+0x28]+0x2184]` gültig **und** vtable
   `0x80595238` (AP_MEMORY_MAP.md, Abschnitt 6). Im Menü/Laden werden nur diese Zeiger gelesen, sonst nichts; Blöcke,
   Entprellung und Lernmodus werden zurückgesetzt. Ingame: Welt `[0x80680234]+8`, `ItemPercentage` (Slot 21) und
   `PowerBeam.capacity` (Slot 0, „Inventar befüllt“).
3. **Flag-Block** (`flag_block.FlagBlockFinder`, E8): gemerkte Adresse prüfen, bei Abweichung sofort neu suchen,
   sonst höchstens alle 2 s, wenn nichts gefunden. Ein Suchlauf liest MEM1 (24 MiB in 1-MiB-Stücken, ca. 90 ms) und
   findet die Blöcke **aller** Welten auf einmal. Signatur (alles Pflicht):
   - `W−4 = 0xEAEAEAEA`, `W+0 = MLVL-ID`, `W+0x18 = 0x400`;
   - `[W+0x08]` zeigt auf einen Deskriptor mit `"SAVW"` bei +8 und der SAVW-ID der Welt bei +16;
   - `[W+0x10]` zeigt auf das SAVW-Objekt, dessen Liste-1-Länge (`+0x10`) zur Welt passt;
   - plausibel: alle Bytes ab der Liste-1-Länge sind 0.

   Nach dem Lesen der 1024 Byte wird die Signatur noch einmal geprüft (Block könnte inzwischen freigegeben sein).
   SAVW-ID und Liste-1-Länge je Welt stehen in `flag_block.SAVW_INFO` (aus dem PAL-ISO, MLVL `+0x14` und SAVW).
4. **Checks** (`checks`): Bytes aus `location_flags.py` für die aktuelle Welt; ein Ort zählt, wenn sein Byte in
   **2 aufeinanderfolgenden Abfragen** gesetzt ist (Entprellung). AP-ID = `0x4D503300 + Pickup-Index`. Jeder Ort wird
   pro Sitzung höchstens einmal gesendet; vom Server schon als erledigt gemeldete Orte (`checked_locations`) werden
   nicht gesendet, und es werden nur Orte gesendet, die der Server kennt (`server_locations`). Orte früherer Welten stehen
   im Spielstand und werden beim nächsten Besuch erneut gesehen, aber nicht doppelt gesendet.
5. **Lernmodus** (siehe 4).
6. **Item-Vergabe**: `MP3Context.give_items(state)` – Schnittstelle für T07, in T06 leer.

### Annahme zu mehreren Blöcken (T14 prüft live)

Nachauswertung der 22 T10-Snapshots (MEM1) mit dem Client-Code:

- In jedem Snapshot liegen Blöcke **aller 14 Welten mit Orten** gleichzeitig im Speicher, auch nie besuchter. Getrennt
  werden sie über die MLVL-ID.
- „Pirate Homeworld - Command“ hat ab dem Neuladen zwei Blöcke mit gültigem Kopf. Einer (`0x80A11900`) hat die Bytes
  670–1019 gesetzt, obwohl die Welt nur 209 Memory Relays hat: Datenmüll, wird von der Plausibilitätsprüfung verworfen
  (`/blocks` zeigt ihn als „verworfen“).
- Im Snapshot C1 gab es je Welt eine zweite gültige Kopie (`0x811E….`), deren gesetzte Bytes eine Teilmenge des
  Hauptblocks waren. In C2 war sie weg.

**Annahme:** Mehrere gültige, plausible Blöcke derselben Welt werden **ODER-verknüpft** (Byte gesetzt, wenn in
irgendeinem gesetzt). Begründung: Flags werden innerhalb eines Spielstands nur gesetzt, die gesehenen Kopien waren
Teilmengen. Risiko: Ein noch gültiger, liegengebliebener Block eines **anderen** Spielstands könnte Orte melden, die im
geladenen Spielstand nicht eingesammelt sind. Abweichungen zwischen Blöcken schreibt der Lernmodus als
`blocks_disagree` ins Log.

## 4. Lernmodus (E19)

Standardmäßig an. Steigt `ItemPercentage` (jeder Pickup +1), sammelt der Client alle Bytes, die im Block der aktuellen
Welt im Fenster **8 s vor bis 2 s nach** dem Anstieg von 0 auf ≠0 gesprungen sind, und schreibt 2 s nach dem Anstieg eine
JSON-Zeile in die Logdatei. Das Fenster reicht zurück, weil bei SpecialFunction-Orten das Memory Relay zu Beginn der
Sequenz gesetzt werden kann. Der Anstieg zählt nur, wenn das Inventar vorher und nachher befüllt war
(`PowerBeam.capacity > 0`), damit das Befüllen nach dem Laden kein Pickup ist.

Beispiel (eine Zeile, hier umbrochen):

```json
{"kind": "pickup", "time": "2026-11-24T19:25:43.512", "world": "Norion", "world_id": "0x6FB8EF2A9523C343",
 "room": "Docking Hub Alpha", "item_percentage": [1, 2], "blocks": ["0x80A13AA0"],
 "bytes": [{"byte": 8, "value": 1, "time": "2026-11-24T19:25:43.010", "role": "location", "location": 4,
            "location_name": "Norion - Docking Hub Alpha - Pickup (Grapple Lasso)", "room": "Docking Hub Alpha",
            "status": "sicher"},
           {"byte": 118, "value": 1, "time": "…", "role": "unknown", "location": null, "location_name": null,
            "room": null, "status": null}],
 "warnings": ["Byte 118 gesetzt, aber keinem Ort zugeordnet"]}
```

| `kind` | Bedeutung |
|---|---|
| `pickup` | ItemPercentage gestiegen; `bytes` = neu gesetzte Bytes mit Rolle `location` (Ort laut Tabelle), `extra` (`other_bytes` eines Orts) oder `unknown` |
| `location_byte_without_pickup` | Orts-Byte gesetzt, ohne dass ItemPercentage im Fenster gestiegen ist |
| `blocks_disagree` | mehrere gültige Blöcke der Welt mit unterschiedlichem Inhalt (Byte-Liste, Adressen) |

Warnungen (auch im Client-Log): „Byte X gesetzt, aber keinem Ort zugeordnet“ und „Pickup eingesammelt
(ItemPercentage gestiegen) ohne erwartetes Orts-Byte“. Der **Raum** ist nur für Bytes bekannt, die laut Tabelle zu
einem Ort gehören; der aktuelle Raum des Spielers wird nicht gelesen (Adresse unbekannt, AP_MEMORY_MAP.md 7).

Auswertung für T13/Playtests: Jede `pickup`-Zeile ohne Warnung bestätigt einen Ort der Tabelle. Bei `unknown`-Bytes
zusammen mit einem `location`-Byte ist der Ort trotzdem bestätigt (der Block hält auch Story-Relays, z. B. Norion 118).

## 5. Live-Test (2026-11-24)

Aufbau: PrimeHack, AP-gepatchtes PAL-ISO (Pickups zeigen „Archipelago Item“), lokaler `MultiServer.py` mit
MP3-Solo-Seed auf `127.0.0.1:38281`, Client über den Launcher mit `--nogui --connect 127.0.0.1:38281 --name Samus`.
Clock Override wurde nicht ausdrücklich bestätigt.

| Schritt | Ergebnis |
|---|---|
| Verbinden mit bestehendem Spielstand | Ort 4 (Norion, Byte 8) aus dem Spielstand erkannt und gesendet |
| Dolphin zweimal beendet und neu gestartet | „Verbindung verloren“ → „nicht gefunden“ → „kein Spiel“ → neu verbunden, kein Absturz, nichts doppelt |
| Neuer Spielstand, Pickup 1: Valhalla, Docking Bay 5 | Ort 11 am Server; Lernmodus: ItemPercentage 0→1, nur Byte 1 = Ort 11, Block `0x80A20180` |
| Neuer Spielstand, derselbe Pickup nochmal | Lernmodus Byte 1 = Ort 11, **keine** zweite Meldung am Server |
| Weltwechsel Valhalla → Bryyo Fire | „pausiere“ (Laden) → `Ingame: Bryyo - Fire`, neuer Block `0x80A08220` |
| Pickup 2: Bryyo Fire, Main Lift | Ort 17 am Server; Lernmodus: ItemPercentage 1→2, nur Byte 6 = Ort 17 |
| Spielstand neu geladen (ohne Speichern), Main Lift nochmal | Blöcke neu gefunden (Bryyo Fire jetzt `0x80A32AA0`), Ort 17 am Server weiterhin nur einmal |

Alle drei Orts-Bytes stimmen mit `location_flags.py` überein. Auffälligkeiten (für T12/T14):

- **Bryyo Fire Byte 2** wurde nach dem Neuladen ca. 6 s vor dem Main-Lift-Pickup gesetzt, ist keinem Ort zugeordnet
  (Lernmodus-Warnung). Wahrscheinlich ein Story-/Raum-Relay auf dem Weg zum Main Lift, kein Pickup-Byte.
- **Valhalla nach dem Neuladen:** zwei gültige, plausible Blöcke (`0x80A3E7A0`, `0x80BCC120`), die sich in Byte 35
  unterscheiden (`blocks_disagree`). Byte 35 ist kein Orts-Byte, die ODER-Annahme hatte hier also keine Folgen. Es
  zeigt aber, dass nach dem Neuladen eine zweite Kopie mit abweichendem Inhalt existiert; T14 muss klären, welche die
  echte ist.

## 6. Tests

```powershell
$env:AP_TEST_WORLDS = "metroidprime3"
.venv\Scripts\python.exe -m pytest worlds/metroidprime3/test/test_client.py -q
```

Fake-Speicher: `test/fake_memory.py` (MEM1 als `bytearray`, zählt Zugriffe, legt Zustandszeiger und Blöcke an).
Geprüft: Signatursuche (auch an Stückgrenzen, nach Umzug, gedrosselte Neusuche, Kopf-/SAVW-/Plausibilitätsprüfung,
ODER mehrerer Blöcke), falsche Game-ID (kein weiterer Lesezugriff, kein Schreiben), Menü/Laden (nur Zustandszeiger
gelesen, kein Suchlauf), neu gesetztes Byte → genau ein `LocationChecks` mit AP-ID `1297101572` (Ort 4), Weltwechsel
und Neuladen ohne doppelte Checks, Server offline/schon erledigt, Verbindungsabbruch, Lernmodus (unbekanntes Byte,
Byte vor dem Anstieg, Orts-Byte ohne Pickup, Inventar-Befüllung nach dem Laden).

Optional gegen einen echten Speicherabzug (T10, 24 MiB MEM1):
`$env:MP3_MEM1_SNAPSHOT = "<pfad>\D2_mem1.bin"` – erwartet Norion `0x80A13AA0` (Orte 3, 4), Valhalla `0x80A49CC0`
(Ort 11), 14 Welten, den verworfenen PHC-Block.

## 7. Bekannte Lücken

- **Keine Item-Vergabe** (T07). `items_handling = 0b111` ist schon gesetzt (E10), empfangene Items liegen nur in
  `items_received`.
- **Keine Seed-Prüfung** (T18): Der Client meldet die Orte des geladenen Spielstands an jeden Slot, mit dem er
  verbunden ist. Falscher Spielstand → falsche Checks.
- **Mehrere Blöcke**: ODER-Annahme (Abschnitt 3), Prüfung in T14. Live gesehen: nach dem Neuladen zwei abweichende
  Valhalla-Blöcke (Abschnitt 5). Liegt in einer Kopie ein Orts-Byte, das im geladenen Spielstand nicht gesetzt ist,
  sendet der Client einen falschen Check. Ebenso offen: 1 h Dauerbetrieb, Dolphin (nicht nur
  PrimeHack), Clock Override.
- **Raum** des Spielers unbekannt (nur Raum des Orts im Lernmodus).
- **Nur PAL** `RM3P01`. NTSC-U/J werden mit „Falsches Spiel“ abgelehnt.
- **10 SpecialFunction-Orte** stehen in der Tabelle nur als „wahrscheinlich“ (T12); der Lernmodus meldet Abweichungen.
- `requirements.txt` der APWorld (für `dolphin-memory-engine`) fehlt noch (Release-Paket, `archipelago.json` in T05b).
- Dolphin-Zugriffe laufen synchron in der asyncio-Schleife; ein Suchlauf blockiert ca. 0,1 s.
- Kein Tracker-/DeathLink-Teil.
