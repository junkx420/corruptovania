# AP-Patcher-Analyse: MP3Randomizer und Exporter (T09)

Stand: 2026-11-23. Nur gelesen, kein Code im Repo geändert. Beantwortet die vier Fragen aus `STATUS.md` (T09) als
Eingabe für F-01 (Location-Check-Erkennung und Item-Vergabe von außen).

Quellen und Konventionen:
- `PATCHER/` = `tools/prime3_patcher/MP3Randomizer/MP3Randomizer/` (C#, `net8.0`). `ItemName.cs` liegt eine Ebene höher
  in `tools/prime3_patcher/MP3Randomizer/`.
- `EXP/` = `randovania/games/prime3/exporter/`. `GOLLOP` = `randovania/games/prime3/patcher/gollop_corruption_patcher.py`.
- `OPR/` = `venv/Lib/site-packages/open_prime_rando/dol_patching/` (open-prime-rando 0.15.1, im Repo nicht eingecheckt).
- **Eigene Messung an der PAL-`main.dol` (`RM3P01`)**: Die Datei wurde nur gelesen und nur im Scratchpad analysiert. Belege
  dafür sind virtuelle Wii-Adressen, keine Zeilennummern. Das Skript steht in Abschnitt 8, damit man es wiederholen kann.
- Alles, was nur aus Code geschlossen wurde und nicht live im Spiel gezeigt ist, steht als **ungeprüft** oder
  **Schluss** da.

> **Kurzfassung**
> 1. Im Patch-JSON hat ein Pickup **kein einziges eigenes Feld**. Alle 100 Pickups stecken als je ein Buchstabe im String
>    `seed`. Item-ID, Modell, Text und Menge kommen aus der festen C#-Tabelle `Item.cs`.
> 2. `ItemName.cs` (57 Einträge) sind **Patcher-Namen, keine Inventar-IDs**. Die Inventar-Slots (0–69) sind im Spiel über
>    eine sortierte **Hash→Slot-Tabelle in `main.dol`** (59 Einträge) adressiert. Der Patcher schreibt pro Pickup den
>    4-Byte-Hash (`item_type`), nicht den Slot.
> 3. **Frei und per Pickup adressierbar ist nur Slot 47.** Die Slots 43 und 53–61 sind frei, haben aber keinen Hash.
>    Die Slots 68 und 69 nutzt der Patcher schon selbst als „temporäre“ Marker-Items. Das ist der Beweis, dass ein
>    Pickup einen Stat-Slot als Marker geben kann.
> 4. Der Patcher fasst `main.dol` **nicht** an. Die DOL wird nur im Exporter per `hpatchz` verändert (Deflicker, nur
>    NTSC-U). Ein eigener Hook ist machbar, aber nur mit Reverse-Engineering-Aufwand.

---

## 1. Wie kommt ein Pickup vom Patch-JSON ins Spiel?

### 1.1 Datenfluss

```
Randovania-Layout (patches.pickup_assignment)
  └─ CorruptionPatchDataFactory.create_game_specific_data        EXP/patch_data_factory.py:18
       ├─ pickup_names[0..99]  (leerer Index = "Missile Expansion")      :26-33
       └─ layout_string_for_items(pickup_names) → String "seed"          :35 → GOLLOP:188-197
  └─ Patch-JSON (11 Schlüssel, Tabelle 1.2)                              :108-120
  └─ CorruptionGameExporter._do_export_game                              EXP/game_exporter.py:60
       ├─ ISO entpacken (DATA/files, DATA/sys)                           :78-79
       ├─ optional main.dol per hdiff (nur NTSC-U)                       :89-98
       ├─ 13 Dateien nach paks_path kopieren                             :124-144
       └─ MP3Randomizer.exe --layout <seed> --starting-items ... aufrufen  :146-150 und :236-255
            └─ MP3Randomizer.Main                                        PATCHER/MP3Randomizer.cs:10
                 1. Argumente lesen (--layout = encoded_permalink)       PATCHER/Configuration.cs:65-67
                 2. decode_permalink: String → ItemName[]                PATCHER/MP3Randomizer.cs:13, MP3Permalink.cs:12
                 3. Main-required-Varianten austauschen                  PATCHER/MP3Randomizer.cs:14-32
                 4. Patches.add_patches: alle Spiel-Patches sammeln      PATCHER/MP3Randomizer.cs:50, Patches.cs:268-329
                 5. PAK.modify_pak je Pak, danach NTWK                   PATCHER/MP3Randomizer.cs:51-66, PAK.cs:94-121
       └─ WIT baut aus DATA das ISO                                      EXP/game_exporter.py:152-159
```

### 1.2 Felder im Patch-JSON

Quelle: `EXP/patch_data_factory.py:108-120` (plus `_randovania_meta`, das das Framework ergänzt; Beispiel
`build/seed/t01.patcher.json`).

| Schlüssel | Inhalt | Von wem gelesen |
|---|---|---|
| `commands` | `set`-Zeilen im Stil von `randovania/data/gollop_mp3_patcher/RandomizePaks.bat:1` | von niemandem (der Exporter liest sie nicht) |
| `seed` | Layout-String: 2 Rotations-Zeichen + 100 Pickup-Zeichen + 5 Hex-Zeichen SHA-256-Prüfsumme | `EXP/game_exporter.py:242-243` → `--layout` |
| `starting_items` | `custom <43 Hexziffern>` | `game_exporter.py:231,244-245` → `--starting-items` |
| `starting_location` | `custom <Welt-ID> <Raum-ID>` | `game_exporter.py:232,246-247` |
| `random_door_colors`, `random_welding_colors` | bool | `game_exporter.py:248-249` |
| `missile_required_mains`, `ship_missile_required_mains` | bool | `game_exporter.py:252-253` |
| `phaaze_skip` | bool | `game_exporter.py:254` |
| `mp3_update`, `disable_deflicker` | bool | `game_exporter.py:89,100` (Exporter, nicht der Patcher) |

**Ein Pickup hat im JSON weder Item-ID noch Modell noch Text noch Anzahl.** Es gibt genau ein Zeichen pro Pickup-Index:
- Der Index kommt aus dem Randovania-Pickup-Index 0–99 (`patch_data_factory.py:26-33`). Ein unbesetzter Index wird zu
  `"Missile Expansion"` (`:31-32`). Für den Index 0–99 gibt es 100 Pickup-Knoten in der Datenbank (geprüft, lückenlos).
- Das Zeichen kommt aus `LETTER_TO_ITEM_MAPPING` (`GOLLOP:47-127`). Ein Item ohne Buchstaben löst in Python einen
  `KeyError` aus (`GOLLOP:128,195`).
- Das Alphabet ist `LAYOUT_LETTERS` (`GOLLOP:13`). Die ersten beiden Zeichen (`"00"`, `GOLLOP:189`) bedeuten „keine
  Rotation“. Der C#-Decoder rotiert sonst (`MP3Permalink.cs:14-15,255`).
- Die Prüfsumme sind die ersten 5 Hex-Zeichen von SHA-256 über den Rest (`GOLLOP:194-195`, geprüft in
  `MP3Permalink.cs:18-24`, Fehler = `ArgumentException`).
- Das Pickup-Modell eines Fremdwelt-Items gibt es nicht. Die Pickup-Datenbank hat nur den leeren Schlüssel
  `default_offworld_model` (`pickup_database/pickup-database.json:776`), und die Patch-Daten kennen ihn nicht.

### 1.3 Was der Patcher je Item festlegt (`Item.cs`)

Der Decoder macht aus dem Zeichen einen `ItemName` (`MP3Permalink.cs:35-253`). `Item.get_item_data(ItemName)`
(`PATCHER/Item.cs:43`) liefert dann ein Objekt mit diesen Feldern (`Item.cs:7-41`):

| Feld | Größe | Bedeutung | Wohin geschrieben (Property-ID) | Zeile |
|---|---|---|---|---|
| `item_type` | 4 B | **Hash des Inventar-Slots** (siehe 2.2). `FF FF FF FF` = kein Inventar-Item (Progressive) | PCKP `A0 2E F0 C4` | `PickupPatches.cs:68` |
| `capacity` | 4 B | Kapazitäts-Zuwachs (Missile Expansion = 5, Suit = 5, Ship Missile = 3, sonst 1) | PCKP `28 C7 1B 54` | `:69`, `Item.cs:134,478,715` |
| `amount` | 4 B | Mengen-Zuwachs | PCKP `94 AF 14 45` | `:70` |
| `model` | 8 B | Asset-ID CMDL (statisches Modell). `FF…FF` = keins; nur die Energy Cells setzen es | PCKP `C2 7F FA 8F` | `:71`, `Item.cs:558` |
| `character` + `default_animation` | 8 B + 4 B | Asset-ID CHAR (animiertes Modell) plus Animation. Das ist das sichtbare Pickup-Modell | PCKP `A2 44 C9 D8` | `:72`, `:30-41` |
| `scan` | 8 B | Asset-ID SCAN (Scan-Text) | PCKP `B9 4E 9B E7` | `:73` |
| `pickup_effect` | 8 B | Asset-ID PART (Partikeleffekt) | PCKP `A9 FE 87 2A` | `:74` |
| `streamed_audio` | 8 B | Asset-ID STRM (Jingle) | STAU `9D 1A 67 A8` | `:94` |
| `memo` | 8 B | Asset-ID STRG (HUD-Meldung, z. B. „Plasma Beam acquired!“) | MEMO `91 82 25 0C` | `:95` |
| `percent` | 4 B | wird gesetzt, aber **nie ausgewertet** (keine Verwendung außerhalb `Item.cs`) | – | `Item.cs:11` |
| `is_progressive`, `progressive_*` | – | Progressive Beam/Missile (zwei Inventar-Geber im Raum) | – | `PickupPatches.cs:235-281` |
| `conversion_start_*`, `conversion_end_*` | – | Main-required-Varianten (siehe 3.1) | – | `PickupPatches.cs:109-234` |

Menge und Text sind also an den `ItemName` gebunden. Ein Pickup mit z. B. „Plasma Beam, 3 Stück, eigener Text“ lässt sich
heute nicht ausdrücken.

### 1.4 Welche Spielstrukturen schreibt der Patcher?

| Struktur | Was | Zeile |
|---|---|---|
| Skript-Objekt **PCKP** (Pickup) im MREA-Skript des Raums | Itemtyp, Kapazität, Menge, Modell, Scan, Effekt (7 Properties) | `PickupPatches.cs:66-75` |
| Skript-Objekt **SPFN** (Special Function) | bei den 10 Orten vom Typ `SpecialFunction` (Index 0, 9, 34, 42, 43, 62, 70, 73, 79, 89): SPFN wird umkonfiguriert, ein **zweites PCKP** (`percentage_pickup_id`) bekommt Typ, Kapazität, Menge | `:78-91`, `PickupLocations.cs:11,20,45,53,54,73,81,84,90,100` |
| **STAU**, **MEMO** | Jingle und HUD-Text je Ort; optional HUD-Typ ändern | `:94-107` |
| **Neue Skript-Objekte** (Conditional Relay, Inventory Giver/Taker) und **Verbindungen** | Progressive Items und Main-required-Umwandlung | `:109-281`, `SpecialFunction.cs:7-53`, `ConditionalRelay.cs:7-52` |
| **Abhängigkeitslisten** je MREA (CMDL, PART, CHAR, SCAN, STRG, STRM) | damit das Modell im Raum geladen wird | `:46-64`, `MP3Dependencies.cs:9,1575,1601` |
| **STRG-Ressourcen** (Texte) | 32 feste englische Strings (+2 optionale Hyper-Hints), davon 10 mit synthetischen IDs `0xABCDABCDABCD00xx` | `STRGModificationData.cs:10-41` (Hints `:42-56`), `StringPatches.cs:7-23`, `Item.cs:78` |
| **Fake-Pickups** | 19 Anzeige-Objekte (nur Modell, Scan, kein Itemtyp), die das Item von Index n zeigen | `PickupPatches.cs:424-465`, `FakePickupLocations.cs:8` |
| **Startinventar**: SPWN-Objekt im Startraum | 30 Properties (Mengen, Kapazitäten, Flags je Item) | `StartPatches.cs:236-287`, `MP3Inventory.cs:5-87` |
| Startort (TEL1), Karte aufdecken (1 Timer + 22 AVMC) | – | `StartPatches.cs:7-234,289-296` |
| etwa 40 weitere Raumpatches (Cutscenes, Türen, Fixes) | – | `Patches.cs:270-316` |
| `Standard.ntwk` (Tweaks) | – | `MP3Randomizer.cs:66` |

**Nicht geschrieben:** `main.dol`, Speicherstand, Bootdateien. Der Patcher ändert nur 10 Paks (`MP3Randomizer.cs:52`)
und `Standard.ntwk`.

### 1.5 Stolpersteine für Archipelago

- **Ort 0 wird nie gepatcht.** Die Schleife beginnt bei 1 (`PickupPatches.cs:12`). Eintrag 0 hat eine Dummy-MREA-ID
  `9999999999999999998` (`PickupLocations.cs:11`) und ist in der Datenbank „Pickup (Phazon Enhancement Device)“ in
  MedLab Delta (Olympus). Im Layout steht dort trotzdem ein Zeichen (im Seed `IVG2J7OR` ein Energy Tank). Er hat im Spiel
  keine Wirkung. Für AP bleiben 99 patchbare Orte.
- **Genau 100 Orte, fest verdrahtet:** `new PickupLocation[100]` (`PickupLocations.cs:9`). Mehr Orte erfordern neue Einträge
  mit Skript-Instanz-IDs aus den Paks.
- **Python und C# sind nicht deckungsgleich:** Python kennt `L` = CannonBall (`GOLLOP:95`), der C#-Decoder nicht
  (`MP3Permalink.cs:252-253` wirft „Unsupported character“). `0` (Power Beam) und alle auskommentierten Buchstaben
  (`GOLLOP:66-106`) fehlen ebenfalls in C#.
- **Texte nur Englisch** (`STRGModificationData.cs:10ff`, `Language.English`). Auf PAL in anderer Systemsprache ist das
  Verhalten ungeprüft (schon in `AP_DEV_SETUP.md`, Abschnitt 7).
- **Der Patcher bekommt nur den Seed-String** (`--layout`), nicht das JSON (`game_exporter.py:224-255`). Neue Felder
  (Marker, Text) brauchen entweder ein neues CLI-Argument oder ein neues Zeichen-Alphabet.

---

## 2. Inventar-Item-IDs, ungenutzte Slots und Abgleich mit `AP_MEMORY_MAP.md`

### 2.1 Zwei verschiedene „IDs“

| Begriff | Wo | Umfang |
|---|---|---|
| `ItemName` | `tools/prime3_patcher/MP3Randomizer/ItemName.cs:1-60` | 57 Patcher-Namen (Enum-Index 0–56). **Nicht** die Spiel-ID |
| Item-Hash (`item_type`) | `Item.cs` je Variante, Spalte `specific` in `logic_database/header.json` | 4 Byte, z. B. Plasma Beam `0x93AD6DF9` |
| Inventar-Slot (`item_id`) | `header.json` (`extra.item_id`), Speicher `PS + 0x54 + id * 0xC` (`AP_MEMORY_MAP.md:61`) | 0–69 |

**Von den 57 `ItemName`-Einträgen sind 44 in `Item.get_item_data` implementiert.** Die 13 übrigen sind Echoes-Reste
(`DarkBeam`, `LightBeam`, `AnnihilatorBeam`, `BeamAmmoExpansion`, `DarkSuit`, `LigthSuit`, `DarkVisor`, `EchoVisor`,
`SeekerLauncher`, vier Translators; `ItemName.cs:47-59`). Sie werfen `ArgumentException("Unsupported item")`
(`Item.cs:813-814`) und haben auch kein Zeichen im Decoder.

Der Hash im Patcher ist **identisch** mit `extra.specific` aus `header.json` (alle 38 benutzten Hashes
abgeglichen, z. B. Plasma Beam `147,173,109,249` = `2477616633` = `0x93AD6DF9`, `Item.cs:49`).

### 2.2 Die Hash→Slot-Tabelle in `main.dol` (eigene Messung, PAL)

In der PAL-`main.dol` liegt bei **`0x80584AB8`–`0x80584C88`** (Dateioffset `0x580B98`–`0x580D68`) eine nach Hash
sortierte Tabelle mit **59 Einträgen** à 8 Byte: `u32 Hash, u32 Slot`. Beispiel: `93AD6DF9 00000001` = Plasma Beam →
Slot 1. Der Code greift auf den Anfang und das Ende per `lis r5,0x8058 / addi r5,r5,0x4AB8` (`0x802DA564`/`0x802DA568`)
und `addi …,0x4C90` (`0x802DACA8`) zu. Das ist ein Opcode-Muster, **ich habe die Funktion nicht disassembliert**. Dass die
Tabelle per Binärsuche den PCKP-Hash in einen Slot übersetzt, ist ein **Schluss** und nicht live gezeigt. Er passt dazu,
dass die Tabelle sortiert ist und der Patcher die Hashes genau so schreibt.

Weitere Messwerte:
- Alle 58 Hashes aus `header.json` stehen in der Tabelle, jeder genau einmal. Dazu kommt **ein Eintrag, der nicht in
  `header.json` steht: `0x51E1A9FB` → Slot 47**.
- `add_power_up`, `incr_pickup`, `decr_pickup` (PAL `0x80191E2C`, `0x801920B0`, `0x8019222C`, Adressen aus
  `AP_MEMORY_MAP.md:38-40`) beginnen jeweils mit `stwu r1,-0x20(r1)`, `mflr r0`, **`cmplwi r4,0x45`**. Das Spiel
  akzeptiert also Slots **0 bis 69** (0x45). Die Funktionsadressen sind damit zum ersten Mal an der echten PAL-DOL bestätigt.

### 2.3 Alle Slots 0–69

„Pickup-Nutzung“ = `ItemName`-Varianten des Patchers, die diesen Hash als `item_type` schreiben (`Item.cs`).
Fehlt der Eintrag, schreibt der Patcher den Slot nie über ein Pickup.

| Slot | Hash (PAL-Tabelle) | Name (`header.json`) | Pickup-Nutzung im Patcher |
|---|---|---|---|
| 0 | `0xFB73F2B8` | PowerBeam | – (Startitem, kein Zeichen `0` in C#) |
| 1 | `0x93AD6DF9` | PlasmaBeam | PlasmaBeam |
| 2 | `0x50A0AAA5` | NovaBeam | NovaBeam |
| 3 | `0x35488520` | ChargeUpgrade | ChargeUpgrade |
| 4 | `0x922DA6A8` | Missile | MissileExpansion, MissileLauncher, ConverterMissileLauncher |
| 5 | `0x90F0CED4` | IceMissile | IceMissile |
| 6 | `0xB7F4E76D` | Seekers | SeekerMissile |
| 7 | `0x719B5C5D` | GrappleBeamPull | GrappleLasso |
| 8 | `0x1F2950DC` | GrappleBeamSwing | GrappleSwing |
| 9 | `0x1FF64711` | GrappleBeamVoltage | GrappleVoltage |
| 10 | `0xB9876CD1` | Bomb | Bomb |
| 11 | `0x96664E97` | CombatVisor | CombatVisor |
| 12 | `0xB3CADC47` | ScanVisor | ScanVisor |
| 13 | `0x73D674EA` | CommandVisor | CommandVisor |
| 14 | `0x662B235A` | XRayVisor | XRayVisor |
| 15 | `0x95C0052A` | DoubleJump | SpaceJump |
| 16 | `0xD9CD9EDE` | ScrewAttack | ScrewAttack |
| 17 | `0xD02B0AD8` | SuitType | Suit |
| 18 | `0x26B5C6C5` | Energy | – |
| 19 | `0x1D966CE8` | HypermodeEnergy | – |
| 20 | `0xB36AECDD` | EnergyTank | EnergyTank |
| 21 | `0x50499B43` | ItemPercentage | – |
| 22 | `0xABBC4C2E` | Fuses | – |
| 23–31 | `0x336E6C92` … `0x3DB5E4A0` | Fuse1 … Fuse9 | Fuse1 … Fuse9 |
| 32 | `0x482F8235` | MorphBall | MorphBall |
| 33 | `0xB21BB8C7` | BoostBall | BoostBall |
| 34 | `0x4D415752` | SpiderBall | SpiderBall |
| 35 | `0x5568B8C9` | HyperModeTank | HyperModeTank |
| 36 | `0x49E8A1AC` | HyperModeBeam | – |
| 37 | `0x515556A0` | HyperModeMissile | HyperMissile |
| 38 | `0x8C4847AB` | HyperModeBall | HyperBall |
| 39 | `0x87560845` | HyperModeGrapple | HyperGrapple |
| 40 | `0x8FEBB10D` | HyperModePermanent | – |
| 41 | `0xF4FFB39D` | HyperModePhaaze | – |
| 42 | `0xE5BA1551` | HyperModeOriginal | – |
| **43** | **kein Eintrag** | – (Lücke in `header.json`) | – |
| 44 | `0x57A20D1A` | ShipGrapple | ShipGrapple |
| 45 | `0x81A153FF` | ShipMissile | ShipMissileExpansion, ShipMissile, ConverterShipMissile |
| 46 | `0x7DC366E4` | FaceCorruptionLevel | – |
| **47** | `0x51E1A9FB` | – (nicht in `header.json`) | – |
| 48 | `0x7B6A8F3A` | CannonBall | – (`L` fehlt im C#-Decoder) |
| 49 | `0xB42B43DE` | ActivateMorphballBoost | – |
| 50 | `0x898D3214` | HyperShot | – |
| 51 | `0x3F82745E` | CommandVisorJammed | – |
| 52 | kein Eintrag | EnergyCellsUsed (`header.json`, ohne Hash) | – |
| **53–61** | **kein Eintrag** | – (nicht in `header.json`) | – |
| 62–67 | `0xC05C27EB` … `0x47E7BCEA` | Stat_EnemiesKilled … Stat_CommandoKills | – |
| **68** | `0x22390F26` | Stat_TinCanHighScore | **MainRequiredMissileExpansion** (`Item.cs:152-171`) |
| **69** | `0x38BE4C42` | Stat_TinCanCurrentScore | **MainRequiredShipMissileExpansion** (`Item.cs:773-792`) |

Die IDs 1000–1003 (`MissileLauncher`, `ShipMissileLauncher`, `TemporaryMissile`, `TemporaryShipMissile`) sind reine
Logik-Ressourcen ohne Slot und ohne Hash (`header.json`, `AP_MEMORY_MAP.md:117`).

### 2.4 Freie bzw. ungenutzte Slots, mit Begründung

„Frei“ heißt hier: weder der Patcher noch die Randovania-Datenbank belegen den Slot, und es gibt keinen Beleg für
eine Nutzung im Spiel. **Dass das Spiel einen Slot nie liest, ist statisch nicht zu beweisen.** Das Spiel hat den Slot
im Array (Index ≤ 69), und kein Wert wurde je darin beobachtet. Der Beweis braucht einen Live-Test (Abschnitt 5).

| Slot | Hash-adressierbar per Pickup? | Status | Begründung |
|---|---|---|---|
| **47** | **ja** (`0x51E1A9FB`) | **bester Kandidat** | Steht in der DOL-Tabelle, aber in keiner Randovania-/Patcher-Datei (`header.json`, `Item.cs`, `MP3Inventory.cs`). `GOLLOP:94` nennt für die Lücke zwischen `FaceCorruptionLevel` (46) und `CannonBall` (48) den Namen „PhazonBall“ (auskommentiert, wohl abgeschnittenes Feature). Das ist ein Hinweis aus einem Kommentar, **ungeprüft**. Max. Kapazität des Slots unbekannt |
| **43** | nein (kein Hash) | frei, aber nur schreibbar | Lücke zwischen 42 und 44 in `header.json` und in der DOL-Tabelle. **Vorbehalt:** Das Startinventar-Struct hat ein Feld `HyperModeCharge` (`StartPatches.cs:285`, `MP3Inventory.cs:81`), das `header.json` nicht kennt. Es könnte zu Slot 43 gehören, **ungeprüft** |
| **53–61** | nein (kein Hash) | frei, aber nur schreibbar | In keiner Quelle genannt. Die Stats beginnen bei 62 (`header.json`). Das Array reicht bis 69 (`cmplwi r4,0x45`), also existieren die Slots |
| 52 | nein (kein Hash) | unklar | `header.json` kennt `EnergyCellsUsed` (Max 9, `AP_MEMORY_MAP.md:115`) ohne Hash. Ob das Spiel selbst den Slot nutzt, ist offen |
| 68, 69 | ja | **vom Patcher belegt**, frei nur mit `missile_required_mains = false` und `ship_missile_required_mains = false` | `MP3Randomizer.cs:16-23` ersetzt Missile Expansion / Ship Missile Expansion durch die Main-required-Varianten, deren `item_type` diese zwei Stat-Hashes sind. Das Starter-Preset hat beide Flags auf `true` (`build/seed/t01.patcher.json`) |
| 62–67 | ja | nicht frei | Das Spiel zählt selbst: 63 und 64 live bestätigt (`AP_MEMORY_MAP.md:272-273`). 62, 65 bis 67 nach Namen ebenfalls, nicht live gesehen |
| 18–19, 21–22, 36, 40–42, 46, 49–51 | ja | nicht frei | Zustand des Spiels (Energie, Hypermode, Gesichtsverderbnis, Flags). Der Patcher schreibt sie nur als Startwerte, nicht per Pickup |

### 2.5 Abgleich mit `docs/AP_MEMORY_MAP.md`

| Punkt in `AP_MEMORY_MAP.md` | Befund | Folge |
|---|---|---|
| Zeile 119: „IDs 43, 47 und 53–61 fehlen in `header.json`“ | stimmt. Aber **47 hat einen Hash in der DOL**, 43 und 53–61 haben keinen | 47 ist per Pickup adressierbar, 43/53–61 nicht |
| Zeile 117 und 189-190: `TemporaryMissile` (1002) „nicht im Speicher“ | Auf der Spielseite liegt die Ladung wahrscheinlich in **Slot 68** (`Stat_TinCanHighScore`) und die Ship-Missile-Ladung in Slot 69. Das folgt aus `Item.cs:152-171,773-792` und den Hashes. **Aus Code abgeleitet, nicht live gemessen.** T02 nennt beim ersten Pickup nur `ItemPercentage` +1 (`AP_MEMORY_MAP.md:271`), Slot 68 wird dort nicht erwähnt. Ob das Watch-Log ihn zeigte, ist offen | Eine „Locked Missile Expansion“ müsste Slot 68 um 5 erhöhen, solange der Missile Launcher fehlt. Leicht live zu prüfen |
| Zeile 199: Zähler-Item „zum Beispiel einen ungenutzten Slot (43, 47, 53–61)“ | Per Pickup kann der Patcher heute nur Slots mit Hash schreiben. Das schließt 43 und 53–61 aus | siehe Abschnitt 3 |

---

## 3. Kann ein Pickup ein beliebiges Inventar-Item mit eigener ID geben?

**Ja, mit Einschränkungen.** Der Patcher schreibt nur den 4-Byte-Hash (`PickupPatches.cs:68`). Es gibt keinen Whitelist-Check
außer dem `switch` in `Item.get_item_data` (`Item.cs:46-815`). Es gibt zwei Beweise dafür, dass das Spiel Hashes von
Slots akzeptiert, die kein „echtes“ Item sind:
- **Slots 68 und 69** sind Stat-Zähler. Der Patcher gibt sie heute schon als Marker aus
  (`Item.cs:152-171,773-792`), und die Umwandlung in echte Raketen läuft über Relais (`PickupPatches.cs:109-234`).
- Progressive Items kommen ganz ohne Inventar-Hash aus: `item_type = FF FF FF FF` plus zwei Inventory-Geber-Objekte
  (`Item.cs:69,233`, `PickupPatches.cs:259-280`).

Ein Marker pro Location mit eigener ID stößt aber an **drei Grenzen**:

| Grenze | Befund |
|---|---|
| **Zu wenige Slots** | Hash-adressierbar und frei ist nur Slot 47 (plus 68/69, wenn man die Main-required-Flags abschaltet). 99 Orte bräuchten 99 Slots. Die 11 Slots ohne Hash (43, 52–61) sind per Pickup unerreichbar |
| **Unbekannte Klemmung** | Das Spiel hat je Slot eine maximale Kapazität (Missile 255, Stats 99999, `AP_MEMORY_MAP.md:78-116`). Für 43, 47 und 53–61 ist sie unbekannt. Ist sie 0 oder 1, verschwinden Mengen-Bits |
| **Menge ist additiv** | Ein Pickup erhöht `amount`/`capacity` (live: ItemPercentage 0/100 → 1/101, `AP_MEMORY_MAP.md:271`). Zwei Pickups desselben Slots addieren sich |

### 3.1 Möglichkeiten und ihr Aufwand

| Variante | Idee | Bewertung |
|---|---|---|
| **A. Bitmaske in `amount`/`capacity`** | Jeder Ort addiert `2^k` zu einem Marker-Slot. Eine Summe aus verschiedenen Zweierpotenzen ist eindeutig zerlegbar | Braucht 99 Bits. Stat-Slots (Max 99999) tragen höchstens 16 Bit je Feld. 3 Slots (47, 68, 69) × 2 Felder × 16 Bit = 96 Bit, also knapp zu wenig, falls Slot 47 nicht mehr trägt. Hängt komplett von der Klemmung ab (ungeprüft). **Bedingt machbar** |
| **B. DOL-Tabelle erweitern** | Hash-Einträge für 43, 52–61 ergänzen (11 Slots mehr) | Weiter nur 12–13 Slots. Hilft nicht für 99 Orte, verlangt zusätzlich einen DOL-Patch (Abschnitt 4) |
| **C. Zähler-Item (nur Anzahl)** | Jeder Pickup erhöht einen Zähler um 1. Der Client sieht „es kam einer dazu“, aber nicht welcher | Reicht nicht für eindeutige Checks. Als Plausibilitätsprüfung brauchbar (ItemPercentage macht das schon) |
| **D. Ereignis-Hook in der DOL** | Hook in `add_power_up`/`incr_pickup` schreibt (Slot, Delta) in einen Ringpuffer | Der Hook sieht die Argumente **vor** jeder Klemmung. Mit eindeutigem Delta je Ort (`amount = Ort-ID + 1` im Slot 47) ist der Ort im Puffer eindeutig, ohne dass Mengen sich addieren müssen. Braucht den DOL-Patch aus Abschnitt 4 |

### 3.2 Was im Patcher dafür zu ändern wäre (nur beschrieben)

Für ein neutrales „AP-Item“ (Modell + Text) und einen Marker je Ort:

1. **`ItemName.cs:1-60`**: neuen Eintrag `APItem` (oder je Marker-Typ einen) ergänzen. Alternativ einen der 13 toten
   Echoes-Einträge umwidmen, um die Enum-Reihenfolge nicht zu ändern.
2. **`Item.cs:43-815`**: neuen `case` mit `item_type` = Hash des Marker-Slots (für 47: `51 E1 A9 FB`), `capacity`/`amount`
   (die Marker-Menge), `model`/`character`/`scan`/`pickup_effect`/`memo`/`streamed_audio`. Die Menge je Ort ist heute
   nicht parametrierbar (Menge steckt im `ItemName`). Für „ein Marker je Ort“ müsste `get_item_data` zusätzlich den
   Ort-Index bekommen (`PickupPatches.cs:29`: `Item.get_item_data(item_list[j])`, der Index `j` ist dort vorhanden).
3. **Modell und Text:** nur Assets, die in `MP3Dependencies.get_file_dependencies()` (`MP3Dependencies.cs:9`) stehen. Für
   Unbekanntes bricht `PAK.gather_resources` mit „Failed to find dependency“ ab (`PAK.cs:73-90`). Ein neutrales Modell kann
   man ohne Eingriff aus vorhandenen Items wiederverwenden (z. B. das generische Kugelmodell der Energy Cells,
   `Item.cs:558`). Ein eigener Text braucht einen STRG-Eintrag. Neue IDs gehen, siehe die synthetischen
   `0xABCDABCDABCD00xx` (`Item.cs:78,242`, `STRGModificationData.cs:40-41`). Für 99 individuelle Texte („Sent Hookshot
   to Player2“) wären es 99 neue STRG-Ressourcen. Das Skalieren darauf ist **ungeprüft**.
4. **`MP3Permalink.cs:35-253`**: ein neues Zeichen für den AP-Typ. Der Decoder rechnet je Zeichen genau ein Item. Die
   100-Orte-Marker passen so nicht hinein. Sauberer ist ein **zweiter Parameter**, z. B. `--ap-markers <Liste>` mit je Ort
   einer Marker-Zahl (`Configuration.cs:65ff` kennt das Muster für Argumente).
5. **`EXP/patch_data_factory.py:26-35,108-120`** und **`GOLLOP:47-127,188-197`**: Patch-JSON um die Marker-Liste ergänzen,
   `_build_randomizer_command` (`game_exporter.py:224-255`) erweitern. Der Exporter nutzt unter Windows heute die
   eingecheckte `MP3Randomizer.exe` (`toolchain.py:86`), nicht den Quelltext (`AP_DEV_SETUP.md`, Abschnitt 3). Ein geänderter
   Patcher braucht einen neuen win-x86-Build in `randovania/data/gollop_mp3_patcher/` (Eingecheckte Binärdatei, siehe T05).
6. **Ort 0** bleibt unpatchbar (`PickupPatches.cs:12`), solange die Schleife bei 1 beginnt und die Dummy-MREA-ID gilt.

---

## 4. Verändert der Patcher `main.dol`?

**Nein.** Im Patcher-Quelltext gibt es keinen Zugriff auf `main.dol`, keine Adressen und keinen PowerPC-Code. Die Suche nach
`dol`, `ppc`, `hook`, `0x8…` über `tools/prime3_patcher` findet nur den Treffer `AppContext.BaseDirectory` in
`Compression.cs:33`. Der Patcher bekommt als Eingabe auch nur die Paks und `Standard.ntwk`
(`game_exporter.py:127-141`), nie die DOL.

Die einzige DOL-Änderung der ganzen Kette ist **im Exporter**:

| Schritt | Zeile | Wirkung |
|---|---|---|
| `hpatchz` wendet `MP3Update/main.hdiff` auf `DATA/sys/main.dol` an | `game_exporter.py:89-98`, `toolchain.py:27-28,87` | Deflicker abschalten. Der hdiff speichert die Größe der NTSC-U-DOL (6 045 952 B), die PAL-DOL (6 055 776 B) wird abgelehnt (`AP_DEV_SETUP.md`, Abschnitt 8, F3) |

### 4.1 Wäre ein eigener Hook machbar?

**Machbar mit Aufwand.** Was schon vorhanden ist und was fehlt:

| Baustein | Stand | Beleg |
|---|---|---|
| Stelle im Export, an der die DOL im Zugriff ist | vorhanden: `extract_path/DATA/sys/main.dol` wird schon bearbeitet | `game_exporter.py:95` |
| DOL-Editor und PowerPC-Assembler in Python | vorhanden in der venv (`ppc_asm`, von `open-prime-rando` benutzt): `DolEditor.write_instructions` | `venv/Lib/site-packages/ppc_asm/dol_file.py:74-116` |
| Neue DOL-Sektion anhängen | **nicht** in `ppc_asm`. `offset_for_address` wirft bei unbekannter Adresse | `ppc_asm/dol_file.py:91-95` |
| Platz für Code | **vorhanden, ohne neue Sektion.** PAL-DOL, Sektion 0 (Text, `0x80004000`–`0x800066C0`) hat zwei Null-Lücken: **1228 B bei `0x80005868`** und **716 B bei `0x80004A68`**. Dazu sind 8 Sektionsplätze im DOL-Header unbenutzt (5 Text, 3 Daten), falls man doch eine Sektion anhängen will | eigene Messung, Abschnitt 8 |
| Platz für Daten (Ringpuffer) | Null-Lücken in den Datensektionen, z. B. **490 B bei `0x805B58D4`** (Sektion 12). Ob die beschreibbar und vom Spiel ungenutzt sind, ist ungeprüft | eigene Messung |
| Fertiger MP3-Hook | **fehlt.** `remote_execution_patch_start` und `_load_player_state` werfen `ValueError` für Corruption | `OPR/all_prime_dol_patches.py:82,177` |
| Einstiegspunkt „jeder Frame“ | **unbekannt.** `string_display = None` für alle drei Regionen | `OPR/corruption/dol_versions.py:17,41,58` (`AP_MEMORY_MAP.md:41`) |
| Einstiegspunkt „Item erhalten“ | **bekannt**: `add_power_up`, `incr_pickup`, `decr_pickup` | PAL `0x80191E2C`, `0x801920B0`, `0x8019222C`. Die Prologe sind bestätigt. Die erste Anweisung `stwu r1,-0x20(r1)` ist lageunabhängig und lässt sich in die Lücke kopieren |
| Andere Regionen | **fehlen:** Jede Region hat eigene Adressen (`OPR/corruption/dol_versions.py`), ein NTSC-U-Dump liegt nicht vor | `AP_DEV_SETUP.md`, Abschnitt 7 |

Vorschlag für die kleinste sinnvolle Variante (**ungeprüft**): `add_power_up` per Trampolin umleiten. In `.init` liegen ein
paar Dutzend Anweisungen, die `(Slot, Delta)` in einen Ringpuffer im Datenbereich schreiben und danach in die ursprüngliche
Funktion springen. Das Item-Ereignis ist dann für jeden Pickup sicher, auch ohne Marker-Bitmaske. Eine
Item-Warteschlange „von außen nach innen“ braucht dagegen den fehlenden Frame-Einstieg. **Nicht nötig für den MVP**: Items
geben geht ohne Hook per direktem Schreiben ins Inventar (`AP_MEMORY_MAP.md:158-160`, in T07 live zu testen).

Eine **Alternative ohne ISO-Änderung** passt zu E2 (nur Dolphin): Der Client schreibt den Hook-Code zur Laufzeit per
`dolphin-memory-engine` in den Speicher. Ob Dolphin den JIT-Cache nach so einem Schreibzugriff leert, ist ungeprüft.

---

## 5. Optionaler Live-Test

**Nicht getestet.** Gründe: Der Test braucht (a) einen out-of-repo-Build des Patchers mit einem geänderten `Item.cs`,
(b) einen neuen Export (rund 1 Minute, 15 GB Platz) und (c) dass jemand den Pickup im Spiel einsammelt. Das passt nicht
sicher in 30 Minuten. Stattdessen wurde die PAL-DOL statisch ausgewertet (Abschnitt 2.2 und 8).

Vorschlag für den Test, der die größte offene Frage klärt (Klemmung und Persistenz von Slot 47):
1. Kopie von `PATCHER/` außerhalb des Repos. `ItemName.DarkBeam` (`ItemName.cs:47`, unbenutzt) bekommt einen `case` in
   `Item.cs` mit `item_type = 51 E1 A9 FB`, `capacity = 00 00 00 05`, `amount = 00 00 00 05` und den Visuals von `EnergyTank`
   (`Item.cs:496-515`). Im Decoder `MP3Permalink.cs:130` das Zeichen `B` (HyperMissile) testweise darauf umbiegen.
2. Seed `IVG2J7OR` (`build/seed/t01.patcher.json`): das Zeichen eines Orts nahe am Start austauschen (Startwelt Valhalla,
   `AP_MEMORY_MAP.md:249`), neue SHA-256-Prüfsumme berechnen (`GOLLOP:194-195`), exportieren. Die Missile Expansion in Docking
   Bay 5 ist der erste Pickup (`AP_MEMORY_MAP.md:271`, dort „vermutlich“).
3. In Dolphin einsammeln und Slot 47 lesen: `PS + 0x54 + 47 * 0xC` = **`PS + 0x288`** (Kette `AP_MEMORY_MAP.md:60-61`).
   Vorher/nachher protokollieren, danach speichern, neu laden und noch einmal lesen.
4. Zusätzlich Slots 43 (`PS + 0x258`) und 53–61 (`PS + 0x2D0` … `PS + 0x330`) von Hand beschreiben (Dolphin-Memory-Engine)
   und prüfen, ob das Spiel sie beim Raumwechsel, Speichern oder Laden zurücksetzt.

---

## 6. Einschätzung

| Frage | Urteil | Begründung und Aufwand |
|---|---|---|
| **Neutrales „AP-Item“ mit eigenem Modell und Text** | **machbar mit Aufwand** | Neues `ItemName` + `case` in `Item.cs` + ein Zeichen im Decoder. Modell aus vorhandenen Assets, Text über eine neue STRG-ID. Aufwand: etwa 4 Patcher-Dateien, 2 Python-Dateien, ein neuer win-x86-Build. Individuelle Texte je Ort ungeprüft |
| **Marker-Item pro Location (eindeutig)** | **machbar mit Aufwand, bedingt** | **Ein eigener Slot pro Ort ist nicht machbar** (frei und adressierbar ist nur Slot 47). Zwei Wege bleiben: (A) Bitmaske über wenige Slots. Das trägt nur, wenn die Slots Werte bis 2^16 oder mehr halten, und selbst dann knapp (96 Bit für 99 Orte). Das ist ungeprüft. (D) Ein eindeutiges Delta je Ort (`amount = Ort-ID + 1` im Slot 47), gelesen von einem DOL-Hook. D ist unabhängig von der Klemmung, braucht aber den Hook. Aufwand für beide: ein zusätzlicher Patcher-Parameter (je Ort eine Marker-Zahl, Abschnitt 3.2), ein Live-Test (Abschnitt 5). Ort 0 bleibt ausgeschlossen. **Entscheidend ist der Live-Test der Klemmung** |
| **Hook in `main.dol`** | **machbar mit Aufwand** (nur Item-Ereignis, Region PAL) / **hoher Aufwand** (Frame-Hook, weitere Regionen) | Infrastruktur steht (Export-Stelle, `ppc_asm`, Code-Lücken, bestätigte `add_power_up`-Adresse). Fehlend: Frame-Einstieg, NTSC-U/J-Adressen, Prüfung der Daten-Lücke für den Ringpuffer. Für den MVP nicht nötig, wenn Variante A trägt |
| **Direktes Item-Schreiben (c)** | **nicht untersucht (T07)** | Slot-Array ist bis 69 gültig (`cmplwi r4,0x45`). Nebenwirkungen offen (`AP_MEMORY_MAP.md:158-160`) |

**Empfehlung für F-01:** Ansatz (a) ist grundsätzlich machbar, aber nicht als „ein Slot pro Pickup“. Realistisch ist ein
Marker aus wenigen Slots, dessen Menge den Ort kodiert. Vor der Entscheidung ist der Live-Test aus Abschnitt 5 nötig. Ansatz (b)
ist nur als Ereignis-Hook auf `add_power_up` realistisch. Ansatz (c) (Items per Schreiben geben) bleibt für den MVP plausibel.

---

## 7. Offene Punkte

1. Live-Test der Slot-Klemmung und Persistenz (Abschnitt 5). Das ist der einzige Punkt, der die Marker-Entscheidung kippen kann.
2. Hat Slot 47 in MP3 eine Funktion („PhazonBall“ ist nur ein Kommentar in `GOLLOP:94`)? Hat Slot 43 das Feld `HyperModeCharge`?
3. Ist `TemporaryMissile` wirklich Slot 68? Live prüfen: „Locked Missile Expansion“ einsammeln und Slot 68 lesen.
4. Lookup-Funktion an `0x802DA564` disassemblieren, um den Schluss „Binärsuche Hash→Slot“ und das Verhalten bei unbekanntem Hash
   (Absturz oder wirkungslos) zu belegen.
5. NTSC-U-DOL auswerten, sobald ein Dump vorliegt (E7). Tabelle und Funktionsadressen weichen je Region ab.
6. 99 individuelle STRG-Texte: Skalierung des Patchers (Größe der Paks, Abhängigkeiten) ungeprüft.

---

## 8. Reproduktion der DOL-Messung

Die PAL-`main.dol` wurde nur lesend aus dem eigenen ISO geholt (`DolphinTool extract`) und liegt nicht im Repo. Prüfskript
(Python 3.12, `py -I`), Argument = Pfad zur `main.dol`:

```python
import struct, sys
d = open(sys.argv[1], "rb").read()
offs  = struct.unpack(">18I", d[0x00:0x48])   # Dateioffsets der 18 Sektionen
addrs = struct.unpack(">18I", d[0x48:0x90])   # virtuelle Adressen
sizes = struct.unpack(">18I", d[0x90:0xD8])
def v2f(v):
    for o, a, s in zip(offs, addrs, sizes):
        if s and a <= v < a + s:
            return o + v - a
p, table = v2f(0x80584AB8), {}                # PAL: Anfang der Hash->Slot-Tabelle
while True:
    h, slot = struct.unpack(">II", d[p:p + 8]); table[slot] = h; p += 8
    if h == 0xFB73F2B8: break                 # größter Hash = letzter Eintrag
print(len(table), "Einträge; fehlende Slots 0-69:", [i for i in range(70) if i not in table])
# erwartet: 59 Einträge; fehlend [43, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61]
for name, addr in [("add_power_up", 0x80191E2C), ("incr_pickup", 0x801920B0), ("decr_pickup", 0x8019222C)]:
    o = v2f(addr); print(name, [hex(w) for w in struct.unpack(">3I", d[o:o + 12])])
# erwartet je: ['0x9421ffe0', '0x7c0802a6', '0x28040045']  (stwu, mflr, cmplwi r4,0x45)
```

Kopf der PAL-`main.dol`: 10 benutzte Sektionen (2 Text, 8 Daten), 8 freie Plätze (5 Text, 3 Daten), BSS `0x805C2E00`–`0x80686A04`, Einstieg
`0x80006320`, keine Daten hinter der letzten Sektion (Dateigröße = Sektionsende `0x5C6760`).
