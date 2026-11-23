# AP-Live-Tests PAL: Direktschreiben für alle Item-Klassen (T11)

Stand: 2026-11-23. Prüft SPEC E9/E16: Wirkt das Direktschreiben von Anzahl/Kapazität in `PS + 0x54 + slot*0xC`
(`PS = [[0x80680234]+0x24]`, je Slot `u32 Anzahl, u32 Max, u32 ?`, Big Endian) für alle Item-Klassen im Pool?
Slot-Bedeutungen nach `AP_MEMORY_MAP.md` Abschnitt 3 und `AP_PATCHER_NOTES.md`. Abweichungen sind unten vermerkt, es gilt die Messung.

## Testumgebung

| Punkt | Wert |
|---|---|
| Emulator | PrimeHack v1.0.9 (Dolphin-Fork), Windows 11 |
| CPU Clock Override | an, 500 % (`OverclockEnable = True`, `Overclock = 5.` in `Dolphin.ini`) |
| Disc Speed | `FastDiscSpeed = True` in `GameSettings\RM3P01.ini` („Speed up Disc Transfer Rate“, also keine emulierte Lesezeit). In T10 meldete der Nutzer „Emulate Disc Speed aus“, das passt dazu |
| Spiel | PAL `RM3P01`, ISO `out/t01_IVG2J7OR.iso` (Seed IVG2J7OR, Starter Preset), außerhalb des Repos |
| Spielstand | Wegwerf-Save aus T10 (Nutzer bestätigt), Norion, Docking Hub Alpha, ingame. Frühes Spiel: Schiff nicht nutzbar, Hyper-Korruption (Story, laut Nutzer erst in Bryyo) nicht ausgelöst |
| Startinventar | Seed-Startitems (Power, Charge, Combat, Scan, Space Jump, Morph Ball, Bombs), dazu aus T10 noch Missile 15/15, Plasma, Grapple Lasso, Energy Tank, Screw Attack. `PS = 0x80995B20`, Welt Norion `0x6FB8EF2A9523C343` |
| Werkzeug | dolphin-memory-engine 1.3.0 (Python 3.12), Wegwerf-Skripte im Scratchpad außerhalb des Repos. Je Schreibzugriff: alle 70 Slots vor dem Schreiben, danach Lesen nach 0 s, 0,5 s und 3 s und alle 70 Slots nach 3 s |
| Zeitraum | 21:20 bis 21:43 (2026-11-23), Speichern + Reset + Continue Game um 21:42 |
| Absturz | keiner |

Methode: Der Nutzer spielte und meldete je Schritt, was er sah. Geschrieben wurde der Wert, den ein echter Pickup laut `Item.cs` ergäbe
(`capacity`/`amount` des Pickups addiert auf den Ausgangswert). **Wichtig zur Auswertung:** Der Nutzer meldete pro Item ein Gesamturteil („geht“) und nach
dem Neuladen „alles noch da“. HUD und Pausenmenü wurden daher nicht in jedem Fall einzeln abgefragt. Wo das Menü gezielt abgefragt oder fotografiert wurde, steht es
in der Spalte. Sonst steht „Sammelurteil“.

## Ergebnistabelle

Legende: ja / nein / n. p. (nicht prüfbar, mit Grund). „Sammelurteil“ = Nutzer meldete „geht“ bzw. „alles noch da“ ohne Einzelabfrage.
„Neuladen“ = Speichern, Reset, Continue Game; Speicherwert **und** Nutzerurteil.

| Slot | Item | Geschrieben (vorher → Wert) | Wirkt | HUD | Menü | Übersteht Neuladen | Seiteneffekt |
|---|---|---|---|---|---|---|---|
| 17 | Suit (SuitType) | 0/6 → 5/11 (Pickup: +5/+5) | ja, Anzug sichtbar verändert | Sammelurteil | Sammelurteil (Menü „Suits“) | Anzahl ja (5). **Max nein: 11 → 3** | Max wird beim Speichern/Laden auf 3 Bit gekürzt (11 mod 8 = 3). Kein Absturz, keine Sequenz |
| 13 | Command Visor | 0/0 → 1/1 | ja (Visier umschaltbar) | ja (Visier-Wechsel nutzbar) | nach Neuladen: Sammelurteil | ja | keiner |
| 14 | X-Ray Visor | 0/0 → 1/1 | ja | ja (Visier-Wechsel nutzbar) | nach Neuladen: Sammelurteil | ja | keiner |
| 44 | Ship Grapple | 0/0 → 1/1 | **n. p.:** Schiff im frühen Save nicht nutzbar | n. p. | nicht gemeldet, kein Eintrag bemerkt | Speicher ja (1/1) | keiner |
| 45 | Ship Missile | 0/0 → 3/3 (Pickup: +3/+3) | **n. p.:** wie Slot 44 | n. p. | nicht gemeldet, kein Eintrag bemerkt | Speicher ja (3/3) | keiner |
| 35 | Hyper Mode Tank | 0/0 → 1/1 | n. p. einzeln (siehe Hyper-Block unten) | n. p. | n. p. | Speicher ja | keiner |
| 37 | Hyper Missile | 0/0 → 1/1 | siehe Hyper-Block | siehe Hyper-Block | ja, im Menü „Hypermode“ gelistet (Screenshot) | ja (Menü nach Neuladen: Sammelurteil) | keiner |
| 38 | Hyper Ball | 0/0 → 1/1 | siehe Hyper-Block | siehe Hyper-Block | ja, gelistet (Screenshot) | ja | keiner |
| 39 | Hyper Grapple | 0/0 → 1/1 | siehe Hyper-Block | siehe Hyper-Block | ja, gelistet (Screenshot) | ja | keiner |
| 22 | Energy Cells gesamt (Fuses) | 0/9 → 2/9 | n. p.: Terminal nicht in Reichweite, Wirkung nur als Anzeige geprüft | ja, Menü zeigt 2 Cells **erst mit diesem Slot** | ja (siehe unten) | ja (2/9) | keiner |
| 23 | Energy Cell 1 (Fuse1) | 0/1 → 1/1 | siehe Slot 22: **allein ohne Anzeige** | nein, allein ohne Slot 22 | nein, allein ohne Slot 22 | ja (1/1) | keiner |
| 24 | Energy Cell 2 (Fuse2) | 0/1 → 1/1 | siehe Slot 22 | wie Slot 23 | wie Slot 23 | ja (1/1) | keiner |
| 33 | Boost Ball | 0/0 → 1/1 | ja (Boost-Schub) | Sammelurteil | Sammelurteil | ja | keiner |
| 34 | Spider Ball | 0/0 → 1/1 | ja (haftet an Schiene) | Sammelurteil | Sammelurteil | ja | keiner |
| 5 | Ice Missile | 0/0 → 1/1 | ja | Sammelurteil | Sammelurteil | ja | keiner |
| 6 | Seeker | 0/0 → 1/1 | ja | Sammelurteil | Sammelurteil | ja | keiner |
| 8 | Grapple Swing | 0/0 → 1/1 | ja | Sammelurteil | Sammelurteil | ja | keiner |
| 9 | Grapple Voltage | 0/0 → 1/1 | ja | Sammelurteil | Sammelurteil | ja | keiner |
| 2 | Nova Beam | 0/0 → 1/1 | ja | Sammelurteil | Sammelurteil | ja | keiner |
| 15 | Space Jump | 1/1 → 0/0 → 1/1 | ja: bei 0/0 nur Einfachsprung (Screw Attack ging weiter), bei 1/1 Doppelsprung | Sammelurteil | Sammelurteil | ja | keiner |
| 36 | HyperModeBeam (kein Pickup-Item, Zusatzversuch) | 0/0 → 1/1 | siehe Hyper-Block | – | ja: schaltet Menü-Kategorie „Hypermode“ frei | ja (Speicher 1/1) | keiner |

Hinweis „n. p.“ bei den Hyper-Einzelfähigkeiten: Hyper Mode selbst startete (unten). Ob Hyper Missile, Hyper Ball und Hyper Grapple einzeln funktionierten, hat der Nutzer nicht einzeln gemeldet.
Energy Cells 25–31 (Fuse3–9) wurden nicht geschrieben (Vorgabe: mindestens 2). Boost Ball und Spider Ball wirken laut Nutzer beide.

### Hyper Mode (Slots 35, 36, 37, 38, 39)

- Nach dem Schreiben von 35, 37, 38, 39 (je 1/1) startete Hyper Mode (laut Nutzer). **Vorher habe ich Hyper Mode nicht getestet**, es ist also nicht gemessen, ob diese vier Schreibzugriffe dafür nötig waren. Slot 42 (HyperModeOriginal) stand schon vor dem Test auf 1/1.
- Hyper Mode löste **keine Korruption** aus (laut Nutzer kommt das Story-Ereignis erst in Bryyo). `HypermodeEnergy` (Slot 19) blieb 0/0, `Stat_HypermodeUses` (66) stieg 0 → 3, `FaceCorruptionLevel` (46) blieb 0/0.
- Pausenmenü: Mit 35/37/38/39 stand oben links **„???“** (gesperrt). Nach dem Schreiben von Slot 36 (HyperModeBeam, 1/1) heißt die Kategorie **„Hypermode“** und listet Hyper Beam, Hyper Ball, Hyper Missile und Hyper Grapple (Screenshot vom Nutzer). Slot 36 ist **kein** Pickup-Item des Patchers. Die Menü-Freischaltung hängt also an einem Slot, den kein Pickup setzt. Nicht gemessen: ob die Kategorie allein an Slot 36 hängt oder an der Kombination.
- Slot 47 (kein Slot von mir): Das Max stieg während der Hyper-Mode-Nutzung 0 → 1 → 2, die Anzahl blieb 0. Nach Speichern und Neuladen wieder 0/0 (wie in T10 Test B). Ob das auch im unveränderten Spiel passiert, ist nicht geprüft.

### Energy Cells

- Slots 23 und 24 allein (je 1/1): Pausenmenü und HUD zeigten **nichts**.
- Zusätzlich Slot 22 auf 2/9: Das Spiel zeigt 2 Cells. Das Spiel rechnet Slot 22 aus den Slots 23–31 **nicht** nach (Slot 22 blieb 0/9, bis ich ihn schrieb).
- Nicht geprüft: ob ein echter Energy-Cell-Pickup Slot 22 miterhöht (der Patcher schreibt in `Item.cs` nur den Fuse-Slot, die Erhöhung von 22 passiert vermutlich im Spiel). Nicht geprüft: Einsetzen der Cells (Wirkung auf Slot 52 `EnergyCellsUsed`, Terminals).

## Diff aller 70 Slots

Je Schreibzugriff (nach 3 s) änderte sich **nur** der geschriebene Slot, kein anderer. Ausnahme: Spielzähler und Slot 47 (siehe oben).

Gesamtvergleich Baseline (21:19:59) → vor dem Speichern (21:41:50), 26 Slots:
alle von mir geschriebenen Slots (2, 5, 6, 8, 9, 13, 14, 17, 22, 23, 24, 33, 34, 35, 36, 37, 38, 39, 44, 45) mit den Werten der Tabelle, außerdem Spielwerte:
Slot 4 (Missile) 15 → 14 (Schuss), 47 (0/0 → 0/2, Hyper-Mode-Nutzung), 63 (Stat_ShotsFired 62 → 184), 64 (Stat_DamageReceived 2 → 9), 65 (Stat_DataSaves 4 → 5), 66 (Stat_HypermodeUses 0 → 3).

Vergleich vor dem Speichern (21:41:50) → nach Neuladen (21:43:43), 5 Slots:

| Slot | vorher | nachher | Ursache |
|---|---|---|---|
| 4 | 14/15 | 15/15 | Spiel füllt Missiles auf |
| 17 | 5/11 | **5/3** | Max auf 3 Bit gekürzt (Befund), Anzahl bleibt |
| 47 | 0/2 | 0/0 | wie T10, Spiel setzt zurück |
| 63 | 184 | 189 | Schüsse |
| 65 | 5 | 6 | Speichern zählt DataSaves |

Alle anderen 65 Slots, darunter alle Test-Slots, blieben gleich. Nach dem Neuladen sind Welt, `PS` und Ingame-Erkennung unverändert.

## Story-Ereignisse und inkonsistente Zustände

- **Suit:** Der Anzug änderte sich sichtbar, es lief keine Sequenz, kein Absturz. Nach dem Neuladen steht das Max auf 3. Die Anzahl bleibt 5, damit gilt die Connector-Regel „Anzahl ≥ 5 = hat Item“ (`corruption_remote_connector.py:142-152`) weiter. Ein echter Pickup (+5 auf Max 6 = 11) würde nach derselben Rechnung ebenfalls auf 3 gekürzt, das ist **nicht** mit einem echten Pickup geprüft.
- **Hyper Mode:** Das Spiel startete Hyper Mode ohne das Story-Ereignis (keine Korruption, kein Absturz). Das Menü-Verhalten (Eintrag erst mit Slot 36) ist die einzige Inkonsistenz, die ich beobachtet habe. Was passiert, wenn der Nutzer später das Story-Ereignis in Bryyo auslöst, wurde nicht gemessen (gehört zu T15).
- **Schiffs-Items:** Ohne nutzbares Schiff nicht beurteilbar. Der Speicher hielt die Werte auch nach Neuladen, ein Menü- oder Spielhinweis wurde nicht gemeldet.
- Nicht aufgetreten: Absturz, übersprungene Sequenz, Veränderung fremder Slots durch meine Schreibzugriffe.

## Abweichungen von der Memory Map

- Slot 22 (Fuses) ist nicht bloß eine Summe: Das Menü zeigt die Cells nur, wenn Slot 22 geschrieben ist. `AP_MEMORY_MAP.md` Zeile 102 nennt „Energy Cells Total“ ohne diese Abhängigkeit.
- Slot 17 (SuitType): Max ist nach dem Speichern/Laden auf 3 Bit begrenzt (gemessen 11 → 3). `AP_MEMORY_MAP.md` nennt Max 6.
- Slot 36 (HyperModeBeam): im Patcher kein Pickup, bestimmt aber die Menü-Kategorie „Hypermode“.
- Slot 47: Max steigt im Spiel mit den Hyper-Mode-Nutzungen (0/0 → 0/2 bei 3 Nutzungen).

## Items, die per Direktschreiben NICHT wirken

Keines der geprüften Items hat sich als wirkungslos erwiesen. Einschränkungen (keine Fehlfunktionen, aber Bedingungen für den Client):

1. **Energy Cells 23–31** zeigen sich im Spiel nur, wenn Slot 22 mitgeschrieben ist (2 Cells nur mit 22 = 2/9, nicht mit 23/24 allein).
2. **Hyper-Mode-Menü** („Hypermode“-Kategorie statt „???“) braucht Slot 36 = 1/1, den kein Pickup setzt.
3. **Suit (17):** Das Max überlebt nur 3 Bit (11 → 3), die Anzahl 5 bleibt.

Nicht prüfbar (frühes Spiel): Wirkung von Ship Grapple (44) und Ship Missile (45), Wirkung von Hyper Missile/Ball/Grapple einzeln, Wirkung der Energy Cells (Terminals), Verhalten beim späteren Story-Ereignis in Bryyo.

## Folgerung für E16 (DOL-Hook)

Alle geprüften Item-Klassen (Suit, Visiere, Beams, Missiles, Grapple, Boost/Spider, Space Jump, Hyper-Slots, Energy Cells) wirkten per Direktschreiben und überstanden Speichern und Neuladen. Die Bedingung aus E16 („nur falls T11 ein Item findet, das per Direktschreiben nicht wirkt“) ist damit nach dieser Messung nicht erfüllt. Offen sind die Wirkung der Schiffs-Items und das Verhalten beim späteren Hyper-Story-Ereignis; der Client muss außerdem Slot 22 (Energy Cells) und Slot 36 (Hypermode-Menü) mitschreiben und kann beim Suit nur die Anzahl (nicht das Max) verlässlich halten.

## Offene Punkte

1. Schiffs-Items (Slots 44, 45) in einem Save mit nutzbarem Schiff testen (Wirkung, HUD, Menü).
2. Hyper Missile, Hyper Ball, Hyper Grapple und Hyper Tank einzeln auf Wirkung prüfen; klären, ob 35/37/38/39 für den Start von Hyper Mode nötig sind und ob Slot 36 allein den Menüpunkt freischaltet.
3. Energy Cells einsetzen (Terminal) und prüfen, ob Slot 22 bei einem echten Pickup miterhöht wird; Slots 25–31 mit demselben Muster prüfen.
4. Suit-Max: mit einem echten Suit-Pickup gegenmessen, ob das Max dort ebenfalls auf 3 fällt.
5. Verhalten beim Story-Ereignis in Bryyo nach per Direktschreiben vergebenen Hyper-Slots (T15).
6. Nicht geprüft: NTSC-U (`RM3E01`), Standard-Dolphin und die Messung ohne 500 % Clock Override.
