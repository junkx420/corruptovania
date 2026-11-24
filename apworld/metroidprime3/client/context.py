"""Metroid Prime 3 Client (T06): CommonClient + Dolphin, Location-Checks und Lernmodus.

Start und Bedienung: docs/AP_CLIENT.md. Item-Vergabe kommt in T07 (``MP3Context.give_items``).
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import traceback
from typing import Any

import Utils
from CommonClient import ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled, logger, server_loop

from ..items import BASE_ID, GAME_NAME
from .checks import CheckDetector, LocationTable
from .flag_block import FlagBlockFinder
from .game import GameState, read_game_state
from .learning import LearningMode
from .memory import ConnectionLost, ConnectStatus, MemoryAccess, MemoryAccessError

DEFAULT_POLL_INTERVAL = 0.5
RECONNECT_DELAY = 5.0
SUPPORTED_SLOT_DATA_VERSION = 1


class MP3CommandProcessor(ClientCommandProcessor):
    ctx: "MP3Context"

    def _cmd_dolphin(self) -> None:
        """Zeigt den Status der Dolphin-Verbindung."""
        self.output(self.ctx.status_text())

    def _cmd_learning(self, value: str = "") -> None:
        """Lernmodus an/aus: /learning on|off (ohne Argument: Status)."""
        learning = self.ctx.learning
        if value.lower() in ("on", "an", "1"):
            learning.enabled = True
        elif value.lower() in ("off", "aus", "0"):
            learning.flush()
            learning.enabled = False
        self.output(f"Lernmodus {'an' if learning.enabled else 'aus'}, Logdatei: {learning.log_path}, "
                    f"{learning.entries_written} Einträge, {learning.warnings} Warnungen")

    def _cmd_blocks(self) -> None:
        """Zeigt die gefundenen Flag-Blöcke je Welt."""
        finder = self.ctx.finder
        if not finder.blocks:
            self.output("Keine Flag-Blöcke bekannt.")
        for world, addresses in sorted(finder.blocks.items()):
            self.output(f"{self.ctx.table.world_name(world)}: " + ", ".join(f"0x{a:08X}" for a in addresses))
        for world, addresses in sorted(finder.rejected.items()):
            self.output(f"verworfen (unplausibel) {self.ctx.table.world_name(world)}: "
                        + ", ".join(f"0x{a:08X}" for a in addresses))
        self.output(f"Suchläufe: {finder.scan_count}, letzter {finder.last_scan_seconds:.2f} s")

    def _cmd_poll(self, seconds: str = "") -> None:
        """Polling-Intervall in Sekunden setzen: /poll 0.5"""
        if seconds:
            try:
                value = float(seconds)
            except ValueError:
                self.output("Zahl erwartet, z. B. /poll 0.5")
                return
            self.ctx.poll_interval = min(max(value, 0.1), 5.0)
        self.output(f"Polling-Intervall: {self.ctx.poll_interval} s")


class MP3Context(CommonContext):
    command_processor = MP3CommandProcessor
    game = GAME_NAME
    items_handling = 0b111  # E10: alle Items kommen vom Server, auch eigene

    def __init__(self, server_address: str | None, password: str | None, memory: MemoryAccess | None = None,
                 poll_interval: float = DEFAULT_POLL_INTERVAL, learning: bool = True,
                 learning_log: str | None = None, confirm_polls: int = 2) -> None:
        super().__init__(server_address, password)
        if memory is None:
            from .memory import DolphinMemory
            memory = DolphinMemory()
        self.memory = memory
        self.poll_interval = poll_interval
        self.table = LocationTable(BASE_ID)
        self.finder = FlagBlockFinder(memory)
        self.detector = CheckDetector(confirm_polls)
        if learning_log is None:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            learning_log = Utils.user_path("logs", f"MP3Client_learning_{stamp}.jsonl")
        self.learning = LearningMode(self.table, learning_log, logger, enabled=learning)
        self.slot_data: dict[str, Any] = {}
        self.dolphin_status = "Dolphin-Verbindung noch nicht gestartet."
        self.game_state: GameState | None = None
        self.current_world: int | None = None
        self.sync_task: asyncio.Task | None = None
        self._was_ingame = False
        self._last_status_message = ""

    # ---- Server ---------------------------------------------------------------------------------------------- #

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict[str, Any]) -> None:
        if cmd == "Connected":
            self.slot_data = args.get("slot_data") or {}
            version = self.slot_data.get("slot_data_version")
            if version != SUPPORTED_SLOT_DATA_VERSION:
                logger.warning(f"slot_data_version {version}, der Client kennt {SUPPORTED_SLOT_DATA_VERSION}.")
            if self.slot_data.get("base_id", BASE_ID) != BASE_ID:
                logger.error("base_id im Seed passt nicht zu diesem Client. Location-IDs wären falsch.")
            # Bereits im Speicher erkannte Orte schickt CommonClient beim Connected selbst (locations_checked).
            self.watcher_event.set()

    def make_gui(self):
        ui = super().make_gui()
        ui.base_title = "Archipelago Metroid Prime 3 Client"
        return ui

    @property
    def server_connected(self) -> bool:
        return (self.slot is not None and self.server is not None and self.server.socket is not None
                and not self.server.socket.closed)

    # ---- Location-Checks ------------------------------------------------------------------------------------- #

    async def report_locations(self, pickup_indices: set[int]) -> set[int]:
        """Meldet neu erkannte Orte. Jeder Ort wird höchstens einmal gesendet (``locations_checked``); vom Server
        schon als erledigt gemeldete Orte werden nicht noch einmal gesendet. Ohne Server-Verbindung werden die Orte
        vorgemerkt; CommonClient schickt ``locations_checked`` beim nächsten ``Connected`` mit."""
        ids = {self.table.location_id(i) for i in pickup_indices}
        new = ids - self.locations_checked
        if not new:
            return set()
        self.locations_checked |= new
        for location_id in sorted(new):
            index = location_id - self.table.base_id
            logger.info(f"Ort {index} eingesammelt: {self.table.names.get(index, location_id)}")
        if not self.server_connected:
            logger.info(f"{len(new)} Ort(e) vorgemerkt, werden nach dem Verbinden mit dem Server gesendet.")
            return set()
        to_send = new - self.checked_locations
        if self.server_locations:
            to_send &= self.server_locations
        if to_send:
            await self.send_msgs([{"cmd": "LocationChecks", "locations": sorted(to_send)}])
        return to_send

    # ---- Item-Vergabe (T07) ---------------------------------------------------------------------------------- #

    async def give_items(self, state: GameState) -> None:
        """SCHNITTSTELLE T07: Item-Vergabe per Soll/Ist-Abgleich (SPEC E9, E11).

        Wird in jeder Abfrage aufgerufen, in der der Spieler ingame ist und der Flag-Block gelesen wurde
        (``state.ingame``). Schreiben erst, wenn ``state.inventory_valid`` (PowerBeam.capacity > 0, E9).
        Empfangene Items: ``self.items_received``, Startitems/Wirkung: ``self.slot_data``, Schreiben:
        ``self.memory.write`` (prüft die Game-ID). In T06 absichtlich leer: es wird nichts geschrieben.
        """
        return None

    # ---- Dolphin-Schleife ------------------------------------------------------------------------------------ #

    def _status(self, message: str, level: int = logging.INFO) -> None:
        self.dolphin_status = message
        if message != self._last_status_message:
            self._last_status_message = message
            logger.log(level, message)

    def status_text(self) -> str:
        lines = [self.dolphin_status]
        state = self.game_state
        if state is not None and self.memory.connected:
            if state.ingame:
                lines.append(f"Ingame, Welt {self.table.world_name(state.world_id)}, "
                             f"ItemPercentage {state.item_percentage}")
            else:
                lines.append(f"Nicht ingame: {state.reason}")
        lines.append(f"Orte erkannt: {len(self.locations_checked)}, Lernmodus {'an' if self.learning.enabled else 'aus'}")
        return "\n".join(lines)

    def _leave_game(self) -> None:
        """Menü, Laden oder Verbindungsabbruch: alles vergessen, was an der Spielsitzung hängt."""
        self.finder.reset()
        self.detector.reset_pending()
        self.learning.reset()
        self.current_world = None
        self._was_ingame = False

    async def poll_once(self) -> float:
        """Eine Abfrage. Liefert die Wartezeit bis zur nächsten."""
        if not self.memory.connected:
            if self._was_ingame or self.dolphin_status.startswith("Mit Dolphin verbunden"):
                self._status("Verbindung zu Dolphin verloren, verbinde neu ...", logging.WARNING)
            self._leave_game()
            self.game_state = None
            result = self.memory.connect()
            if result.status is not ConnectStatus.CONNECTED:
                level = logging.ERROR if result.status is ConnectStatus.WRONG_GAME else logging.INFO
                self._status(result.message + f" Neuer Versuch in {RECONNECT_DELAY:.0f} s.", level)
                return RECONNECT_DELAY
            self._status(result.message)
        try:
            if not self.memory.check_game_id():
                self._leave_game()
                self._status(f"Game-ID hat sich geändert ({self.memory.last_game_id!r}). Getrennt, nichts wird "
                             f"geschrieben.", logging.ERROR)
                return RECONNECT_DELAY
            state = read_game_state(self.memory)
            self.game_state = state
            if not state.ingame:
                if self._was_ingame:
                    logger.info(f"Nicht mehr ingame ({state.reason}), pausiere.")
                    self._leave_game()
                return self.poll_interval
            if not self._was_ingame:
                logger.info(f"Ingame: {self.table.world_name(state.world_id)}")
                self._was_ingame = True
            if state.world_id != self.current_world:
                if self.current_world is not None:
                    logger.info(f"Weltwechsel: {self.table.world_name(self.current_world)} -> "
                                f"{self.table.world_name(state.world_id)}")
                self.current_world = state.world_id
                self.detector.reset_pending()
            if not self.table.has_world(state.world_id):
                return self.poll_interval  # Welt ohne Orte (z. B. Phaaze)
            flag_read = self.finder.read_flags(state.world_id)
            if flag_read is None:
                return self.poll_interval  # Block (noch) nicht gefunden, erneute Suche gedrosselt
            new = self.detector.update(self.table.collected(state.world_id, flag_read.flags))
            if new:
                await self.report_locations(new)
            self.learning.update(state.world_id, flag_read.flags, state.item_percentage, state.inventory_valid,
                                 flag_read.blocks, flag_read.disagree)
            await self.give_items(state)
            return self.poll_interval
        except ConnectionLost as exc:
            self.memory.disconnect()
            self._leave_game()
            self._status(f"Verbindung zu Dolphin verloren ({exc}). Neuer Versuch in {RECONNECT_DELAY:.0f} s.",
                         logging.WARNING)
            return RECONNECT_DELAY
        except MemoryAccessError as exc:
            # ungültiger Zeiger mitten im Laden o. Ä.: diese Abfrage verwerfen
            logger.debug(f"Abfrage verworfen: {exc}")
            self._leave_game()
            return self.poll_interval

    async def dolphin_sync_loop(self) -> None:
        logger.info("Starte Dolphin-Verbindung. Status: /dolphin")
        while not self.exit_event.is_set():
            try:
                delay = await self.poll_once()
            except Exception:  # noqa: BLE001 - die Schleife darf nie sterben
                logger.error("Unerwarteter Fehler in der Dolphin-Schleife:\n" + traceback.format_exc())
                self.memory.disconnect()
                self._leave_game()
                delay = RECONNECT_DELAY
            try:
                await asyncio.wait_for(self.exit_event.wait(), delay)
            except asyncio.TimeoutError:
                pass
        self.learning.flush()


def main(*args: str) -> None:
    Utils.init_logging("MetroidPrime3Client", exception_logger="Client")
    parser = get_base_parser(description="Metroid Prime 3 Client (Dolphin/PrimeHack, PAL RM3P01)")
    parser.add_argument("--name", default=None, help="Slot-Name")
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL,
                        help=f"Abfrage-Intervall in Sekunden (Standard {DEFAULT_POLL_INTERVAL})")
    parser.add_argument("--no-learning", action="store_true", help="Lernmodus (E19) ausschalten")
    parser.add_argument("--learning-log", default=None, help="Pfad der Lernmodus-Logdatei (JSON-Zeilen)")
    parser.add_argument("url", nargs="?", help="Archipelago-URL archipelago://name:pass@host:port")
    parsed = parser.parse_args(args)
    from CommonClient import handle_url_arg
    parsed = handle_url_arg(parsed, parser=parser)

    async def _main() -> None:
        ctx = MP3Context(parsed.connect, parsed.password, poll_interval=parsed.poll_interval,
                         learning=not parsed.no_learning, learning_log=parsed.learning_log)
        if parsed.name:
            ctx.auth = parsed.name
        logger.info(f"Lernmodus {'an' if ctx.learning.enabled else 'aus'}, Logdatei: {ctx.learning.log_path}")
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        ctx.sync_task = asyncio.create_task(ctx.dolphin_sync_loop(), name="DolphinSync")
        await ctx.exit_event.wait()
        ctx.server_address = None
        await ctx.shutdown()
        if ctx.sync_task:
            await ctx.sync_task
        ctx.memory.disconnect()

    import colorama
    colorama.just_fix_windows_console()
    asyncio.run(_main())
    colorama.deinit()
