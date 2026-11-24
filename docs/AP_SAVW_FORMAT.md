# SAVW-Format und Location-Flags (T12)

Stand: 2026-11-24. Nur gelesen, Spieldaten bleiben außerhalb des Repos. Gilt für Metroid Prime 3 Wii PAL `RM3P01`.
NTSC-U ist nicht geprüft. Alles, was nur aus den Daten geschlossen und nicht gemessen ist, steht als **Vermutung** da.

> **Kurzfassung**
> 1. Der 1024-Byte-Flag-Block je Welt (`AP_LIVE_TESTS.md`, Test D) ist der **Zustand der Memory Relays (MRLY)** aus
>    **Liste 1 der SAVW** dieser Welt. Byte `i` gehört zu Eintrag `i` der Liste, Leerplätze zählen mit.
> 2. Ein Pickup setzt kein eigenes Byte. Beim Einsammeln aktiviert er über ein Relay „sein“ Memory Relay
>    (`PCKP –ACQU/ACTN→ SRLY –RLAY/ACTV→ MRLY`). Dieses MRLY schaltet beim Laden den Pickup wieder ab (`ACTV/DCTV → PCKP`).
> 3. Alle drei Messpunkte stimmen: Ort 11 → Byte 1, Ort 3 → Byte 7, Ort 4 → Byte 8.
> 4. Tabelle für alle 99 Orte: `apworld/metroidprime3/location_flags.py`. **89 sicher, 10 wahrscheinlich** (die 10
>    SpecialFunction-Orte), keine Kollision. Originales und gepatchtes ISO (T01-Seed) ergeben byte-identische Tabellen.
> 5. Bei den 10 SpecialFunction-Orten steht **das zweite PCKP** (`percentage_pickup_id`) in der SAVW, **nicht das SPFN**.
>    Ihr Byte kommt vom Memory Relay, das der gemeinsame Auslöser von SPFN und PCKP aktiviert.

## 1. Reproduktion

ISO entpacken (außerhalb des Repos, z. B. neben dem Repo-Ordner):

```powershell
tools\dolphin\Dolphin-x64\DolphinTool.exe extract -i mp3.iso -o pal_extract -g -q
```

Tabelle erzeugen (Repo-Wurzel, venv aus `AP_DEV_SETUP.md`):

```powershell
venv\Scripts\python.exe -I apworld\tools\build_location_flags.py ..\pal_extract
```

Mit `--check` wird nur verglichen (Exit 1 bei Abweichung). Zweimal ausgeführt ergibt die Datei byte-identisch (geprüft,
auch mit verschiedenem `PYTHONHASHSEED`). Ohne `lzokay` (z. B. System-Python) nimmt der Parser einen eingebauten
LZO1X-Entpacker; an 1298 echten Segmenten geprüft, Ergebnis gleich. Laufzeit ca. 1,5 s.

Tests (ohne Spieldaten laufen 6, die 5 Spieldaten-Tests werden übersprungen):

```powershell
$env:MP3_PAL_EXTRACTED = "..\pal_extract"; venv\Scripts\python.exe -m pytest apworld\tools\test_savw_parser.py -v
```

Quellen: Parser `apworld/tools/savw_parser.py`. Patcher-Code `tools/prime3_patcher/MP3Randomizer/MP3Randomizer/`
(`PAK.cs`, `MP3MLVL.cs`, `MP3Area.cs`, `MREANew.cs`, `ScriptLayer.cs`, `ScriptObject.cs`, `Connection.cs`,
`PickupLocations.cs`). Belege zur Laufzeitform aus den T10-Snapshots (PrimeHack, MEM1/MEM2, nicht im Repo).

Alle Zahlen sind Big Endian.

## 2. Container

### 2.1 PAK (Wii)

| Offset | Größe | Inhalt |
|---|---|---|
| `0x00` | `0x40` | Kopf (`PakHeader.cs`) |
| `0x40` | 4 | Anzahl Abschnitte (3) |
| `0x44` | 3 × 8 | je FourCC + Größe: `STRG` (Namen), `RSHD` (Ressourcen), `DATA` |
| `0x80` | … | die Abschnitte hintereinander |

`RSHD`: `u32` Anzahl, je Ressource `u32` komprimiert (0/1), FourCC Typ, `u64` Asset-ID, `u32` Größe, `u32` Offset ab
`DATA`. `STRG`: `u32` Anzahl, je Eintrag C-String, FourCC, `u64` ID. Im PAL-ISO sind alle MLVL, SAVW und MREA unkomprimiert
(Flag 0). Alle 16 Spiel-SAVWs liegen in `Worlds.pak`, die MLVL/MREA in `Metroid1.pak` … `Metroid8.pak`.

### 2.2 MLVL (Version `0x19`, `MP3MLVL.cs`)

| Offset | Inhalt |
|---|---|
| `0x00` | Magic `0xDEAFBABE` |
| `0x04` | Version `0x19` |
| `0x08` | `u64` Weltname (STRG) |
| `0x10` | `u32` temple_key_world_index |
| `0x14` | **`u64` SAVW-ID** |
| `0x1C` | `u64` Skybox |
| `0x24` | `u32` Anzahl Bereiche, dann je Bereich: `u64` Name, 48 B Transform, 24 B Bounding Box, **`u64` MREA-ID**, `u64` interne ID, `u32` n + n × `u16` angrenzende Bereiche, `u32` Docks (je `u32` n + n × 8 B, `u32` m + m × 12 B), C-String interner Name |

Der Bereichs-Index (Reihenfolge in dieser Liste) ist das Feld „Bereich“ in der Instanz-ID.

### 2.3 MREA (Version `0x1E`, `MREANew.cs`)

| Offset | Größe | Inhalt |
|---|---|---|
| `0x00` | 4 | Magic `0xDEADBEEF` |
| `0x04` | 4 | Version `0x1E` |
| `0x08` | 48 | Transform |
| `0x38` | 4 | Anzahl World Models |
| `0x3C` | 4 | Anzahl Skript-Layer |
| `0x40` | 4 | Anzahl Datenabschnitte |
| `0x44` | 4 | Anzahl komprimierter Blöcke |
| `0x48` | 4 | Anzahl Abschnitts-Labels |
| `0x4C` | 20 | Füllung |
| `0x60` | … | je Abschnitt `u32` Größe, auf 32 ausgerichtet; je Block 4 × `u32` (Puffergröße, entpackt, gepackt, Abschnittsanzahl), ausgerichtet; je Label FourCC + `u32` Abschnitts-Index (`SOBJ` = erster Skript-Layer, `DEPS`, `SGEN`, …), ausgerichtet; dann die Blöcke |

Block mit gepackter Größe 0: roh. Sonst stehen `(-gepackt) mod 32` Füllbytes **vor** den Daten, danach Segmente mit
`i16` Länge (negativ = roh), entpackt je höchstens `0x4000` Byte (LZO1X). Ein Block enthält so viele Abschnitte, wie
sein Kopf angibt.

**Skript-Layer** (Abschnitt `SOBJ + n`): 10 Byte Kopf (`SCLY`, Version, Byte 8 = Layer-Nummer), `u32` Anzahl Objekte.
Je Objekt: FourCC Typ, `u16` Größe (ab hier), `u32` Instanz-ID, `u16` Anzahl Verbindungen, je Verbindung FourCC
Zustand, FourCC Nachricht, `u32` Ziel, danach die Properties.

**Instanz-ID** (32 Bit): Bits 31–26 Layer, 25–16 Bereichs-Index, 15–0 lokale ID. `PickupLocations.cs` enthält Layer
(`scly_section`) und die unteren 16 Bit, die volle ID steht in der MREA. Das PCKP trägt die GUID seines SAVW-Eintrags in
den Properties.

**Eigenheiten des gepatchten Spiels** (Corruptovania-Patcher, an `out/t01_IVG2J7OR.iso` gesehen):
- Verbindungsziele werden ohne Layer-Bits zurückgeschrieben (`Connection.export`: `00 | Bereich | ID`). Das Spiel
  findet die Ziele trotzdem (Ort 4 liegt auf Layer 16 und setzte live Byte 8). Der Parser löst Ziele deshalb über die
  unteren 26 Bit auf.
- Entpackte Blöcke werden auf 32 Byte aufgefüllt, ohne die Abschnittsgröße anzupassen.
- Neue Patcher-Objekte haben teils dieselbe Bereich+ID in mehreren Layern. Solche Ziele löst der Parser nur bei exakter
  voller ID auf. Bei keinem der 99 Orte liegt so ein Objekt in der Kette.

## 3. SAVW (Version 6)

| Offset | Größe | Inhalt |
|---|---|---|
| `0x00` | 4 | Magic `0xC001D00D` |
| `0x04` | 4 | Version `6` |
| `0x08` | 4 | Anzahl Bereiche (= Bereiche im MLVL, bei allen 19 SAVWs geprüft) |
| `0x0C` | 4 + n × 20 | **Liste 0**: Cinematics (`CINE`) |
| … | 4 + n × 20 | **Liste 1: Memory Relays (`MRLY`) = Flag-Block** |
| … | 4 + n × 20 | **Liste 2**: Türen (`DOOR`) |
| … | 4 + n × 12 | Scans: `u64` SCAN-ID, `u32` Logbuch-Kategorie |
| … | 4 + 0 | unbekannter Abschnitt, in allen 19 SAVWs leer (Parser bricht bei n > 0 ab) |
| … | 4 + … | Variablen: je C-String + 3 × `u32`, immer `(0, 1, 0)` |
| … | 4 + n × 20 | **Liste 3**: gespeicherte Objekte, darunter alle PCKP |
| Ende | | `0xFF` bis zum Vielfachen von 64 |

Ein Listeneintrag hat 20 Byte: **16 Byte GUID + `u32` volle Instanz-ID**. 20 Nullbytes sind ein **Leerplatz**: Er belegt
einen Index, zählt also beim Byte-Index mit.

Inhalt über alle Welt-SAVWs (Typen aus den MREAs aufgelöst):

| Liste | längste Liste | Einträge |
|---|---|---|
| 0 | 243 | 1401 CINE, 435 leer |
| 1 | 262 | 1338 MRLY, 595 leer |
| 2 | 99 | 545 DOOR, 124 leer |
| 3 | 87 | 110 PCKP, 106 leer, 474 nicht in den Skript-Layern gefunden |

Die nicht gefundenen Einträge in Liste 3 liegen zum größten Teil in Bereich 0 (`universalarea`) auf Layer 58/59, in jeder
Welt gleich. **Vermutung:** Weltübergreifende Objekte und Objekte aus dem `SGEN`-Abschnitt (nicht ausgewertet).

Variablen sind Namen wie `PiratePlanet_GFShip`, `Mii Bobble Head`, `LandingSite_0G_GFPlanet_VistaBridge_A`.
**Vermutung:** Die drei `u32` sind Minimum, Maximum und Startwert.

Die Reihenfolge entspricht den Listen in `retro_data_structures/formats/savw.py` (Cinematic Skips, Memory Relays, Layer
Toggles, Doors, Scans), nur dass MP3 statt Layer Toggles die Türen und am Ende Variablen und Liste 3 hat, und je Eintrag
eine GUID statt einer reinen Instanz-ID.

Vom Spiel gibt es außerdem SAVWs in `FrontEnd.pak` (2) und `UniverseArea.pak` (1). Sie parsen mit demselben Format.

## 4. Laufzeitform

Belege aus den T10-Snapshots (Norion-Block `W = 0x80A13AA0`, D2):

| Offset | Inhalt |
|---|---|
| `W + 0x00` | `u64` MLVL-ID |
| `W + 0x08` | Zeiger auf einen Ressourcen-Deskriptor mit `"SAVW"` und der SAVW-ID der Welt (`0x808C0800` → `… 53415657 … 732E1A63A1122AD3`) |
| `W + 0x0C` | unbekannt (`0x01FD0000`) |
| `W + 0x10` | Zeiger auf das geparste SAVW-Objekt (`0x809886E0`) |
| `W + 0x14` | unbekannt (`0x01FFFFFF`) |
| `W + 0x18` | `0x400` = Anzahl Flags. **Vermutung:** `reserved_vector<bool, 1024>` (Größe, dann Daten) |
| `W + 0x1C` | 1024 Byte, Byte `i` = Memory Relay `i` aus Liste 1 |

Das geparste SAVW-Objekt hält die Listen als Vektoren `(Anzahl, Kapazität, Zeiger)` in Dateireihenfolge:
`+0x00` Bereiche, `+0x04` Liste 0, `+0x10` Liste 1, `+0x1C` Liste 2, `+0x28` Liste 3, `+0x34` Scans,
`+0x40` unbekannt, `+0x4C` Variablen. Norion: 243, 149, 53, 33, 232, 0, 4 Einträge, wie in der Datei.

**Alle gesetzten Bytes aus T10 sind Memory Relays** im Raum, in dem der Spieler war:

| Welt | Byte | Liste-1-Eintrag | Raum | Ursache |
|---|---|---|---|---|
| Valhalla | 1 | MRLY `0x00020039` | `01_abandoned_hangar` | Ort 11 (Messpunkt) |
| Valhalla | 35 | MRLY `0x000201B2` | `01_abandoned_hangar` | schon vor Pickup 1 gesetzt |
| Norion | 1, 6 | MRLY `0x000204E8`, `0x0002039D` | `01_gfplanet_landingsite` | bei Ankunft gesetzt |
| Norion | 7 | MRLY `0x00020403` | `01_gfplanet_landingsite` | Ort 3 (Messpunkt) |
| Norion | 8 | MRLY `0x000202E0` | `01_gfplanet_landingsite` | Ort 4 (Messpunkt) |
| Norion | 118 | MRLY `0x00020534` | `01_gfplanet_landingsite` | zugleich mit Ort 4 gesetzt |
| Norion | 24, 116 | MRLY `0x000800AE`, `0x0008015A` | `0a_gfplanet_venttube` | zwischen C2 und D2 (Spieler im Vent Tube) |

Vorher geprüft und verworfen: Sortierung von Liste 3 nach GUID oder Instanz-ID, Gruppierung nach Bereich, Kombinationen
der Listen, einfache Hashes der GUID. Keine passte zu den drei Messpunkten.

Folge für den Client: Der Block enthält nicht nur Pickup-Flags (Story-Relays, Türen-Logik usw. teilen ihn). Es zählt nur
das Byte aus der Tabelle. Liste 1 ist höchstens 262 Einträge lang, Bytes darüber bleiben 0 (**Vermutung**, nicht live
geprüft). Wo der Zustand der Liste-3-Objekte zur Laufzeit liegt, ist offen; für die Checks wird er nicht gebraucht.

## 5. Zuordnung Ort → Byte

Pro Ort aus `PickupLocations.cs` (1–99, Ort 0 entfällt, E13): Welt über die MREA-ID im MLVL, volle Instanz-ID aus
Layer + lokaler ID in der MREA, Verbindungs-Graph des Raums, dann:

**Pickup-Orte (89):** Kandidaten sind die MRLY, die vom PCKP über höchstens 3 Verbindungen mit Nachricht `ACTV`
erreicht werden. „Sein“ MRLY ist das, das zusätzlich beim Laden den PCKP abschaltet (`ACTV/DCTV → PCKP`). Bei allen 89
gibt es genau eins, es wird nur aus der Kette des Pickups aktiviert, und es liegt immer in Tiefe 2
(`ACQU/ACTN → SRLY`, `RLAY/ACTV → MRLY`). Status **sicher**. Bei 4 Orten setzt derselbe Vorgang weitere Bytes
(`other_bytes` in der Tabelle): 64 (+231), 77 (+220), 87 (+5, +187), 95 (+108).

**SpecialFunction-Orte (10):** SPFN und zweites PCKP haben keine eigenen Ausgänge. Ein gemeinsamer Auslöser
(Relay `SRLY`, meist nach einer Animation `ACKF`) schickt `ACTN` an das SPFN und `IM00` an das PCKP. Gesucht wird das
MRLY, das dieser Auslöser (oder bis zu zwei Stufen davor) mit `ACTV` aktiviert und das nur von dort aktiviert wird.
Es schaltet beim Laden nicht das SPFN ab, sondern startet ein Aufbau-Relay (`ACTV/ACTN → SRLY`). Status **wahrscheinlich**:
Muster eindeutig, aber kein Rückverweis auf SPFN/PCKP und nicht live gemessen.

| Ort | Welt | SPFN | zweites PCKP (in SAVW-Liste 3, Index) | MRLY | Byte | Hinweis |
|---|---|---|---|---|---|---|
| 9 | Norion | `0x000F01EE` | `0x000F026C` (30) | `0x000F01F1` | 53 | |
| 34 | Bryyo - Reptilicus | `0x000E032B` | `0x000E04BA` (69) | `0x000E031B` | 68 | Byte 54 wird im selben Moment gesetzt |
| 42 | Bryyo - Reptilicus | `0x00210127` | `0x002103AB` (70) | `0x0021014C` | 109 | |
| 43 | Bryyo - Reptilicus | `0x102100CB` | `0x10210778` (73) | `0x0021036B` | 107 | MRLY hängt 2 Stufen vor dem Auslöser (Start der Sequenz) |
| 62 | SkyTown, Elysia - Main | `0x00180165` | `0x001802E5` (80) | `0x00180045` | 81 | |
| 70 | SkyTown, Elysia - Pod | `0x0010035F` | `0x00100426` (45) | `0x0010019C` | 42 | |
| 73 | SkyTown, Elysia - Pod | `0x001C02F3` | `0x001C01DE` (52) | `0x001C00EA` | 81 | MRLY hängt 1 Stufe vor dem Auslöser |
| 79 | Pirate Homeworld - Research | `0x00070185` | `0x0007003A` (72) | `0x0007012B` | 45 | Byte 176 wird im selben Moment gesetzt |
| 89 | Pirate Homeworld - Command | `0x000502A6` | `0x0005034A` (30) | `0x0005029D` | 10 | |
| 93 | Pirate Homeworld - Mines | `0x0003002B` | `0x000300F4` (33) | `0x0003002E` | 1 | |

Bei 34 und 79 aktiviert der Auslöser zwei MRLY, die nur von dort aktiviert werden. Gewählt ist das mit dem Lade-Muster
`ACTV/ACTN → SRLY` wie bei den anderen acht. Für die Erkennung ist die Wahl egal, beide Bytes werden zugleich gesetzt.

**Prüfungen im Generator:** jedes Orts-Objekt existiert mit passendem Bereich und Layer, genau ein Objekt des Orts steht
in Liste 3, kein Byte wird von zwei Orten derselben Welt benutzt. Bei Verletzung bricht der Generator ab bzw. markiert
den Ort als `unsicher` (kommt derzeit nicht vor).

**Gilt für alle Seeds (E12):** Der Patcher ändert Item-Properties und löscht bzw. ergänzt Cutscene-Objekte, die Ketten
Pickup → Relay → MRLY bleiben. Die Tabelle aus dem gepatchten T01-ISO ist byte-identisch zur Tabelle aus dem Original.
**Vermutung** für Seeds mit anderen Items: Progressive Items und Main-required-Varianten fügen nur Verbindungen hinzu
(`PickupPatches.cs:109-281`), das ändert die gewählten MRLY nicht. Nicht an einem zweiten Seed geprüft.

## 6. Offene Punkte

1. **Live-Stichprobe (T13):** vor allem die 10 SpecialFunction-Orte (Status „wahrscheinlich“) und ein Ort mit
   `other_bytes`. Die 89 Pickup-Orte folgen demselben Muster wie die drei Messpunkte.
2. Bedeutung von `W + 0x0C`, `W + 0x14`, des leeren Abschnitts nach den Scans und der drei `u32` je Variable.
3. Wo der Zustand von Liste 3 (PCKP, GUID) zur Laufzeit liegt, und was die zweite Kopie des Blocks in MEM1 ist
   (`AP_LIVE_TESTS.md`, Test D).
4. NTSC-U `RM3E01`: Format vermutlich gleich, Asset-IDs und Listen nicht geprüft.
