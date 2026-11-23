# AP-Dev-Setup: Corruptovania unter Windows (T01)

Stand: 2026-11-23. Getestet auf Windows 11 Home (x64) mit Git Bash und PowerShell 5.1.
Ziel: In ca. 15 Minuten von einem leeren Rechner zu einem exportierten, bootfähigen MP3-ISO.

> **Wichtigstes Ergebnis vorab:** Getestet wurde mit einem **PAL**-ISO (`RM3P01`), weil nur dieses
> vorlag. Mit den Standard-Optionen (Starter-Preset) funktioniert der Export für PAL und das ISO
> bootet bis Olympus. Die optionalen Patches „MP3Update“ und „Disable Deflicker“ funktionieren
> **nur mit NTSC-U (`RM3E01`)** und scheitern auf PAL (Details in Abschnitt 8).

Inhalt:

1. Voraussetzungen
2. Python-venv und Requirements
3. .NET-8-SDK und Patcher `MP3Randomizer` bauen
4. Seed generieren
5. ISO exportieren
6. Boot-Test in Dolphin
7. Unterstützte Spielversion (mit Belegen im Code)
8. Gescheiterte Schritte und Fehlermeldungen
9. Stolpersteine und Hinweise für die nächsten Tasks

Konventionen:

- `REPO` = Repo-Wurzel `corruptovania` (z. B. `C:\Projekte\corruptovania`).
- Das Original-ISO und alle Ausgaben liegen **außerhalb** des Repos (`..\mp3.iso`, `..\out\`).
  **Lege nie ein ISO im Repo ab.**
- Alle Build-Artefakte gehen nach `build/`, das per `.gitignore` (Zeile 8) ignoriert wird.
- Befehle sind für Git Bash geschrieben. Wenn es ein PowerShell-Äquivalent braucht, steht es dabei.

---

## 1. Voraussetzungen

| Werkzeug | Version (getestet) | Installation |
|---|---|---|
| Git | 2.56.0.windows.4 | https://git-scm.com |
| Python | 3.12.10, 64-bit (`py -3.12`) | python.org-Installer, Haken bei „py launcher“ setzen |
| .NET SDK | 8.0.428 | `winget install --id Microsoft.DotNet.SDK.8 -e` |
| Dolphin | 2609b (portable) | https://dolphin-emu.org/download/ (das winget-Paket `DolphinEmulator.Dolphin` ist veraltet, Version 5.0 von 2016) |
| Original-ISO | Metroid Prime 3: Corruption, Wii-Standalone | eigener Dump (siehe Abschnitt 7) |

Prüfen:

```bash
py -0p
```
```
 -V:3.12 *        C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe
```

```bash
"/c/Program Files/dotnet/dotnet.exe" --list-sdks
```
```
8.0.428 [C:\Program Files\dotnet\sdk]
```

> Falls `dotnet --list-sdks` leer ist („No SDKs were found“): Es ist nur die Runtime installiert.
> Dann das SDK installieren (Befehl in der Tabelle oben). Vorher war dieser Rechner genau in diesem Zustand
> (nur Runtimes 8.0.23 und 10.0.14).

Ausgabe der winget-Installation:
```
Downloading https://download.microsoft.com/download/.../dotnet-sdk-8.0.428-win-x64.exe
Successfully verified installer hash
Starting package install...
Successfully installed
```

In der aktuellen Git-Bash-Sitzung ist `dotnet` danach oft noch nicht im `PATH`. Entweder ein neues Terminal öffnen oder:

```bash
export PATH="/c/Program Files/dotnet:$PATH"
```

## 2. Python-venv und Requirements

```bash
cd REPO
py -3.12 tools/check_py_version.py
```
```
Using Python 3.12 (64-bit)
```

```bash
py -3.12 -m venv venv
venv/Scripts/python.exe --version
```
```
Python 3.12.10
```

```bash
venv/Scripts/python.exe -m pip install --upgrade -r requirements-setuptools.txt
venv/Scripts/python.exe -m pip install -e ".[gui]" -c requirements.txt
venv/Scripts/python.exe -m pip install -r requirements.txt
```
Ausgabe (gekürzt, Ende des 2. Befehls):
```
Successfully installed PySide6-Essentials-6.8.2.1 ... dolphin-memory-engine-1.3.0 ... nod-1.9.4 ... randovania-1.9.0.dev87 ...
```

**Wichtig:** Der dritte Befehl (`requirements.txt`) ist Pflicht. Erst damit wird z. B.
`open-prime-rando==0.15.1` installiert, das der Dolphin-Connector für MP3 braucht. Ohne ihn:
```
ModuleNotFoundError: No module named 'open_prime_rando'
```

Kontrolle:
```bash
venv/Scripts/python.exe -m randovania --version
```
```
Randovania 1.9.0.dev87 from ...\corruptovania\randovania
```

Hinweis: `tools/prepare_virtual_env.bat` macht im Wesentlichen dasselbe, ruft aber zusätzlich
`pre-commit install` auf (schreibt Git-Hooks). Für T01 wurde das bewusst weggelassen.

## 3. .NET-8-SDK und Patcher `MP3Randomizer` bauen

Der Patcher-Quellcode liegt in `tools/prime3_patcher/MP3Randomizer` (`net8.0`, siehe `MP3Randomizer.csproj`).

**Der Patcher muss als x86 (32-bit) gebaut werden.** Die mitgelieferte native Bibliothek
`randovania/data/gollop_mp3_patcher/lzokay/lzokay.dll` ist 32-bit (PE-Machine `0x14c`), genau wie die
mitgelieferte `MP3Randomizer.exe`. Ein x64-Build stürzt beim ersten komprimierten Bereich ab (Abschnitt 8, F2).
Auf dem Rechner ist keine x86-.NET-Runtime installiert, deshalb wird der Patcher self-contained veröffentlicht.

```bash
cd REPO
export PATH="/c/Program Files/dotnet:$PATH" DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
dotnet publish tools/prime3_patcher/MP3Randomizer/MP3Randomizer.csproj \
  -c Release -r win-x86 --self-contained true \
  --artifacts-path build/mp3r -o build/mp3r/publish
mkdir -p build/mp3r/publish/lzokay
cp randovania/data/gollop_mp3_patcher/lzokay/lzokay.dll build/mp3r/publish/lzokay/
```
```
  Restored ...\tools\prime3_patcher\MP3Randomizer\MP3Randomizer.csproj (in 2.69 sec).
  MP3Randomizer -> ...\build\mp3r\bin\MP3Randomizer\release_win-x86\MP3Randomizer.dll
  MP3Randomizer -> ...\build\mp3r\publish\
```

`--artifacts-path` sorgt dafür, dass `bin/` und `obj/` unter `build/` landen und nicht als ungetrackte
Ordner in `tools/prime3_patcher/MP3Randomizer/` (dort greift kein `.gitignore`).

Unit-Tests des Patchers:
```bash
dotnet test tools/prime3_patcher/MP3Randomizer.Tests/MP3Randomizer.Tests.csproj --artifacts-path build/mp3r-tests
```
```
Passed!  - Failed:     0, Passed:     2, Skipped:     0, Total:     2, Duration: 2 ms - MP3Randomizer.Tests.dll (net8.0)
```

Kurztest:
```bash
build/mp3r/publish/MP3Randomizer.exe --help
```
```
USAGE
MP3Randomizer.exe [FLAGS]

REQUIRED FLAGS
--input-path "INPUT_PATH"           Folder containing the pak files
--output-path "OUTPUT_PATH"         Folder to save the randomized paks to
--layout "LAYOUT"                   The item layout/seed
...
```

### Welcher Patcher wird beim Export benutzt?

Der Exporter ruft unter Windows **nicht** den selbst gebauten Patcher auf, sondern die eingecheckte
`randovania/data/gollop_mp3_patcher/MP3Randomizer.exe`
(`randovania/games/prime3/exporter/toolchain.py:82-94`, Pfad in Zeile 86).

Gleichwertigkeit geprüft: Beide Patcher wurden mit demselben Seed und denselben Flags auf die 13 Eingabedateien
des PAL-ISOs angewendet. Ergebnis: **alle 13 Ausgabedateien sind byte-identisch (SHA-256)**:
FrontEnd, Logbook, Metroid1/3/4/5/6/7/8, MiscData, UniverseArea, Worlds, Standard.ntwk.
Logbook.pak und MiscData.pak bleiben dabei unverändert.

Wer für T05 den eigenen Build im Exporter nutzen will, muss `MP3Randomizer.exe` plus Laufzeit-Dateien nach
`randovania/data/gollop_mp3_patcher/` legen. Das ist eine Änderung an eingecheckten Dateien und gehört in einen
eigenen Task.

## 4. Seed generieren

Für MP3 gibt es genau ein Preset: `randovania/games/prime3/presets/starter_preset.rdvpreset` („Starter Preset“).

```bash
cd REPO
mkdir -p build/seed
venv/Scripts/python.exe -m randovania layout generate-from-presets \
  --name "prime3/Starter Preset" --seed-number 1000 build/seed/t01.rdvgame
```
```
Permalink: DQUaavDSCSsKDyO7HiYpa-sH
Took 6.873 seconds. Hash: IVG2J7OR
```

Patch-Daten (die JSON, die der Exporter an den Patcher übergibt) ausgeben:
```bash
venv/Scripts/python.exe -m randovania layout patcher-data \
  --layout-file build/seed/t01.rdvgame --output build/seed/t01.patcher.json
```
Inhalt (gekürzt):
```
seed: 00kk44g44xtk944sdk444Cko{4rk^44}...
starting_items: custom 0000000010010000000001100100100000000010000
starting_location: custom c133f919c108bdf9 d8cf355d3e9e3741
random_door_colors: False, random_welding_colors: False
missile_required_mains: True, ship_missile_required_mains: True
phaaze_skip: False, mp3_update: False, disable_deflicker: False
```

Im Starter-Preset sind `mp3_update` und `disable_deflicker` aus. Deshalb funktioniert es auch mit PAL.

## 5. ISO exportieren

```bash
cd REPO
mkdir -p ../out
venv/Scripts/python.exe -m randovania layout export-game \
  --patcher-data build/seed/t01.patcher.json prime3 \
  --input-path "../mp3.iso" --output-path "../out/t01_IVG2J7OR.iso" --output-format iso
```
```
          [5.2274 INFO nod] Success!
[ 10%] Extracting ISO...
[ 20%] Removing attract videos...
[ 50%] Copying Paks...
[ 60%] Randomizing Paks...
[ 70%] Exporting to ISO...

real	0m54.902s
```
Ergebnis: `..\out\t01_IVG2J7OR.iso`, 4 519 067 648 Bytes. Der Exporter legt temporäre Ordner unter `%TEMP%` an
und räumt sie selbst wieder auf (geprüft). Freier Platz: etwa 3 × ISO-Größe, also rund 15 GB.

Kontrolle mit DolphinTool (siehe Abschnitt 6 für Dolphin):
```bash
DolphinTool.exe header -i "..\out\t01_IVG2J7OR.iso"
```
```
Internal Name: Metroid Prime 3: Corruption
Revision: 0
Game ID: RM3P01
Title ID: 00010000524d3350
Region: PAL
Country: Europe
```

Hinweis: Das CLI-Flag `--mp3-update` von `export-game prime3` hat keine Wirkung. Es landet in
`CorruptionGameExportParams.mp3_update` (`game_exporter.py:29`), der Exporter liest aber
`patch_data["mp3_update"]` (`game_exporter.py:100`). Das kommt aus dem Preset
(`corruption_configuration.py:17`, `patch_data_factory.py:50,118`).

## 6. Boot-Test in Dolphin

Dolphin portabel neben das Repo legen (nicht ins Repo):

```bash
cd "REPO/.."
mkdir -p tools/dl tools/dolphin
curl -sSL -o tools/dl/dolphin-2609b-x64.7z https://dl.dolphin-emu.org/releases/2609b/dolphin-2609b-x64.7z
/c/Windows/System32/tar.exe -xf tools/dl/dolphin-2609b-x64.7z -C tools/dolphin
touch tools/dolphin/Dolphin-x64/portable.txt
```

Steuerung per Tastatur und Maus. Diese Datei als `tools/dolphin/Dolphin-x64/User/Config/WiimoteNew.ini` anlegen.
MP3 verlangt einen Nunchuk, und der Zeiger muss an der Maus hängen. Wenn man den Zeiger auf Tasten legt,
springt er beim Loslassen in die Mitte zurück, und Menüs lassen sich so nicht bedienen.

```ini
[Wiimote1]
Device = DInput/0/Keyboard Mouse
Source = 1
Extension = Nunchuk
Buttons/A = F
Buttons/B = SPACE
Buttons/1 = `1`
Buttons/2 = `2`
Buttons/- = Q
Buttons/+ = E
Buttons/Home = H
D-Pad/Up = UP
D-Pad/Down = DOWN
D-Pad/Left = LEFT
D-Pad/Right = RIGHT
IR/Up = `Cursor Y-`
IR/Down = `Cursor Y+`
IR/Left = `Cursor X-`
IR/Right = `Cursor X+`
IR/Auto-Hide = False
Nunchuk/Buttons/C = C
Nunchuk/Buttons/Z = Z
Nunchuk/Stick/Up = W
Nunchuk/Stick/Down = S
Nunchuk/Stick/Left = A
Nunchuk/Stick/Right = D
[Wiimote2]
Source = 0
[Wiimote3]
Source = 0
[Wiimote4]
Source = 0
[BalanceBoard]
Source = 0
```

Optional `User/Config/Dolphin.ini` (Analytics-Abfrage aus, Spiel im Hauptfenster):
```ini
[Analytics]
PermissionAsked = True
Enabled = False
[Interface]
ConfirmStop = False
[Display]
RenderToMain = True
```

Starten:
```bash
tools/dolphin/Dolphin-x64/Dolphin.exe -b -e "C:\...\MP3 Archi\out\t01_IVG2J7OR.iso"
```

Ablauf und Beobachtung (2026-11-23, Dolphin 2609b, JIT64, Direct3D 11, HLE):

1. Fenstertitel: `Metroid Prime 3: Corruption (RM3P01)`. Das Nintendo/Retro-Intro läuft, mit A (`F`) überspringen.
2. Titelbildschirm „PRESS (A) TO START“ → A.
3. „Game Select“: Zeiger mit der Maus auf `[ New Game ]` → A, dann Mii wählen → A, dann `Game Start` → A.
4. „Main Menu“ → `[ Play Game ]` → A. „Select Difficulty“ → `[ Normal ]` → A.
5. Lebenserhaltungs-Text im Cryo-Schlaf, danach Spielbeginn auf der **G.F.S. Olympus**.
   Das HUD ist sichtbar (Energie 99, „Objective Completed“).
6. Mit `W` (Nunchuk-Stick) läuft Samus vorwärts. **Das Level ist spielbar.**

Beweis-Screenshot: `..\out\t01_boot_olympus.jpg` (außerhalb des Repos).

Tipp: Tasten mindestens ca. 0,3 s halten. Sehr kurze Tastendrücke erkennt das Spiel manchmal nicht.

## 7. Unterstützte Spielversion (mit Belegen im Code)

### Kurzfassung

| Version | Game-ID | Standard-Export (Starter-Preset) | Mit `MP3Update`/`disable_deflicker` | Dolphin-Connector |
|---|---|---|---|---|
| Wii-Standalone NTSC-U | **RM3E01** | erwartet ja (Ziel der Original-Skripte, hier nicht getestet: kein ISO vorhanden) | **ja**, die einzige Version, für die die hdiffs gebaut sind | ja („Wii NTSC“) |
| Wii-Standalone PAL | **RM3P01** (Rev 0) | **ja, getestet**: Export ok, bootet bis Olympus, spielbar | **nein**, hpatchz bricht ab (Abschnitt 8, F3) | ja („Wii PAL“), Speicher-Adressen in T02 prüfen |
| Wii-Standalone NTSC-J | RM3J01 | ungetestet | sicher nein (die hdiffs passen nur zu NTSC-U) | ja („Wii NTSC-J“) |
| Metroid Prime Trilogy (R3ME01/R3MP01) | R3M* | **nicht unterstützt**: kein Code-Pfad, keine Referenz | nein | nein (keine Trilogy-DOL-Version) |

**Für das MVP (E2):** Zielversion ist **Wii-Standalone NTSC-U `RM3E01`**. Nur damit stehen alle Patcher-Optionen
zur Verfügung. PAL `RM3P01` funktioniert ohne MP3Update/Deflicker und ist für die Entwicklung brauchbar.

### Belege

1. **Es gibt keine aktive Prüfung von Game-ID oder Hash.** Weder der Exporter
   (`randovania/games/prime3/exporter/game_exporter.py`, `toolchain.py`) noch der Patcher
   (`tools/prime3_patcher/MP3Randomizer/MP3Randomizer/*.cs`) lesen die Game-ID oder prüfen einen ISO-Hash.
   Die Suche nach `RM3`, `R3M`, `game_id`, `sha1`/`md5` über `randovania/games/prime3`, `tools/prime3_patcher` und
   den Connector findet nichts dazu. Der Export-Dialog prüft nur, ob die Datei existiert und auf `.iso` endet
   (`randovania/games/prime3/gui/dialog/game_export_dialog.py:73-77, 91-92`).
   Der Patcher arbeitet fest mit Paket-Dateinamen und Asset-IDs
   (`tools/prime3_patcher/MP3Randomizer/MP3Randomizer/MP3Randomizer.cs:51-66`).
2. **NTSC-U ist die implizite Zielversion der Patcher-Daten:**
   - `randovania/data/gollop_mp3_patcher/CreateWBFS.bat:1-2` schreibt fest
     `Metroid Prime 3 - Corruption [RM3E01]/RM3E01.wbfs`.
   - Die hdiff-Patches in `randovania/data/gollop_mp3_patcher/MP3Update/*.hdiff` speichern die erwartete
     Größe der Originaldatei. Diese stimmt für alle 11 Dateien nicht mit PAL überein. Beispiel `main.dol`:
     erwartet 6 045 952 Bytes, PAL hat 6 055 776 Bytes. Die Patches werden angewendet in
     `game_exporter.py:89-98` (Deflicker → `main.hdiff`) und `game_exporter.py:100-122` (MP3Update → 10 Paks).
3. **Der Dolphin-Connector kennt drei Wii-Standalone-DOLs, aber keine Trilogy-Version:**
   `randovania/game_connection/builder/prime_connector_builder.py:40,64` lädt
   `open_prime_rando.dol_patching.corruption.dol_versions.ALL_VERSIONS` (open-prime-rando 0.15.1, `dol_versions.py:9,33,50`):
   - „Wii NTSC“: `!#$MetroidBuildInfo!#$2007/07/27 13:13 Build v3.436 (MP3)`
   - „Wii PAL“: `!#$MetroidBuildInfo!#$2007/08/24 16:52 Build v3.453 (mp3)`
   - „Wii NTSC-J“: `!#$MetroidBuildInfo!#$2007/11/12 14:15 Build v3.495 (jpn)`
4. **Trilogy:** Im prime3-Code gibt es keinerlei Trilogy-Bezug. „Trilogy“ kommt nur bei den Teleportern von
   Prime 1 und 2 vor. Die Paketnamen in `MP3Randomizer.cs:51-52` (`Metroid1.pak` … `Worlds.pak`) entsprechen dem
   Standalone-Layout. Auf der Trilogy-Disc liegen die Spiele in Unterordnern je Spiel.
5. **Texte:** Der Patcher ersetzt Strings nur auf Englisch
   (`tools/prime3_patcher/MP3Randomizer/MP3Randomizer/STRGModificationData.cs:10ff`, `Language.English`).
   Bei PAL in einer anderen Systemsprache als Englisch sind Pickup-Texte daher vermutlich nicht oder gemischt
   angepasst. Ungetestet.

Verwendetes Test-ISO: `RM3P01`, Revision 0, MD5 `f4c734a1e191c45e9ac037d92e14485d` (laut `DolphinTool verify`),
4 699 979 776 Bytes.

## 8. Gescheiterte Schritte und Fehlermeldungen

**F1: Patcher als x64 gebaut** (`dotnet publish -r win-x64 --self-contained false`). Der Build klappt,
aber beim Ausführen kommt:
```
Unhandled exception. System.DllNotFoundException: Unable to load DLL 'lzokay' or one of its dependencies: The specified module could not be found. (0x8007007E)
   at MP3Randomizer.Compression.decompress(...)
   at MP3Randomizer.Compression.decompress_mrea_block(Byte[] compressed_b) in ...\Compression.cs:line 79
```
Ohne `lzokay.dll` neben der EXE fehlt die Datei. Mit DLL scheitert es trotzdem, weil die DLL 32-bit ist.
Suchpfade: `Compression.cs:33-39` (`<exe-dir>\lzokay.dll` oder `<exe-dir>\lzokay\lzokay.dll`).
**Lösung:** `-r win-x86 --self-contained true` und die DLL nach `publish/lzokay/` kopieren (Abschnitt 3).

**F2: `tools/prime3_patcher/compare_randomizer_outputs.py` kann so nicht laufen.**
```
Unhandled Exception: System.IO.FileNotFoundException: Could not find file '...\old-output\Standard.ntwk'.
   at MP3Randomizer.NTWK.modify_ntwk(String orig_tweak_location, String dest_tweak_location)
RuntimeError: Randomizer process failed with exit code 3762504530.
```
Das Skript legt einen leeren Ausgabeordner an. Der Patcher erwartet aber, dass `Standard.ntwk` dort schon existiert,
was im echten Export immer so ist (Ausgabe = extrahierter `DATA/files`). Außerdem übergibt das Skript
`--starting-items` als ein einziges Argument, was für `custom <bits>` nicht passt.
**Umgehung:** Beide Patcher von Hand mit vorbefüllten Ausgabeordnern laufen lassen und SHA-256 vergleichen
(Ergebnis in Abschnitt 3: identisch).

**F3: Export mit `mp3_update = true` auf PAL.** Getestet mit einer Kopie der Patch-JSON, in der `mp3_update` auf `true` steht:
```
[ 10%] Extracting ISO...
[ 20%] Removing attract videos...
[ 40%] Applying Update...
RuntimeError: Prime 3 helper failed (hpatchz.exe, exit code 6): ('...\hpatchz.exe', '-f', '...\DATA\files\FrontEnd.pak', '...\MP3Update\FrontEnd.hdiff', '...\DATA\files\FrontEnd.pak')
Helper output:
input oldFile oldDataSize 27923392 != diffFile saved oldDataSize 27951744 ERROR!
```
Einzeln geprüft, alle 11 hdiffs gegen PAL scheitern mit Exit-Code 6:

| Datei | PAL-Größe | vom hdiff erwartet |
|---|---|---|
| main.dol | 6 055 776 | 6 045 952 |
| FrontEnd.pak | 27 923 392 | 27 951 744 |
| InGameAudio.pak | 4 404 224 | 4 433 536 |
| NoARAM.pak | 16 658 752 | 16 181 824 |
| Metroid1.pak | 773 174 208 | 772 462 336 |
| Metroid3.pak | 698 251 328 | 695 588 608 |
| Metroid4.pak | 738 060 992 | 736 660 224 |
| Metroid5.pak | 577 712 320 | 576 161 856 |
| Metroid6.pak | 126 914 560 | 126 891 392 |
| Metroid7.pak | 158 443 456 | 157 911 168 |
| UniverseArea.pak | 15 069 440 | 15 059 840 |

Dasselbe gilt für `disable_deflicker` (`main.hdiff`). Hier wurde nur hpatchz direkt getestet, kein ganzer Export.

**F4: `winget install DolphinEmu.Dolphin`** → `No package found matching input criteria.` Die richtige ID ist
`DolphinEmulator.Dolphin`, aber das ist nur Version 5.0 (2016). Deshalb wird das portable Release 2609b verwendet.

**F5: Dolphin-Zeiger auf Tasten (I/J/K/L) gelegt.** Der Zeiger springt beim Loslassen in die Mitte zurück, und Menüpunkte
lassen sich nicht auswählen. Lösung: Zeiger an die Maus binden (`Cursor X±/Y±`, Abschnitt 6).

## 9. Stolpersteine und Hinweise für die nächsten Tasks

- **Option `--phaaze-skip`:** Die Hilfe des Patchers nennt `--skip-phaaze`
  (`tools/prime3_patcher/MP3Randomizer/MP3Randomizer/Configuration.cs:162`). Der Parser akzeptiert aber nur
  `--phaaze-skip`/`-phaaze-skip` (`Configuration.cs:85`), und das schickt der Exporter auch. Nur der Hilfetext ist falsch.
- **Mitgelieferte EXE:** `randovania/data/gollop_mp3_patcher/MP3Randomizer.exe` ist ein 32-bit-.NET-Framework-Build
  (das erkennt man am Stacktrace-Stil `System.IO.__Error.WinIOError`). Sie läuft ohne installierte .NET-8-Runtime.
- **T02 (Speicher-Mapping):** Der Connector unterstützt PAL über die Build-Kennung. Ob die PAL-Adressen in
  open-prime-rando stimmen, ist noch nicht geprüft. Das ist ein Kandidat für T02.
- **T05 (Patch-Pfad):** Der Patcher bekommt den Seed nur als `--layout`-String (Permalink-Format von Gollop), nicht als
  JSON (`game_exporter.py:224-255`). Für AP-Platzhalter-Items muss also entweder dieses Format oder der Patcher erweitert werden.
- **Ein NTSC-U-ISO (`RM3E01`) wird gebraucht**, um MP3Update/Deflicker und die eigentliche MVP-Zielversion zu testen.
