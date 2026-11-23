# AP-Speicher-Mapping: Metroid Prime 3 in Dolphin (T02)

Stand: 2026-11-23. Grundlage: `randovania/game_connection/connector/corruption_remote_connector.py`,
`prime_remote_connector.py`, `executor/dolphin_executor.py` und die Versionstabellen aus
**open-prime-rando 0.15.1** (`venv/Lib/site-packages/open_prime_rando/dol_patching/…`, im Folgenden `OPR/…`).
Live geprüft mit **PAL `RM3P01`** (Rev 0), Seed `IVG2J7OR` aus T01, Dolphin 2609b, dolphin-memory-engine 1.3.0.

> **Kurzfassung**
> - Für PAL sind Build-String, aktuelle Welt, die Erkennung „ingame/Menü/Laden“ und das Inventar **live bestätigt**.
>   Beim Einsammeln ändern sich `ScrewAttack` von 0/0 auf 1/1 und `ItemPercentage` von 1/101 auf 2/102.
> - **Randovania kann für MP3 heute weder Items ins Spiel geben noch Location-Checks erkennen.**
>   Beides ist im Connector nicht implementiert (Abschnitte 4 und 5). Für den AP-Client (T06/T07) sind das die
>   zwei Lücken, die neu gebaut werden müssen.
> - NTSC-U (`RM3E01`) und NTSC-J (`RM3J01`) sind **nur aus Code** belegt und nicht live geprüft.

Konventionen:
- Alle Adressen sind virtuelle Wii-Adressen (MEM1 `0x80000000–0x81800000`, `dolphin_executor.py:15-16`). Alle Werte
  sind **Big Endian**.
- `[X]` heißt: 4-Byte-Zeiger an Adresse X lesen. `[X]+off` heißt: Zeiger lesen, dann den Offset addieren.
  So arbeitet auch der Executor: Eine `MemoryOperation` mit `offset` liest erst den Zeiger an `address` und addiert dann
  den Offset (`dolphin_executor.py:84-92, 113-132`).
- Quelle `OPR/corruption/dol_versions.py` = `open_prime_rando/dol_patching/corruption/dol_versions.py`.

---

## 1. Versionstabelle (globale Adressen je Region)

Quelle: `OPR/corruption/dol_versions.py:6-65`. Der Connector wählt die Version anhand des Build-Strings
(`randovania/game_connection/builder/prime_connector_builder.py:40,64-100`).

| Feld | NTSC-U „Wii NTSC“ (RM3E01) | PAL „Wii PAL“ (RM3P01) | NTSC-J „Wii NTSC-J“ (RM3J01) | Quelle |
|---|---|---|---|---|
| `build_string_address` | `0x805822B0` | `0x805843A8` | `0x80587C2C` | `dol_versions.py:10,34,51` |
| `build_string` | `…2007/07/27 13:13 Build v3.436 (MP3)` | `…2007/08/24 16:52 Build v3.453 (mp3)` | `…2007/11/12 14:15 Build v3.495 (jpn)` | `dol_versions.py:11,35,52` |
| `game_state_pointer` | `0x8067DC0C` | `0x80680234` | `0x80683A7C` | `dol_versions.py:14,38,55` |
| `cplayer_vtable` | `0x80592C78` | `0x80595238` | `0x80598650` | `dol_versions.py:15,39,56` |
| `cstate_manager_global` | `0x805C4F70` | `0x805C7570` | `0x805CAA30` | `dol_versions.py:16,40,57` |
| `powerup_functions.add_power_up` | `0x8019111C` | `0x80191E2C` | `0x801932D0` | `dol_versions.py:26,43,60` |
| `powerup_functions.incr_pickup` | `0x801913A0` | `0x801920B0` | `0x80193554` | `dol_versions.py:27,44,61` |
| `powerup_functions.decr_pickup` | `0x8019151C` | `0x8019222C` | `0x801936D0` | `dol_versions.py:28,45,62` |
| `string_display` | `None` | `None` | `None` | `dol_versions.py:17,41,58` |
| `sda2_base` / `sda13_base` | `0x806869C0` / `0x806801C0` | `0x80688FE0` / `0x806827C0` | `0x8068C840` / `0x80686000` | `dol_versions.py:12-13,36-37,53-54` (vom Connector nicht benutzt) |
| **Status** | **nur aus Code** | **live bestätigt** (bis auf `powerup_functions`, `sda*`) | **nur aus Code** | |

---

## 2. Feld-Tabelle (Pointer-Ketten)

PAL-Beispieladressen stammen aus dem Live-Lauf. Die dynamischen Adressen (Heap) ändern sich je nach Sitzung.

| Feld | Adresse / Pointer-Kette | Typ | Region | Status | Quelle (Datei:Zeile) |
|---|---|---|---|---|---|
| Game-ID | `0x80000000`, 6 Byte | ASCII | alle | PAL live: `RM3P01` | Dolphin-Standard (nicht vom Connector gelesen) |
| Build-String (Versionserkennung) | `build_string_address`, `len(build_string)` Byte | ASCII | s. Tab. 1 | PAL live: passt | `prime_remote_connector.py:86-104`, `prime_connector_builder.py:67-100` |
| Layout-UUID | Bytes `[6:22]` des Build-Strings | 16 Byte UUID | alle | PAL live: **nicht gesetzt** (Original-Text `roidBuildInfo!#$`) → `INVALID_UUID` | `prime_remote_connector.py:92-101` |
| Aktuelle Welt (MLVL-Asset-ID) | `[game_state_pointer] + 0x8`, 8 Byte | `u64` (`>Q`) | s. Tab. 1 | PAL live: Valhalla, Norion, FrontEnd | `corruption_remote_connector.py:48-49,64-65,72`; Abgleich `prime_remote_connector.py:110-136` |
| „Pending-Op“-Byte | `cstate_manager_global + 0x2`, 1 Byte | `u8` | s. Tab. 1 | PAL live: **immer `0xFF`** (Menü, Laden, ingame) | `corruption_remote_connector.py:73,87-88`, `prime_remote_connector.py:254` |
| CPlayer-Zeiger | `[cstate_manager_global + 0x28] + 0x2184`, 4 Byte | Zeiger | s. Tab. 1 | PAL live: Menü/Laden = `0`, ingame z. B. `0x80B81AE0` | `corruption_remote_connector.py:67-74,77` |
| CPlayer-vtable (Ingame-Prüfung) | `[[cstate_manager_global + 0x28] + 0x2184]`, 4 Byte | Zeiger | s. Tab. 1 | PAL live: `0x80595238` = erwartet | `corruption_remote_connector.py:79-85`, `prime_remote_connector.py:127-133` |
| CPlayerState-Basis | `[game_state_pointer] + 0x24` = Zeiger-Slot; `PS = [[game_state_pointer] + 0x24]` | Zeiger | s. Tab. 1 | PAL live: `PS = 0x80995B20` (in allen Lesungen gleich) | `corruption_remote_connector.py:95-102` |
| Inventar-Slot `item_id` | `PS + 0x54 + item_id * 0xC`, 8 Byte | `u32 amount`, `u32 capacity` (`>II`) | alle | PAL live, s. Abschnitt 3 | `corruption_remote_connector.py:37-41,104-111`, `prime_remote_connector.py:151-166` |
| Item geben (Kapazität) | Funktionsaufruf `add_power_up(PlayerState, item_id, delta)` | PPC-Funktion | s. Tab. 1 | nur aus Code, **in MP3 nicht nutzbar** (Abschnitt 4) | `OPR/all_prime_dol_patches.py:202-213`; `corruption_remote_connector.py:117-125` |
| Item geben (Menge) | `incr_pickup` / `decr_pickup(PlayerState, item_id, n)` | PPC-Funktion | s. Tab. 1 | nur aus Code, **in MP3 nicht nutzbar** | `OPR/all_prime_dol_patches.py:216-227` |

Herleitung des Inventar-Offsets (`corruption_remote_connector.py:37-41`):
`0x50` (Powerup-Vektor in CPlayerState) + `0x4` (Datenzeiger/Größe des Vektors) + `item_id * 0xC` (Größe eines
Eintrags). Gelesen werden nur die ersten 8 Byte eines Eintrags (`amount`, `capacity`). Was in den restlichen 4 Byte
steht, ist nicht dokumentiert.

---

## 3. Inventar: Item-ID → Offset

Item-IDs aus `randovania/games/prime3/logic_database/header.json` (`resource_database.items[*].extra.item_id`).
Offset relativ zu `PS`. PAL-Absolutadressen gelten für `PS = 0x80995B20` aus dem Live-Lauf. Nur IDs `< 1000` liegen im
Speicher (`prime_remote_connector.py:155`). IDs ab 1000 sind reine Logik-Ressourcen.

| item_id | Name (`header.json`) | Offset von `PS` | PAL-Adresse (live) | max. Kapazität |
|---|---|---|---|---|
| 0 | PowerBeam | `+0x054` | `0x80995B74` | 1 |
| 1 | PlasmaBeam | `+0x060` | `0x80995B80` | 1 |
| 2 | NovaBeam | `+0x06C` | `0x80995B8C` | 1 |
| 3 | ChargeUpgrade (Charge Beam) | `+0x078` | `0x80995B98` | 1 |
| 4 | Missile | `+0x084` | `0x80995BA4` | 255 |
| 5 | IceMissile | `+0x090` | `0x80995BB0` | 1 |
| 6 | Seekers | `+0x09C` | `0x80995BBC` | 1 |
| 7 | GrappleBeamPull (Lasso) | `+0x0A8` | `0x80995BC8` | 1 |
| 8 | GrappleBeamSwing | `+0x0B4` | `0x80995BD4` | 1 |
| 9 | GrappleBeamVoltage | `+0x0C0` | `0x80995BE0` | 1 |
| 10 | Bomb | `+0x0CC` | `0x80995BEC` | 1 |
| 11 | CombatVisor | `+0x0D8` | `0x80995BF8` | 1 |
| 12 | ScanVisor | `+0x0E4` | `0x80995C04` | 1 |
| 13 | CommandVisor | `+0x0F0` | `0x80995C10` | 1 |
| 14 | XRayVisor | `+0x0FC` | `0x80995C1C` | 1 |
| 15 | DoubleJump (Space Jump Boots) | `+0x108` | `0x80995C28` | 1 |
| 16 | ScrewAttack | `+0x114` | `0x80995C34` | 1 |
| 17 | SuitType | `+0x120` | `0x80995C40` | 6 (Connector: ≥5 = „hat Item“, `corruption_remote_connector.py:142-152`) |
| 18 | Energy | `+0x12C` | `0x80995C4C` | 1499 (live 0/0, obwohl das HUD 99 zeigt: **nicht** die Lebensenergie) |
| 19 | HypermodeEnergy | `+0x138` | `0x80995C58` | 0 |
| 20 | EnergyTank | `+0x144` | `0x80995C64` | 14 |
| 21 | ItemPercentage | `+0x150` | `0x80995C70` | 255 |
| 22 | Fuses (Energy Cells Total) | `+0x15C` | `0x80995C7C` | 9 |
| 23–31 | Fuse1 … Fuse9 (Energy Cell 1–9) | `+0x168` … `+0x1C8` (Schritt `0xC`) | `0x80995C88` … `0x80995CE8` | 1 |
| 32 | MorphBall | `+0x1D4` | `0x80995CF4` | 1 |
| 33 | BoostBall | `+0x1E0` | `0x80995D00` | 1 |
| 34 | SpiderBall | `+0x1EC` | `0x80995D0C` | 1 |
| 35–42 | HyperModeTank, HyperModeBeam, HyperModeMissile, HyperModeBall, HyperModeGrapple, HyperModePermanent, HyperModePhaaze, HyperModeOriginal | `+0x1F8` … `+0x24C` | `0x80995D18` … `0x80995D6C` | 1 |
| 44 | ShipGrapple | `+0x264` | `0x80995D84` | 1 |
| 45 | ShipMissile | `+0x270` | `0x80995D90` | 11 |
| 46 | FaceCorruptionLevel | `+0x27C` | `0x80995D9C` | 4 |
| 48 | CannonBall | `+0x294` | `0x80995DB4` | 1 |
| 49 | ActivateMorphballBoost | `+0x2A0` | `0x80995DC0` | 1 |
| 50 | HyperShot | `+0x2AC` | `0x80995DCC` | 2 |
| 51 | CommandVisorJammed | `+0x2B8` | `0x80995DD8` | 1 |
| 52 | EnergyCellsUsed | `+0x2C4` | `0x80995DE4` | 9 |
| 62–69 | Stat_EnemiesKilled, Stat_ShotsFired, Stat_DamageReceived, Stat_DataSaves, Stat_HypermodeUses, Stat_CommandoKills, Stat_TinCanHighScore, Stat_TinCanCurrentScore | `+0x33C` … `+0x390` | `0x80995E5C` … `0x80995EB0` | 99999 |
| 1000–1003 | MissileLauncher, ShipMissileLauncher, TemporaryMissile, TemporaryShipMissile | – (nicht im Speicher) | – | – |

Die IDs 43, 47 und 53–61 fehlen in `header.json`. Die Slots existieren im Array, weil es bis mindestens ID 69 reicht. Ihr Inhalt
wurde nicht geprüft.

Hinweis zu `get_inventory` (`prime_remote_connector.py:154-160`): Die Memory-Ops werden nur für IDs `< 1000` erzeugt,
anschließend aber mit **allen** Items gezippt. Das klappt nur, weil die IDs ab 1000 in `header.json` am Ende stehen.

---

## 4. Items ins Spiel geben (Mechanismus von Randovania)

**Für MP3 nicht implementiert.** Der allgemeine Prime-Mechanismus (MP1/MP2) ist eine *Remote Code Execution*:

1. Der Connector baut PPC-Instruktionen, die `add_power_up` und `incr_pickup` mit `item_id` und Delta aufrufen
   (`OPR/all_prime_dol_patches.py:180-227`, aufgerufen in `corruption_remote_connector.py:113-126`).
2. `create_remote_execution_body` assembliert diese Instruktionen an die Adresse
   `string_display.update_hint_state + Prolog` (`OPR/all_prime_dol_patches.py:242-265`).
3. Er schreibt den Code dorthin und setzt `cstate_manager_global + 0x2 = 0x01` (`prime_remote_connector.py:246-258`).
4. Ein vom Patcher in die DOL eingebauter Hook (`apply_remote_execution_patch`, `OPR/all_prime_dol_patches.py:238-239`)
   prüft dieses Byte in jedem Frame, führt den Code aus und setzt das Byte auf `0` zurück
   (`OPR/all_prime_dol_patches.py:66-128`).
5. Gezählt wird über ein „Magic Item“: Seine `capacity` ist die Zahl der bereits gegebenen Remote-Items
   (`prime_remote_connector.py:201-233`).

Warum das in MP3 nicht geht:
- `string_display = None` für alle drei MP3-Versionen (`dol_versions.py:17,41,58`). Es gibt also weder eine Zieladresse
  noch einen HUD-Text.
- `remote_execution_patch_start` und `_load_player_state` werfen für `Game.CORRUPTION` einen `ValueError`
  (`OPR/all_prime_dol_patches.py:82,177`).
- `CorruptionRemoteConnector.execute_remote_patches` wirft einen `RuntimeError` (`corruption_remote_connector.py:139-140`),
  `receive_remote_pickups` gibt fest `False` zurück (`:131-137`), `_dol_patch_for_hud_message` wirft (`:128-129`),
  `multiworld_magic_item` wirft `NotImplementedError` (`:51-54`).
- Der MP3-Patcher (`MP3Randomizer`) baut keinen Hook ein. Live ist das Byte `cstate_manager_global + 0x2` auf PAL
  dauerhaft `0xFF`, also kein Flag, das ein Hook zurücksetzt. Deshalb hielte `current_game_status` **immer**
  `has_pending_op = True` (`corruption_remote_connector.py:87-88`), und `update()` würde den Multiworld-Teil nie
  erreichen (`prime_remote_connector.py:336-340`).
- Die Layout-UUID wird nicht in den Build-String geschrieben (live: Originaltext). Der Connector setzt deshalb
  `INVALID_UUID` (`prime_remote_connector.py:97-99`).

**Folge für T07 (Lücke):** Der AP-Client braucht einen eigenen Weg, Items zu geben. Möglichkeiten:
- (a) **Direkt schreiben:** `amount`/`capacity` im Slot `PS + 0x54 + id*0xC` setzen. Das ist einfach, aber Nebenwirkungen
  sind ungeprüft, etwa bei HUD, Waffen-Freischaltung, Energy Tanks (Energie auffüllen?), `ItemPercentage` und Speichern.
  Das muss in T07 live getestet werden.
- (b) **Remote-Execution-Hook für MP3 nachbauen:** Patcher-Erweiterung plus MP3-Adressen für `update_hint_state` bzw. einen
  anderen Per-Frame-Hook und für CStateManager→PlayerState. Ein sauberer, aber deutlich größerer Aufwand.

---

## 5. Location-Check-Erkennung

### Wie Randovania es heute macht

**Gar nicht, für MP3 gibt es keinen Weg.** Der generische Ablauf in `PrimeRemoteConnector.known_collected_locations`
(`prime_remote_connector.py:168-199`) liest das Magic Item. Dessen `amount - 1` ist der `PickupIndex` des zuletzt
eingesammelten Fremd-Pickups. Danach setzt er es per Remote-Patch auf 0 zurück und meldet `PickupIndexCollected`
(`:360-366`). Für MP3:
- `multiworld_magic_item` wirft `NotImplementedError` (`corruption_remote_connector.py:51-54`).
- Der Patcher legt keine Magic-Item-Pickups an, und Remote-Patches gehen nicht (Abschnitt 4).
- Der Connector meldet nur **Region** (`PlayerLocationChanged`) und **Inventar** (`InventoryUpdated`)
  (`prime_remote_connector.py:328-335, 354-358`). Selbst dafür müsste `update()` funktionieren. Weil
  `multiworld_magic_item` geworfen wird und `has_pending_op` (siehe oben) immer wahr ist, landet man nie bei
  `_multiworld_interaction`.

**Benannte Lücke:** Es gibt keine Adresse und kein Flag, das einen einzelnen Pickup-Ort identifiziert. Der Raum (Area)
wird vom Connector nicht gelesen, nur die Welt.

### Was live messbar ist (PAL)

Jeder eingesammelte Pickup erhöht `ItemPercentage` (ID 21) um 1, bei `amount` **und** `capacity`
(0/100 → 1/101 → 2/102). Das passt dazu, dass in `pickup-database.json` jeder Pickup `"ItemPercentage": 1` mitgibt
(z. B. Zeile 137). Dieser Zähler ist der einzige Wert, der sich bei **jedem** Pickup ändert. Auch eine
„Locked Missile Expansion“ (ohne Missile Launcher) ändert nur ihn und `Missile` bleibt 0/0, weil die Ladung in die reine
Logik-Ressource `TemporaryMissile` (ID 1002, nicht im Speicher) wandert (`pickup-database.json:737-754`).

### Vorschlag für den AP-Client (T05/T06)

1. **Kurzfristig (Heuristik, ohne Patcher-Änderung):** Alle 0,5 s pollen. Ändert sich `ItemPercentage.amount`, wird das
   Inventar vorher/nachher verglichen und mit der aktuellen Welt plus der Platzierung aus dem Seed die passende Location
   gesucht. Das ist mehrdeutig, wenn in einer Welt mehrere Orte dasselbe Item tragen (z. B. Missile Expansions, AP-Fremd-Items)
   oder ein Pickup nur `ItemPercentage` ändert. Für das MVP reicht es nicht, als Plausibilitätsprüfung ist es aber brauchbar.
2. **Empfohlen:** Jeder Pickup gibt zusätzlich ein **eindeutiges Zähler-Item**, zum Beispiel einen ungenutzten Slot
   (43, 47, 53–61) mit `amount = Location-Index + 1` wie beim MP1/MP2-Magic-Item. Alternativ ein eigenes Item je Location-Gruppe.
   Der Client liest den Slot, meldet den Check und setzt ihn per direktem Schreiben auf 0 zurück. Das braucht eine
   Patcher-Erweiterung in T05 und einen Live-Test, ob ungenutzte Slots stabil bleiben und mitgespeichert werden.
3. **Nicht untersucht:** Layer- oder Memory-Relay-Zustände je Raum (CWorldLayerState), über die das Spiel sich merkt, welche
   Pickups weg sind. Das wäre die patcherfreie Lösung, Adressen dafür gibt es in Randovania aber keine.

---

## 6. Ingame vs. Menü / Ladebildschirm

Verfahren des Connectors (`corruption_remote_connector.py:56-89`, `prime_remote_connector.py:116-136`):
**ingame** ⇔ der CPlayer-Zeiger ist gültig **und** seine vtable ist `cplayer_vtable` **und** die MLVL-ID gehört zu einer
Region in der Datenbank. Sonst wird `None` gemeldet, also nicht ingame.

PAL-Messungen (Watcher-Log, 0,5-s-Polling):

| Zustand | MLVL `[gsp]+8` | CPlayer-Zeiger | vtable ok | Inventar |
|---|---|---|---|---|
| Titel / Game Select / Menü | `0xF4A9F72C65FBAE26` (FrontEnd, keine Region) | `0x0` | nein | alle 0/0 |
| Intro-Text „Life-Support Status“ / Landeanflug | `0xC133F919C108BDF9` (Valhalla) | gültig, vtable ok | ja | **noch 0/0** |
| ingame Valhalla (Start, ~19 s nach Weltwechsel) | `0xC133F919C108BDF9` | `0x80B81960` | ja | Startitems 1/1 |
| Flug Valhalla → Norion (Ladephase) | wechselt auf `0x6FB8EF2A9523C343` | **kurz `0x0`** (2 s) | nein | bleibt |
| ingame Norion | `0x6FB8EF2A9523C343` | `0x80F5AA60` | ja | bleibt |

Folgerungen:
- Die Prüfung „CPlayer + vtable“ trennt Menü und Laden zuverlässig vom Spiel.
- In Intro und Cutscenes gilt man laut Connector schon als „ingame“, obwohl das Inventar noch nicht befüllt ist. Ein
  AP-Client sollte erst schreiben, wenn auch `PowerBeam.capacity > 0` ist, oder auf eine andere Plausibilitätsprüfung warten.
  Für Cutscenes gibt es in MP3 keinen Check: Der MP1/MP2-Kameracheck in `OPR/all_prime_dol_patches.py:70-82` fehlt für Corruption.
- Das Byte `cstate_manager_global + 0x2` taugt in MP3 **nicht** als Zustandsflag (immer `0xFF`).

---

## 7. Aktuelle Welt / Raum

- **Welt:** `[game_state_pointer] + 0x8` als `u64`. Abgleich gegen `region.extra["asset_id"]` aus
  `logic_database/<Region>.json:4` (`prime_remote_connector.py:110-114`). Die Zuordnung Name → ID steht auch in
  `randovania/games/prime3/assets/migration_data.json:2-18`.
- **Raum (Area):** wird vom Connector **nicht** gelesen (`PlayerLocationEvent(region, None)`,
  `prime_remote_connector.py:331`). Adresse unbekannt. Die Area-Asset-IDs stehen in der Datenbank
  (`migration_data.json` → `area_name_to_id`, `<Region>.json` → `extra.asset_id`).

| Region | MLVL-Asset-ID (hex) | Status PAL |
|---|---|---|
| G.F.S. Valhalla | `0xC133F919C108BDF9` | live bestätigt (Startwelt Seed IVG2J7OR) |
| Norion | `0x6FB8EF2A9523C343` | live bestätigt |
| FrontEnd (Menü) | `0xF4A9F72C65FBAE26` | live gesehen, keine Region in der DB |
| G.F.S. Olympus | `0x37A9E86F0A0CAF6F` | nur aus DB |
| übrige 12 Regionen | s. `migration_data.json:2-18` | nur aus DB |

Hinweis zu T01: Der Starter-Preset-Seed `IVG2J7OR` startet laut `t01.rdvgame` auf **Valhalla, Docking Bay 5**, nicht auf
Olympus. Die Speicherwerte bestätigen das. Die T01-Beobachtung „bootet bis Olympus“ sollte man prüfen, wahrscheinlich
war es Valhalla.

---

## 8. Live-Prüfung PAL: Protokoll

Werkzeug: Wegwerf-Skripte außerhalb des Repos (Scratchpad), `mp3mem.py` (Einzel-Lesung) und `mp3watch.py` (0,5-s-Polling,
protokolliert nur Änderungen). Sie bilden die Pointer-Ketten aus Abschnitt 2 nach. Das Einsammeln hat der Nutzer
gespielt, die Werte hat das Skript gelesen.

Bestätigte Werte (PAL `RM3P01`):

| # | Feld | Erwartet (Code) | Gelesen | Ergebnis |
|---|---|---|---|---|
| 1 | Game-ID `0x80000000` | `RM3P01` | `RM3P01` | ✔ |
| 2 | Build-String @ `0x805843A8` | `…2007/08/24 16:52 Build v3.453 (mp3)` | identisch | ✔ |
| 3 | CPlayer-vtable | `0x80595238` | `0x80595238` | ✔ |
| 4 | Welt `[0x80680234]+8` | Valhalla `0xC133F919C108BDF9`, nach Flug Norion `0x6FB8EF2A9523C343` | identisch | ✔ |
| 5 | Inventar Startitems | Seed: Charge, Power, Combat, Scan, Space Jump, Morph Ball, Bombs | genau diese 7 auf 1/1, Rest 0 | ✔ |
| 6 | **ScrewAttack** (ID 16) @ `0x80995C34` | – | **vorher 0/0 → nachher 1/1** (19:25:43, Norion, Docking Hub Alpha, Ort „Pickup (Grapple Lasso)“, laut Seed Screw Attack) | ✔ |
| 7 | **ItemPercentage** (ID 21) @ `0x80995C70` | +1 je Pickup | 0/100 → **1/101** (19:22:41, Valhalla; vermutlich die Missile Expansion in Docking Bay 5, `Missile` blieb 0/0) → **2/102** (Screw Attack) | ✔ |
| 8 | Stat_DamageReceived (ID 64) | – | 0/0 → 2/2, als das HUD von 99 auf 97 fiel | ✔ |
| 9 | Stat_ShotsFired (ID 63) | – | zählt jeden Schuss hoch (0 → 12) | ✔ |

Nicht live geprüft: `powerup_functions` (Item geben), Schreibzugriffe aller Art, NTSC-U und NTSC-J.

---

## 9. Offene Punkte für T05–T07

1. Item-Vergabe (T07): direktes Schreiben in den Inventar-Slot live testen, inklusive Speichern, Laden, Energy Tank und Beam-Wechsel.
2. Location-Checks (T05/T06): Zähler-Item im Patcher oder Layer-State-Adressen finden (Abschnitt 5).
3. Raum-Adresse (Area) für Tracker oder DeathLink, optional.
4. NTSC-U-Adressen (`RM3E01`) live prüfen, sobald ein ISO da ist (E7).
5. Layout-UUID: Der MP3-Patcher schreibt sie nicht. Für die Zuordnung Client ↔ Seed braucht es einen eigenen Marker
   (z. B. Seed-Hash im Build-String, wie bei `apply_build_info_patch`, `OPR/all_prime_dol_patches.py:316`).
