# STATUS

Stand: 2026-11-23 · MVP gemäß SPEC.md E1–E3.

| Task-ID | Beschreibung | Status | Session | Ergebnis |
|---|---|---|---|---|
| T01 | (F1) Dev-Umgebung aufsetzen, einen Seed lokal generieren und exportieren, unterstützte Spielversion feststellen und dokumentieren | fertig (nur mit PAL getestet, siehe E7) | Worker T01, 2026-11-23 | Anleitung `docs/AP_DEV_SETUP.md`. Python-3.12-venv + Requirements, .NET 8 SDK 8.0.428, Patcher als **win-x86** gebaut (byte-identisch zur mitgelieferten EXE). Seed IVG2J7OR (Starter Preset) exportiert, ISO bootet in Dolphin 2609b bis G.F.S. Olympus und ist spielbar. Kein Code prüft Game-ID oder Hash. Implizite Zielversion ist Wii-Standalone NTSC-U **RM3E01** (`CreateWBFS.bat:1-2`, MP3Update-hdiffs). PAL **RM3P01** geht nur ohne MP3Update/Deflicker (hpatchz-Größenfehler). Trilogy wird nicht unterstützt. Offen: Test mit RM3E01-ISO |
| T02 | (F2) Speicher-Mapping dokumentieren: Inventar, Pickup-/Location-Flags, Spielzustand – Quelle: `corruption_remote_connector.py` und Dolphin, live geprüft auf RM3P01 | fertig (PAL live, NTSC-U/J nur aus Code) | Worker T02, 2026-11-23 | `docs/AP_MEMORY_MAP.md`. PAL RM3P01 live bestätigt: Build-String, Welt-ID (`[0x80680234]+8`, Valhalla→Norion), Ingame-Erkennung (CPlayer-Zeiger + vtable `0x80595238`, Menü/Laden = 0), Inventar `[[0x80680234]+0x24]+0x54+id*0xC` (ScrewAttack 0/0→1/1, ItemPercentage 0/100→1/101→2/102). **Lücken:** Randovania kann für MP3 weder Items geben (kein Remote-Exec-Hook, `string_display=None`, Pending-Byte immer 0xFF) noch Location-Checks erkennen (`multiworld_magic_item` nicht implementiert). Vorschlag: Zähler-Item pro Pickup im Patcher (T05). Seed IVG2J7OR startet auf Valhalla, nicht Olympus |
| T03 | (F3) DB-Konverter Corruptovania-JSON → AP-Regionen/Locations/Regeln | läuft | – | – |
| T04 | (F4) APWorld-Grundgerüst, Solo-Seed generiert fehlerfrei | offen (wartet auf T03) | – | – |
| T05 | (F5) Patch-Pfad AP → Patch-JSON → MP3Randomizer, AP-Platzhalter-Item | offen (wartet auf T04; eigenen win-x86-Build einbinden) | – | – |
| T06 | (F6) Client: Location-Checks senden | offen (wartet auf T02, E6) | – | – |
| T07 | (F7) Client: Items empfangen, Wiederaufnahme nach Neustart | offen (wartet auf T06) | – | – |
| T08 | (F8) Ende-zu-Ende-Test 2-Spieler-Multiworld | offen (wartet auf T05, T07) | – | – |
| T09 | Patcher-Analyse (nur lesen): Wie setzt MP3Randomizer Pickups, welche Item-IDs/Slots sind frei, lässt sich pro Location ein eindeutiger Marker schreiben? Eingabe für F-01 | läuft | – | – |

T06/T07 sind blockiert durch F-01.

## Fragen an Fable

| ID | Frage | Status |
|---|---|---|
| F-01 | MP3 (Wii, Dolphin, PAL RM3P01): Für Archipelago brauchen wir Location-Check-Erkennung und Item-Vergabe von außen. Live messbar ist nur das Inventar unter `[[0x80680234]+0x24]+0x54+id*0xC` (Anzahl/Max), ein Code-Hook existiert nicht. Welcher Ansatz ist robust: (a) der Patcher setzt pro Pickup ein eindeutiges Zähler-Item in einem ungenutzten Inventar-Slot, und der Client liest diese Slots; (b) Hook in `main.dol`, der Pickup-Events in einen Ringpuffer schreibt und eine Item-Queue abarbeitet; (c) direktes Schreiben ins Inventar zur Item-Vergabe. Reicht (a)+(c) für den MVP, oder brechen Fähigkeiten (z. B. Grapple, Hyper Mode) ohne Spielfunktions-Aufruf? | offen – Antwort aus T09 abwarten, dann stellen |
