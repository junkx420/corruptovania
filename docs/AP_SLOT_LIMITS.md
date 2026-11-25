# Inventar-Slots: Bitbreite, Persistenz und Spielereignisse (T19, T15)

Stand: 2026-11-25. Nur PAL `RM3P01`, PrimeHack v1.0.9, **CPU Clock Override aus** (`OverclockEnable = False`), Disc Speed
„schnell“ (`FastDiscSpeed = True`). Grundlage: SPEC E9/E11, `AP_LIVE_TESTS.md` (T10), `AP_LIVE_TESTS_T11.md` (T11).
Inventar wie dort: `PS + 0x54 + slot*0xC`, je Slot `u32 Anzahl, u32 Kapazität`, `PS = [[0x80680234]+0x24]` (live `0x80995B20`).

> **Kurzfassung für T07**
> 1. Die `main.dol` enthält ab `0x8057D5F8` eine Tabelle mit 70 Einträgen (Name, **Maximum**, **Flags**). Beim Speichern
>    behält jeder Slot von Anzahl **und** Kapazität getrennt nur die unteren `bits = bit_length(Maximum)` Bit, also
>    `Wert mod 2^bits`. **Es wird nicht geklemmt.** Gemessen an 54 Slots in zwei Durchgängen, alle 108 Werte passen (Abschnitt 3).
>    Das Maximum ist identisch mit `max_capacity` in Randovanias `header.json`.
> 2. Slots ohne Flag-Bit 31 werden **gar nicht** gespeichert, nach dem Laden stehen sie auf 0/0: 18 Energy, 19, **47**,
>    48, 49, 50, **69**.
> 3. Der T11-Befund „Suit 11 → 3“ ist **reproduziert und erklärt**: SuitType hat 3 Bit (Maximum 6), 7 bleibt erhalten,
>    8 wird 0.
> 4. **Konflikte mit dem Pool:** Suit (Kapazität 6 + 5 = 11 > 7) und Energy Cells, falls T07 dort Kapazität addiert
>    (22: 9 + 9 = 18 > 15, 23–31: 1 + 1 = 2 → 0). Alle anderen Pool-Summen passen: Missile 245 ≤ 255, Energy Tank 14 ≤ 15,
>    Ship Missile 11 ≤ 15, Slot 68 240, ItemPercentage 199 ≤ 255.
> 5. **Live-Freeze:** Suit-Anzahl 13 lässt das Spiel im selben Frame einfrieren. Die Anzahl in Slot 17 ist ein Index.
> 6. **T15:** Eine Energy Cell einsetzen senkt die **Anzahl** von 22 und Fuse_i, die Kapazität bleibt. Hypermode und der Flug nach Norion
>    senken nichts. Ein Tod lädt den letzten Spielstand, damit sinkt alles auf den gespeicherten Stand.

## 1. Quelle der Bitbreite: Powerup-Tabelle in der DOL

PAL `main.dol`, Adresse `0x8057D5F8` (Dateioffset `0x5796D8`), 70 × 12 Byte: `u32` Zeiger auf den Namen, `u32` Maximum,
`u32` Flags. Original-ISO (`pal_extract`) und T01-ISO (`pal_t01_extract`) sind hier byte-identisch. Reproduktion
(Repo-Wurzel, venv):

```powershell
venv\Scripts\python.exe -I apworld\tools\live\slot_probe.py dol ..\pal_extract\DATA\sys\main.dol
```

Das Skript vergleicht die DOL mit `SLOT_TABLE` in `apworld/tools/live/slot_probe.py` (Exit 1 bei Abweichung).

Flags: **Bit 31 = wird gespeichert.** Das ist durch Messung belegt: Alle Slots mit Bit 31 hielten ihre Werte, und die
geprüften Slots ohne Bit 31 (47, 69, laut T10 auch 48, 49) stehen nach dem Laden auf 0/0. Bit 30 ist bei 21, 40, 41, 51–61
nicht gesetzt, bei den übrigen gespeicherten Slots schon. Seine Bedeutung ist **unbekannt**, auf die Speicherung hat es
keinen Einfluss (21 und 53–61 wurden gemessen).

Namen in der DOL, die von `AP_MEMORY_MAP.md` abweichen bzw. dort fehlen: **43 = HyperModeCharge**, **47 = PhazonBall**,
**52 = FusesUsed** (dort „EnergyCellsUsed“), **53–61 = Fuse1Used … Fuse9Used**.

## 2. Ablauf der Messung

| Zeit (2026-11-25) | Schritt |
|---|---|
| 01:41 | Spielstand gesichert (`out/t19/save_backup_before`, außerhalb des Repos) |
| 01:45 | Neues Spiel (Rando-Start, G.F.S. Valhalla, Docking Bay 5, Schiff nutzbar), Ist-Stand `baseline` |
| 01:45 | **Durchgang 1** (`pass1`) geschrieben: 54 Slots, Kapazität = `2^bits − 1`, Anzahl = Pool-Maximum. Speichern am Schiff, Reset, Continue |
| 01:47 | **Durchgang 2** (`pass2`) geschrieben: Anzahl `2^bits + 1`, Kapazität `2^bits`, bei 1-Bit-Items 3/2, Suit 13/8. **PrimeHack fror sofort ein** (Speicher unverändert, noch vor dem Speichern). Der Spielstand von Durchgang 1 blieb erhalten |
| 01:51 | Neustart, Durchgang-1-Stand geladen (identisch zu `loaded_pass1`). **Durchgang 2s** (`pass2s`, entschärft): Anzahl = Kapazität = `2^bits`, Suit 5/8, kritische Slots 0/11/12/15/32 auf 1/1. Lief, Speichern, Reset, Continue |
| 01:53 | Freeze-Probe: nur Slot 17 auf 13/8 → **sofort eingefroren**. Neustart |
| 01:54–01:58 | T15 (Abschnitt 5), Logger mit 0,1 s Takt über alle 70 Slots |
| 02:00 | Ausgangsinventar zurückgeschrieben, am Schiff gespeichert, geprüft (`after_final_save`: nur Stat_DataSaves +1) |

Rohdaten (JSON je Schritt, JSONL-Logs) liegen in `out/t19/` neben dem Repo, nicht im Repo.

## 3. Messwerte Durchgang 1 und 2s

„vor“ = gelesen 3 s nach dem Schreiben (Spiel hat nichts verändert, außer Slot 47), „nach“ = nach Speichern, Reset, Continue.

| Slot | Name | bits | D1 vor | D1 nach | D2s vor | D2s nach | Befund |
|---|---|---|---|---|---|---|---|
| 0 | PowerBeam | 1 | 1/1 | 1/1 | 1/1 | 1/1 | kritisch, nur 1 geschrieben |
| 1–3, 5–10, 13, 14, 16 | Beams, Charge, Missile-Upgrades, Grapple, Bomb, Command/X-Ray, Screw | 1 | 1/1 | 1/1 | 2/2 | **0/0** | 1 Bit |
| 4 | Missile | 8 | 245/255 | 255/255 | 256/256 | **0/0** | 8 Bit, Anzahl wird beim Speichern am Schiff auf Kapazität aufgefüllt |
| 11, 12, 15, 32 | Combat/Scan Visor, DoubleJump, MorphBall | 1 | 1/1 | 1/1 | 1/1 | 1/1 | kritisch, nur 1 geschrieben |
| 17 | SuitType | 3 | 5/7 | 5/7 | 5/8 | **5/0** | 3 Bit, 7 bleibt, 8 → 0 |
| 20 | EnergyTank | 4 | 14/15 | 15/15 | 16/16 | **0/0** | 4 Bit, Anzahl wird beim Speichern aufgefüllt |
| 21 | ItemPercentage | 8 | 199/255 | 199/255 | 256/256 | **0/0** | 8 Bit, Spielstand-Menü zeigt „199%“ |
| 22 | Fuses | 4 | 9/15 | 9/15 | 16/16 | **0/0** | 4 Bit |
| 23–31 | Fuse1–9 | 1 | 1/1 | 1/1 | 2/2 | **0/0** | 1 Bit |
| 33–39 | Boost, Spider, HyperModeTank/Beam/Missile/Ball/Grapple | 1 | 1/1 | 1/1 | 2/2 | **0/0** | 1 Bit |
| 43 | HyperModeCharge | 1 | 1/1 | 1/1 | 2/2 | **0/0** | 1 Bit (T10-Vermutung bestätigt) |
| 44 | ShipGrapple | 1 | 1/1 | 1/1 | 2/2 | **0/0** | 1 Bit |
| 45 | ShipMissile | 4 | 11/15 | 11/15 | 16/16 | **0/0** | 4 Bit, Anzahl **nicht** aufgefüllt (bleibt 11) |
| 47 | PhazonBall | – | 0/1 (Anzahl live → 0) | **0/0** | 0/2 | **0/0** | nicht gespeichert |
| 52 | FusesUsed | 4 | 15/15 | 15/15 | 16/16 | **0/0** | 4 Bit |
| 53, 55, 57, 59, 61 | Fuse1/3/5/7/9Used | 1 | 1/0 | 1/0 | 2/3 | **0/1** | 1 Bit, Anzahl und Kapazität getrennt |
| 54, 56, 58, 60 | Fuse2/4/6/8Used | 1 | 0/1 | 0/1 | 3/2 | **1/0** | 1 Bit, Anzahl und Kapazität getrennt |
| 68 | Stat_TinCanHighScore | 17 | 240/131071 | 240/131071 | 131072/131072 | **0/0** | 17 Bit |
| 69 | Stat_TinCanCurrentScore | – | 8/8 | **0/0** | 9/9 | **0/0** | nicht gespeichert |

Auswertung (`slot_probe.py check`): Hypothese „mod 2^bits“ trifft **54/54** in D2s und alle Kapazitäten in D1. Die beiden
Anzahl-Abweichungen in D1 (Slots 4 und 20) kommen vom Auffüllen beim Speichern am Schiff. Das Logging bestätigt den Ablauf:
Missile 245 → 255 und Energy Tank 14 → 15 kamen erst beim Speichern, Stat_DataSaves stieg dabei auf 1.
Hypothese „Klemmen auf das Tabellenmaximum“ trifft 7/54 und ist damit **widerlegt**. Werte über dem Tabellenmaximum
bleiben erhalten, solange sie in die Bitbreite passen (Suit 7 > 6, Energy Tank 15 > 14, Fuses 15 > 9, Ship Missile 15 > 11).

**Freeze (Durchgang 2):** In `pass2` waren mehrere unmögliche Werte gleichzeitig geschrieben. Einzeln geprüft ist nur
SuitType 13/8, das friert sofort ein. Nicht einzeln geprüft sind Anzahl > Kapazität bei Items (3/2), ItemPercentage
257/256, Missile 257/256 (HUD zeigte dabei „255“) und Energy Tank 17/16. Anzahl > Kapazität bei Fuse*Used (1/0, 3/2) lief
ohne Probleme. Ob Suit-Anzahl 6 oder 7 schon einfriert, ist **nicht** geprüft. 5 (Hazard Shield, T11) geht.

## 4. Tabelle für T07 (maschinenlesbar)

Alle Slots, die ein AP-Item berühren kann, dazu die Startitems und die Sonder-Slots aus dem Auftrag. `bits_anzahl` und
`bits_kapazitaet` gelten für den Spielstand, live halten alle Slots volle `u32`. `max_gueltig` ist der höchste Wert, der Speichern
und Laden übersteht (`2^bits − 1`), bzw. 0 bei nicht gespeicherten Slots. `pool_max` ist Kapazität nach Start plus vollem
AP-Pool (`apworld/metroidprime3/data/items.py`, Mengen aus `Item.cs`). `tab_max` ist das Maximum aus der DOL (= `header.json`
`max_capacity`). Messbelege: Abschnitt 3 (`D1` = Durchgang 1, `D2s` = Durchgang 2s).

```csv
slot;name;bits_anzahl;bits_kapazitaet;max_gueltig;tab_max;pool_max;pool_ok;besonderheiten
0;PowerBeam;1;1;1;1;1;ja;Startitem, Kapazität>0 ist Ingame-Kriterium des Clients, nur 1 gemessen
1;PlasmaBeam;1;1;1;1;1;ja;Progressive Beam Stufe 1, 2 -> 0 gemessen
2;NovaBeam;1;1;1;1;1;ja;Progressive Beam Stufe 2, 2 -> 0 gemessen
3;ChargeUpgrade;1;1;1;1;1;ja;Startitem, 2 -> 0 gemessen
4;Missile;8;8;255;255;245;ja;Launcher 5 + 48x5, Speichern am Schiff füllt Anzahl auf Kapazität, 256 -> 0, Umbuchung aus Slot 68 (T10) kann zusätzlich addieren
5;IceMissile;1;1;1;1;1;ja;2 -> 0 gemessen
6;SeekerMissile;1;1;1;1;1;ja;2 -> 0 gemessen
7;GrappleBeamPull;1;1;1;1;1;ja;2 -> 0 gemessen
8;GrappleBeamSwing;1;1;1;1;1;ja;2 -> 0 gemessen
9;GrappleBeamVoltage;1;1;1;1;1;ja;2 -> 0 gemessen
10;Bomb;1;1;1;1;1;ja;Startitem, 2 -> 0 gemessen
11;CombatVisor;1;1;1;1;1;ja;Startitem, nur 1 gemessen
12;ScanVisor;1;1;1;1;1;ja;Startitem, nur 1 gemessen
13;CommandVisor;1;1;1;1;1;ja;2 -> 0 gemessen
14;XRayVisor;1;1;1;1;1;ja;2 -> 0 gemessen
15;DoubleJump;1;1;1;1;1;ja;Startitem Space Jump Boots, nur 1 gemessen
16;ScrewAttack;1;1;1;1;1;ja;2 -> 0 gemessen
17;SuitType;3;3;7;6;11;NEIN;Start 0/6, Pickup +5/+5 ergibt 5/11 -> 5/3 nach Laden, 7 bleibt, 8 -> 0, Anzahl ist Index: 13 friert live sofort ein
20;EnergyTank;4;4;15;14;14;ja;16 -> 0, Speichern am Schiff füllt Anzahl auf Kapazität
21;ItemPercentage;8;8;255;255;199;ja;Start 0/100, Spiel +1/+1 je Pickup, Client schreibt nicht, 256 -> 0
22;Fuses;4;4;15;9;9;ja (nur Anzahl);Start 0/9: Kapazität ist fest 9, Anzahl = gehaltene Zellen, Einsetzen senkt Anzahl um 1, Kapazität +1 je Zelle ergäbe 18 -> 2
23;Fuse1;1;1;1;1;1;ja (nur Anzahl);Start 0/1, Anzahl = Zelle gehalten, Einsetzen setzt Anzahl 0, Kapazität bleibt 1, 2 -> 0
24;Fuse2;1;1;1;1;1;ja (nur Anzahl);wie 23
25;Fuse3;1;1;1;1;1;ja (nur Anzahl);wie 23
26;Fuse4;1;1;1;1;1;ja (nur Anzahl);wie 23
27;Fuse5;1;1;1;1;1;ja (nur Anzahl);wie 23
28;Fuse6;1;1;1;1;1;ja (nur Anzahl);wie 23
29;Fuse7;1;1;1;1;1;ja (nur Anzahl);wie 23
30;Fuse8;1;1;1;1;1;ja (nur Anzahl);wie 23
31;Fuse9;1;1;1;1;1;ja (nur Anzahl);wie 23
32;MorphBall;1;1;1;1;1;ja;Startitem, nur 1 gemessen
33;BoostBall;1;1;1;1;1;ja;2 -> 0 gemessen
34;SpiderBall;1;1;1;1;1;ja;2 -> 0 gemessen
35;HyperModeTank;1;1;1;1;1;ja;Pool-Item Hypermode, 2 -> 0
36;HyperModeBeam;1;1;1;1;1;ja;kein Pickup, schaltet Menü Hypermode frei (T11), 2 -> 0
37;HyperModeMissile;1;1;1;1;1;ja;2 -> 0
38;HyperModeBall;1;1;1;1;1;ja;2 -> 0
39;HyperModeGrapple;1;1;1;1;1;ja;2 -> 0
43;HyperModeCharge;1;1;1;1;-;-;Name aus DOL, 2 -> 0, nicht für Zähler/Marker geeignet
44;ShipGrapple;1;1;1;1;1;ja;2 -> 0
45;ShipMissile;4;4;15;11;11;ja;Ship Missile 3 + 8x1, Anzahl beim Speichern nicht aufgefüllt, 16 -> 0
47;PhazonBall;0;0;0;1;-;-;nicht gespeichert (Flag 0), Anzahl = Hypermode aktiv (1 während Nutzung), neues Spiel 0/1, nach Laden 0/0, nie schreiben
52;FusesUsed;4;4;15;9;-;-;eingesetzte Zellen, Einsetzen +1/0 (Anzahl), 16 -> 0
53;Fuse1Used;1;1;1;1;-;-;Zelle 1 eingesetzt (Anzahl 0 -> 1 beim Einsetzen, Start 0/1), Anzahl und Kapazität getrennt gespeichert
54;Fuse2Used;1;1;1;1;-;-;wie 53
55;Fuse3Used;1;1;1;1;-;-;wie 53
56;Fuse4Used;1;1;1;1;-;-;wie 53
57;Fuse5Used;1;1;1;1;-;-;wie 53
58;Fuse6Used;1;1;1;1;-;-;wie 53
59;Fuse7Used;1;1;1;1;-;-;wie 53
60;Fuse8Used;1;1;1;1;-;-;wie 53
61;Fuse9Used;1;1;1;1;-;-;wie 53
68;Stat_TinCanHighScore;17;17;131071;99999;240;ja;gesperrte Missile Expansions (T10: +5 je Stück), Spiel bucht nach Slot 4 um, 131072 -> 0
69;Stat_TinCanCurrentScore;0;0;0;99999;-;-;nicht gespeichert (Flag 0), ob gesperrte Ship Missiles hier landen, ist offen
```

## 5. T15: Sinken Kapazitäten durch Spielereignisse?

Aufbau: Neues Spiel mit Ausgangsinventar, dazu per Direktschreiben Hypermode (35–39 je 1/1), 3 Energy Tanks und Energy Cell 1
(23 = 1/1, 22 = 1/9). Logger über alle 70 Slots im 0,1-s-Takt. Statistik-Slots 62–64 sind hier weggelassen.

| Ereignis | geprüft | Slot: vorher → nachher | Kapazität gesunken? |
|---|---|---|---|
| Energy Cell 1 am Terminal in Docking Bay 5 eingesetzt (01:54:52) | ja | 22: 1/9 → **0/9**, 23: 1/1 → **0/1**, 52: 0/9 → 1/9, 53: 0/1 → 1/1 | **nein**, aber die **Anzahl** sinkt (22, 23) |
| Hypermode aktivieren und beenden, zweimal (01:55:02–01:55:40) | ja | 47: 0/1 → 1/1 → 0/1 (je Nutzung), 66: 0 → 1 → 2. Energy Tank blieb 3/3 | nein |
| Hypermode bis zur Korruption | ja, aber nicht auslösbar | Hypermode lief ohne Korruption aus (Story-Hypermode noch nicht erreicht) | – |
| Tod (Game Over, vom Spieler herbeigeführt) und Continue (01:56:50–01:56:55) | ja | Alle 70 Slots = Inventar des letzten Spielstands (byte-gleich mit `loaded_pass2s`). Was seit dem Speichern dazukam, war weg | **ja, auf den Stand des letzten Spielstands** |
| Flug Valhalla → Norion (01:57:46) | ja | keine Inventaränderung | nein |
| Speichern am Schiff | ja (T19) | Missile- und Energy-Tank-Anzahl werden auf die Kapazität aufgefüllt, Ship Missile nicht, Stat_DataSaves +1 | nein |
| Rückflug Norion → Valhalla (01:58:35) | nur Zustandswechsel geloggt | Vergleich nicht ausgewertet (Logpuffer beim Stoppen nicht geschrieben) | offen |

**Nicht geprüft (nicht erreichbar ohne Spielfortschritt), die Erkennung übernimmt der Client im Playtest:**
- Anzugwechsel zum PED-Anzug (Story nach Norion/Olympus), Phazon-Anzug auf Phaaze (Slots 17, 40, 41)
- Story-Hypermode und Korruption in Bryyo (Slots 42 HyperModeOriginal, 46 FaceCorruptionLevel, 19 HypermodeEnergy), Tod durch Korruption
- Phaaze: Dauer-Hypermode (40 HyperModePermanent, 41 HyperModePhaaze), Verlust des Hyper-Modus nach dem Endkampf
- Energy Cells 2–9 einsetzen (nur Cell 1 geprüft), Terminals außerhalb von Valhalla
- Command Visor gestört (51 CommandVisorJammed), Ship-Missile-Verbrauch, gesperrte Ship Missile Expansion (Slot 69?)
- Echter Suit-Pickup (Klemmt `add_power_up` die Kapazität auf 6? T11 offen)

## 6. Folgen für T07 und E11

- Soll-Werte **absolut** setzen und auf das Tabellenmaximum klemmen (`tab_max`, = `header.json` `max_capacity`). Das ist
  immer `≤ 2^bits − 1`, damit übersteht jeder geschriebene Wert das Speichern. Nicht blind addieren.
- **Suit (17):** Pool-Item Hazard Shield als feste Werte schreiben: Anzahl 5, Kapazität 6 (Start-Kapazität). Nie 11
  (→ 3 nach Laden) und nie eine Anzahl ≥ 8 (13 friert ein, 6/7 ungeprüft).
- **Energy Cells (22–31):** Die Kapazität ist von Anfang an gesetzt (0/9, 0/1) und ändert sich nie. Das Item ist die **Anzahl**,
  und die sinkt beim Einsetzen. Soll für Fuse_i: Anzahl 1, solange Zelle i empfangen ist **und** Fuse_iUsed (Slot 52 + i, Anzahl)
  0 ist, sonst 0. Soll für Slot 22: Anzahl = empfangene minus eingesetzte Zellen (= Summe der Fuse_i-Anzahlen), Kapazität 9.
  Eine einmal eingesetzte Zelle darf nicht neu gegeben werden.
- **Missile (4) / Energy Tank (20):** Speichern füllt die Anzahl auf. Bei einer Erhöhung Kapazität auf Soll setzen und Anzahl
  um dieselbe Differenz anheben (gesunkene Anzahl durch Verbrauch nicht zurücksetzen). Pool 245 bzw. 14 passt.
  Falls Slot 68 (gesperrte Expansions) im AP-Modus noch gefüllt werden kann, addiert das Spiel ihn beim nächsten Missile-Pickup auf
  Slot 4 (T10). Das kann über 255 führen und muss vermieden werden. Mit `--ap-mode` (T16, Pickups geben 0/0) fällt das weg.
- **Tod/Continue** setzt alles auf den letzten Spielstand zurück. Genau dafür braucht E11 den Abgleich ohne gespeicherten Index:
  Nach jedem Laden muss der Client alle Soll-Werte neu prüfen.
- Slots 47 und 69 nie als Speicher für Client-Zustand nutzen (nicht gespeichert). 43 und 53–61 tragen nur 1 Bit, und 53–61 haben
  Spielbedeutung (eingesetzte Zellen).

**Empfehlung E11:** „Soll-Kapazität nur anheben“ bleibt für alle echten Kapazitäts-Slots tragfähig, wenn T07 die Soll-Werte
absolut setzt und auf `max_capacity` klemmt. Ausnahmen sind der Suit (fest 5/6 schreiben) und die Energy Cells 22–31: Dort zählt
die Anzahl, die beim Einsetzen sinkt, deshalb gilt Soll = empfangen minus eingesetzt laut Slots 52–61, und eingesetzte Zellen
werden nie neu gegeben.

## 7. Grenzen der Messung

- Nur PAL `RM3P01`, nur PrimeHack v1.0.9 (Clock Override aus), nur Speichern am Schiff (keine Speicherstation).
- Bei den kritischen Slots 0, 11, 12, 15, 32 ist der Übergang 2 → 0 nicht gemessen (nur 1/1). Die Bitbreite stammt aus der Tabelle
  und folgt dem gemessenen Muster der übrigen 1-Bit-Slots.
- Spielstand nach Durchgang 1 enthielt Werte über `tab_max`. Das Spiel lud sie ohne Fehler, sie wurden aber nicht im Spiel benutzt.
- Messskript: `apworld/tools/live/slot_probe.py` (schreibt nur ins Inventar-Array im PrimeHack-RAM, nur ingame).
