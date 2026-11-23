# AP-Live-Tests PAL: Item-Vergabe, Slot 47, Slot 68, Pickup-Zustand (T10)

Stand: 2026-11-23. Liefert Fakten für die Architekturfrage F-01 in `STATUS.md`.
Grundlage: `AP_MEMORY_MAP.md` (Inventar `[[0x80680234]+0x24]+0x54+slot*0xC`, je Slot `u32 Anzahl, u32 Max, u32 ?`, Big Endian)
und `AP_PATCHER_NOTES.md` (Slots, Hash-Tabelle). Alle Adressen sind PAL `RM3P01`.

Legende der Messquelle: **[D]** = Dolphin 2609b (vor dem Absturz), **[P]** = PrimeHack. **Alle Zahlen in den Tests A bis D stammen von [P].**
Nur die Vorabmessung unten ist [D].

## Testumgebung

| Punkt | Dolphin [D] | PrimeHack [P] |
|---|---|---|
| Emulator, Version | Dolphin 2609b, JIT64, D3D11 (`AP_DEV_SETUP.md` Abschnitt 6) | PrimeHack v1.0.9 (Ordner `PrimeHack.v1.0.9`, Nutzerdaten in `%APPDATA%\Dolphin Emulator`) |
| CPU Clock Override | Standard (aus), vom Nutzer bestätigt | **an, 500 %** (`OverclockEnable = True`, `Overclock = 5.0`) |
| Disc Speed („Emulate Disc Speed“) | Standard | **aus** (vom Nutzer abgeschaltet) |
| Spiel-ISO | `out/t01_IVG2J7OR.iso` (Seed IVG2J7OR, Starter Preset), außerhalb des Repos | gleiche ISO. In PrimeHack wurde ein neues Spiel angelegt, Start Valhalla, Docking Bay 5 |
| Erkennung der Seed-ISO | – | Startinventar stimmt: PowerBeam (0), ChargeUpgrade (3), Bomb (10), CombatVisor (11), ScanVisor (12), DoubleJump (15), MorphBall (32) je 1/1 |
| Messwerkzeug | dolphin-memory-engine 1.3.0 (Python 3.12), Wegwerf-Skripte im Scratchpad außerhalb des Repos | gleich. Snapshots (MEM1 24 MB + MEM2 64 MB) dauern 0,2 s und liegen nicht im Repo |
| Spielstand | Wegwerf-Save (vom Nutzer bestätigt) | Neues Profil, Wegwerf-Save |

Verbindung zu PrimeHack bestätigt: Game-ID `RM3P01`, CPlayerState-Basis `PS = 0x80995B20` (gleich wie im Dolphin), Welt, CPlayer-vtable wie in
`AP_MEMORY_MAP.md`. Der Zeiger `[0x80680234]` (CGameState) ändert sich beim Laden (`0x80998DC0`, `0x80A234E0`, `0x80A10880`), `PS` blieb gleich.

## Protokoll

| Zeit (2026-11-23) | Ereignis |
|---|---|
| ca. 20:00 | Backup des Wii-Saves aus Dolphin [D] (Scratchpad, nicht im Repo). Der Save im alten Dolphin war von 18:56 (T01/T02), nicht von dieser Sitzung |
| 20:10–20:11 | [D] Test C/D **Schritt 1**: Bryyo Fire, Main Lift, Pickup 17 (Missile Expansion laut Seed). Snapshot 1 und Slots 62–69 gelesen, Logger gestartet (20:11:19, alle 0,25 s 70 Slots) |
| zwischen 20:11 und 20:14 | **Absturz von Dolphin 2609b [D]** bei **Test C/D, zwischen Schritt 1 und Schritt 2**. Der Nutzer stand vor dem Pickup. Es lief **kein Schreibzugriff**, in der ganzen [D]-Sitzung wurde nichts geschrieben. Davor nur Lesen: ein Snapshot (88 MB in 0,2 s) und 4× pro Sekunde 70 Slots. Einstellungen: Standard, **ohne** Clock Override (laut Nutzer), Disc Speed Standard. `dolphin.log` ist leer (0 Byte). Ursache unbekannt. Ein Zusammenhang mit dem Lesen per Memory Engine ist nicht auszuschließen und nicht belegt |
| 20:14:27 | PrimeHack [P] gestartet. Der alte Logger wurde beendet |
| ca. 20:22–20:25 | [P] Neues Spiel, Test C/D Schritt 1 und 2 (Pickup 1, Valhalla) |
| 20:25:27 | Pickup 1 eingesammelt |
| 20:29–20:30 | Speichern, Neuladen (Reset), Snapshot 4 |
| 20:35:29 | Pickup 2 (Norion, Docking Hub Alpha) eingesammelt |
| 20:36:43–20:41:01 | Test A: Schreibzugriffe Slot 4, 7, 20, 1 |
| ca. 20:45–20:46 | Speichern, Neuladen (Snapshots C1 vor, C2 nach dem Laden) |
| 20:47:20–20:51:27 | Test B: Schreibzugriffe Slot 47 (zwei Durchgänge), Probe 47/43/53/54, Persistenz-Test, Rücksetzen |
| 20:54:07 | Pickup 3 (Norion, Docking Hub Alpha, Missile Expansion) eingesammelt |

**Kein Absturz mit PrimeHack [P]**, auch nicht bei den Schreibzugriffen. Kein [P]-Test lief ohne die 500 % Clock Override.

## Vorabmessung [D], zur Bestätigung mit [P] wiederholt

Wurde vor dem Absturz mit [D] gelesen (Spielstand Norion/Bryyo, drei Pickups, kein Missile Launcher). Mit [P] im frischen Spiel bestätigt, soweit unten
angegeben.

| Slot | Name | Anzahl/Max [D] | [P] bestätigt |
|---|---|---|---|
| 21 | ItemPercentage | 3/103 | ja, 0/100 bei Spielstart, +1 je Pickup |
| 47, 48, 49, 53–61 | frei bzw. CannonBall, ActivateMorphballBoost | je 0/1 | ja (frisches Spiel). Nach dem Laden aus dem Save: 47, 48, 49 = 0/0, 53–61 bleiben 0/1 |
| 52 | EnergyCellsUsed | 0/9 | ja |
| 43 | (frei) | 0/0 | ja |
| 68 | Stat_TinCanHighScore | 10/10 (zwei Expansions ohne Launcher) | ja, 5 je gesperrter Missile Expansion (Test C) |
| 69 | Stat_TinCanCurrentScore | 0/0 | ja, 0/0 |

## Test A: Item-Vergabe durch direktes Inventar-Schreiben

**Aufbau:** [P], Norion, Docking Hub Alpha, ingame. Je Item ein Schreibzugriff mit `dolphin_memory_engine.write_bytes` auf `PS + 0x54 + slot*0xC`
(Anzahl und Max als zwei `u32`). Danach 2,5 s Lesen (Wert blieb gleich), der Nutzer prüfte im Spiel Funktion, HUD und Pausenmenü. Am Ende speichern und
neu laden (Reset, Continue Game), danach Speicher lesen und im Spiel prüfen. Die Tests liefen in dieser Reihenfolge, die Items blieben aktiv.

| Item | Slot (Adresse) | Geschrieben (Anzahl/Max), vorher 0/0 | Funktioniert | HUD | Pausenmenü | Übersteht Speichern + Neuladen |
|---|---|---|---|---|---|---|
| Missile (Expansion: Max erhöht) | 4 (`0x80995BA4`) | 5/5 | ja (Schuss, Anzahl 5 → 4, 3, 2, 1, 0; füllt sich auf 5/5) | ja | ja | ja (Speicher 4/5 nach Reload, Max 5 erhalten) |
| Grapple Lasso | 7 (`0x80995BC8`) | 1/1 | ja | ja | ja | ja (Speicher 1/1 nach Reload) |
| Energy Tank | 20 (`0x80995C64`) | 1/1 | ja (leerer Tank erscheint, füllt sich laut Nutzer) | ja (leerer Tank) | ja (vom Nutzer als „denke schon“ gemeldet, unsicher) | ja (Speicher 1/1 nach Reload) |
| Beam-Upgrade Plasma Beam | 1 (`0x80995B80`) | 1/1 | ja (MP3 hat feste Beams, Wechsel nur zum Hyperbeam) | ja | ja | ja (Speicher 1/1 nach Reload) |

Alle vier nach dem Neuladen laut Nutzer im Spiel noch vorhanden.

**Seiteneffekte und Beobachtungen:**
- ItemPercentage (Slot 21) blieb bei allen Schreibzugriffen unverändert (2/102). Er steigt nur durch echte Pickups.
- Missile (Slot 4) funktioniert ohne Missile-Launcher-Item. **Der Schreibzugriff auf Slot 4 löst die Umbuchung der gesperrten Raketen aus:** Beim nächsten
  Missile-Pickup (20:54:07, Pickup 3) wurde Slot 68 von 5/5 auf 0/0 gesetzt und Slot 4 von 5/5 auf **15/15** (5 aus Slot 68 plus 5 vom Pickup plus die
  geschriebenen 5). Das ist der gleiche Mechanismus, der beim echten Aufnehmen des Launchers die gesperrten Raketen freigeben würde. Ohne den Schreibzugriff
  hätte Slot 68 nach der zweiten Expansion 10/10 gezeigt (wie [D] vor dem Absturz).
- Stat_DataSaves (Slot 65) steigt bei jedem Speichern (1, 3, 4 gelesen).
- Kein Absturz, keine Fehlanzeige im HUD, kein Zurücksetzen der Werte durch das Spiel.

**Ergebnis:** Missile, Grapple Lasso, Energy Tank und Plasma Beam lassen sich durch direktes Schreiben in den Inventar-Slot vergeben und wirken sofort, zeigen
sich in HUD und Pausenmenü und bleiben nach Speichern und Neuladen erhalten.

## Test B: Slot 47

**Aufbau:** [P], Norion, ingame, Slot 47 = `PS + 0x288` = `0x80995DA8`. Durchgang 1: nur die Anzahl (erste vier Byte) schreiben, Max blieb 0. Durchgang 2: Anzahl und
Max auf denselben Wert. Jeweils sofort, nach 0,5 s und nach 3 s gelesen. Probe mit 4 ms Abtastung (Slots 47, 43, 53, 54, je 7/7). Persistenz: Slot 47 auf 0/65535,
dazu Slot 43 = 65535/65535, Slot 53 = 1000/1000, Slot 54 = 7/7, speichern, neu laden, lesen.

**Tabelle Schreibwert → Lesewert** (Anzahl/Max):

| Geschrieben (Anzahl) | Durchgang 1, Max=0: sofort → nach 0,5 s und 3 s | Durchgang 2, Max=Wert: sofort → nach 0,5 s und 3 s | Nach Speichern + Neuladen |
|---|---|---|---|
| 1 | 1/0 → 0/0 | 1/1 → 0/1 | nicht einzeln geprüft (live immer 0) |
| 2 | 2/0 → 0/0 | 2/2 → 0/2 | nicht einzeln geprüft (live immer 0) |
| 50 | 50/0 → 0/0 | 50/50 → 0/50 | nicht einzeln geprüft (live immer 0) |
| 255 | 255/0 → 0/0 | 255/255 → 0/255 | nicht einzeln geprüft (live immer 0) |
| 1000 | 1000/0 → 0/0 | 1000/1000 → 0/1000 | nicht einzeln geprüft (live immer 0) |
| 65535 | 65535/0 → 0/0 | 65535/65535 → 0/65535 | **0/0** (gespeichert mit 0/65535, da die Anzahl live auf 0 fiel) |

- **Die Anzahl in Slot 47 setzt das Spiel nach etwa 18 ms (ein Frame) auf 0 zurück**, auch wenn das Max gleich hoch ist. Gemessen mit 4-ms-Abtastung:
  Wert 7 stand bei 0 ms, bei 18 ms stand 0.
- **Das Max in Slot 47 bleibt live bei jedem Wert bis 65535 stehen** (keine Klemmung gesehen). Nach Speichern und Neuladen steht Max wieder auf 0.
- Nach dem Laden aus dem Save steht Slot 47 immer auf 0/0, im frischen Spiel stand er auf 0/1.
- Nachbarn 46 und 48 blieben 0/0, ItemPercentage blieb 2/102. Kein Absturz, kein Seiteneffekt, den der Nutzer gemeldet hätte.

**Nebenmessung** (gleiche Probe, zum Vergleich mit den anderen freien Slots):

| Slot | Geschrieben | Nach 1 s live | Nach Speichern + Neuladen |
|---|---|---|---|
| 43 (`0x80995D78`) | 7/7, dann 65535/65535 | bleibt (7/7, 65535/65535) | **1/1** |
| 53 (`0x80995DF0`) | 7/7, dann 1000/1000 | bleibt | **0/0** |
| 54 (`0x80995DFC`) | 7/7 | bleibt | **1/1** |

Ein Bit je Slot würde das Muster erklären (7 und 65535 sind ungerade → 1, 1000 ist gerade → 0). **Das ist eine Vermutung**, ein weiterer Wert (z. B. 2 oder 3) wurde
nicht geschrieben. Die Testslots wurden danach auf ihre Ausgangswerte gesetzt (43 = 0/0, 53 und 54 = 0/1).

**Ergebnis:** Eine Anzahl in Slot 47 hält sich keinen Frame, und das Max von Slot 47 übersteht das Neuladen nicht, Slot 47 kann also weder live noch über den Save Werte tragen.

## Test C: Slot 68 und 69

**Aufbau:** [P], Valhalla, Docking Bay 5. Slots 68 und 69 an drei Zeitpunkten gelesen. Der Pickup war eine Missile Expansion (Seed-Ort „Pickup (Energy Cell)“ in Docking Bay 5,
Pickup 11). Der Spieler hatte keinen Missile Launcher (Slot 4 = 0/0), die Expansion war also „gesperrt“.

| Zeitpunkt | Slot 68 | Slot 69 | Slot 4 (Missile) | Slot 21 (ItemPercentage) |
|---|---|---|---|---|
| 1. Im Spiel (nach Spielstart) | 0/0 | 0/0 | 0/0 | 0/100 |
| 2. Vor dem Einsammeln (20:24, Snapshot 1) | 0/0 | 0/0 | 0/0 | 0/100 |
| 3. Nach dem Einsammeln (20:25:27) | **5/5** | 0/0 | 0/0 | 1/101 |

Slot 68 und Slot 21 änderten sich im selben Logger-Takt. Zum Vergleich [D] vor dem Absturz: Slot 68 = 10/10 bei zwei gesperrten Expansions.
Slot 69 (Ship Missile Expansion) wurde nicht gemessen, es gab keinen Ship-Missile-Pickup.

**Widerspruch geklärt:** `AP_PATCHER_NOTES.md` (Abschnitt 2.5) hat recht: Die Ladung einer gesperrten Missile Expansion liegt in **Slot 68** (5 je Expansion).
`AP_MEMORY_MAP.md` (Zeile 117 und 189–190: „`TemporaryMissile` nicht im Speicher“) ist damit überholt. Slot 68 wird beim Aufnehmen einer Missile Expansion nach Slot 4
umgebucht, sobald Slot 4 nicht mehr 0 ist (gemessen in Test A, 20:54:07).

**Ergebnis:** Slot 68 steigt bei einer gesperrten Missile Expansion um 5, Slot 69 bleibt 0/0.

## Test D: Pickup-Zustand im Speicher

**Aufbau:** [P]. Snapshots von MEM1 und MEM2 (`0x80000000`–`0x817FFFFF` und `0x90000000`–`0x93FFFFFF`), jeweils zwei direkt hintereinander (3 s Abstand) als Rauschpaar:

| Name | Zeitpunkt | Ort |
|---|---|---|
| A1, A1b | vor Pickup 1 | Valhalla, Docking Bay 5 |
| A2, A2b | nach Pickup 1 (Missile Expansion) | Valhalla, Docking Bay 5 |
| A3, A3b | nach Flug Norion und zurück | Valhalla, Docking Bay 5 |
| A4, A4b | nach Speichern und Neuladen | Valhalla |
| B1, B1b / B2, B2b | vor / nach Pickup 2 (Screw Attack, Pickup 4) | Norion, Docking Hub Alpha |
| C1 / C2 | vor / nach Speichern und Neuladen (Test A) | Norion |
| D1, D1b / D2, D2b | vor / nach Pickup 3 (Missile Expansion, Pickup 3) | Norion, Docking Hub Alpha |

„Raum verlassen und zurückkommen“ war in Docking Bay 5 nicht möglich, deshalb der Flug nach Norion und zurück (lädt die Welt neu).

**Störquelle PrimeHack und Rauschen:** Im Leerlauf ändern sich zwischen zwei Snapshots im Abstand von 3 s **124 528 Wörter in MEM1 und 36 549 in MEM2** (A1 gegen A1b).
Wie viel davon PrimeHack-Kamera- und Steuerwerte sind, ist nicht getrennt worden. Das Rauschpaar wurde deshalb als Filter benutzt (Adressen, die sich im Ruhepaar ändern, zählen nicht).
Der gefundene Block (unten) war in allen Ruhepaaren (A1/A1b, B1/B1b, D1/D1b, D2/D2b) unverändert. PrimeHack-Schreibzugriffe treffen ihn nicht.

**Ausgeschlossen:**
- **ItemPercentage** (Slot 21): steigt bei jedem Pickup, sagt aber nicht welcher.
- **Rohes Diff A1 → A2:** zu laut. 1 433 Wörter in MEM1 ändern sich stabil (A2 = A3 = A4), davon ist der Großteil freigegebener Heap und statische Daten, 0 in MEM2.
- **Zeigerketten ab `[0x80680234]`** (Tiefe 4, 39 stabile Kandidaten): nur Ressourcen-Objekte (`STRG`-Texte) und Allokator-Reste.
- **Save-Datei `save.bin`** (65 536 Byte, bitgepackt mit Prüfsumme): nicht entschlüsselt.
- Einzelbit-Änderungen im Speicher: 573 Treffer in MEM1, überwiegend Heap- und Allokator-Rauschen.

**Gefunden (Suche nach der Welt-ID als 8 Byte im Speicher, 37 Treffer. Bei 26 davon im Heap und Umfeld geprüft änderte sich nur einer um Pickup 1, die übrigen Treffer wurden nicht ausgewertet):** Pro Welt gibt es einen Heap-Block mit diesem Aufbau
(Adressen am Beispiel Valhalla `W = 0x80A1FD40`):

| Offset | Inhalt |
|---|---|
| `W − 4` | `0xEAEAEAEA` (Wächterwert des Allokators) |
| `W + 0x00` | MLVL-Asset-ID der Welt als `u64` (Valhalla `0xC133F919C108BDF9`, Norion `0x6FB8EF2A9523C343`) |
| `W + 0x18` | `0x00000400` (Größe) |
| `W + 0x1C` … `W + 0x41B` | **1024 Byte Flags**, im Spiel nur die Werte 0 oder 1 gesehen. Im Folgenden Byte-Index ab `W + 0x1C` |

Der Block liegt im Heap und zieht um: Valhalla `0x80A1FD40` vor dem ersten Laden, `0x80A49CC0` danach. Er wird über die Welt-ID plus `0x400` bei `+0x18` plus `0xEAEAEAEA` bei `−4` gefunden.
In MEM1 gibt es ein zweites Exemplar mit gleichem Inhalt (Valhalla `0x811ED3C0`), Zweck unbekannt.

**Messwerte, Pickup → geändertes Byte** (im Block sonst keine Änderung):

| Pickup (Ort) | Welt, Block `W` | Byte-Index vor → nach | Adresse | Übersteht |
|---|---|---|---|---|
| 11, Docking Bay 5, Missile Expansion (Seed) | Valhalla, `0x80A1FD40` | 1: `0x00` → `0x01` | `0x80A1FD5D` | Planetenwechsel ja, Speichern + Neuladen ja (Block dabei umgezogen nach `0x80A49CC0`, Inhalt gleich) |
| 4, Docking Hub Alpha, Grapple-Lasso-Ort (Seed: Screw Attack) | Norion, `0x80A13AA0` | 8: `0x00` → `0x01` | `0x80A13AC4` | Speichern + Neuladen ja (C1 → C2, Block blieb an derselben Adresse, Inhalt gleich) |
| 3, Docking Hub Alpha, Missile Expansion | Norion, `0x80A13AA0` | 7: `0x00` → `0x01` | `0x80A13AC3` | nicht geprüft |

- Jeder der drei Pickups hat **genau ein** neues Byte im 0x460 Byte großen Block gesetzt. Im Leerlauf, beim Planetenwechsel und beim Neuladen ändert sich nur der Zeiger-Header.
- Die beiden Pickups im selben Raum (Docking Hub Alpha, Pickup 3 und 4) haben **benachbarte** Bytes (7 und 8). Das passt zu „Byte-Index = Pickup-Nummer + 4“ für Norion, aber nur zwei Punkte belegen das.
  In Valhalla liegt Pickup 11 auf Byte 1, die Verschiebung ist also je Welt verschieden.
- **Der Block hält auch andere Zustände:** Norion hatte schon vor Pickup 2 die Bytes 1 und 6 gesetzt, und zwischen Pickup 2 und dem Speichern kamen die Bytes 24, 116 und 118 dazu
  (der Nutzer hat in der Zeit unter anderem Grapple Lasso und Beam ausprobiert). Das Byte eines Pickups ist also nicht das einzige gesetzte Byte, und die Zuordnung eines Byte zu einem Ort ist nicht
  aus dem Block allein ablesbar.

**Zweiter Pickup in anderer Welt/Raum, gleiches Muster?** Ja: Valhalla (Pickup 11) und Norion (Pickups 3 und 4) setzen jeweils genau ein Byte im gleichen Blocktyp.

**Ergebnis:** Der Zustand eines eingesammelten Pickups wird als ein Byte im 1024-Byte-Flag-Block der jeweiligen Welt (gefunden über Welt-ID + `0x400` + `0xEAEAEAEA`) gespeichert,
bestätigt an drei Pickups in zwei Welten, wobei die Zuordnung Byte ↔ Ort (und die Persistenz von Pickup 3) offen ist.

## Folgerung für F-01

Direktes Schreiben in den Inventar-Slot (Variante c) funktioniert für Missile (Slot 4), Grapple Lasso (Slot 7), Energy Tank (Slot 20) und Plasma Beam (Slot 1): Fähigkeit, HUD und Pausenmenü reagieren sofort, die Werte
überstehen Speichern und Neuladen, ItemPercentage ändert sich dabei nicht, und ein Schreibzugriff auf Slot 4 löst beim nächsten Missile-Pickup die Umbuchung von Slot 68 nach Slot 4 aus.
Slot 47 trägt keinen Marker: Das Spiel setzt seine Anzahl nach etwa 18 ms auf 0, sein Max (live bis 65535 stabil) ist nach dem Neuladen wieder 0, Variante (a) mit Slot 47 als Bitmaske ist damit mit den gemessenen Werten ausgeschlossen.
Die Slots 43 und 53–61 halten live jeden geschriebenen Wert, behalten nach dem Neuladen aber nur ein Bit, und das Patcher-Hash-Verfahren erreicht sie nicht.
Variante (d) hat einen belegten Kern: Pro Welt gibt es einen 1024-Byte-Flag-Block (Anker: Welt-ID `u64` + `0x400` bei `+0x18` + `0xEAEAEAEA` bei `−4`), in dem jeder der drei getesteten Pickups genau ein Byte gesetzt hat,
das bei zwei der drei Pickups nach dem Neuladen geprüft wurde und erhalten blieb, wobei der Block im Heap umzieht, auch andere Zustände enthält und nur für zwei Orte (Docking Hub Alpha, Pickup 3 und 4: Byte 7 und 8) zugeordnet ist.
Offen sind die Zuordnung aller 99 Orte zu Byte-Indizes (aus Patcher/MREA ableitbar oder nur durch Einsammeln jedes Orts messbar) und die Frage, ob das Byte bei jedem Itemtyp gesetzt wird, auch bei den 10 Orten vom Typ `SpecialFunction`.

## Offene Punkte

1. Zuordnung Byte-Index ↔ Pickup-Index für alle 99 Orte (Hypothese Norion: Pickup-Nummer + 4, Valhalla Pickup 11 → 1, je Welt verschieden).
2. Prüfung der 10 `SpecialFunction`-Orte und von Ort 0 (nie gepatcht) im Block.
3. Persistenz von Pickup 3 nach Speichern/Neuladen, und Verhalten des Blocks beim Laden eines Saves mit mehr als einer Welt besucht.
4. Slot 69 mit einer gesperrten Ship Missile Expansion messen. Menge je Expansion (Ship Missile: 3?) und ob Slot 69 dem Muster von Slot 68 folgt.
5. Ob das Max von Slot 47 durch einen echten Pickup (Hash `0x51E1A9FB`) das Neuladen übersteht (hier nur per direktem Schreiben geprüft).
6. Bits je Slot für 43 und 53–61 nach dem Laden (nur 1 Bit vermutet).
7. NTSC-U (`RM3E01`) und die Messung ohne 500 % Clock Override sind nicht geprüft. Alle Zahlen oben stammen von PrimeHack mit 500 % Clock Override.
