"""Metroid Prime 3 Client: CommonClient + Dolphin, location checks and learning mode (T06), item giving and seed check
(T07, T18 part 2).

Start and usage: docs/AP_CLIENT.md.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import traceback
from typing import Any

import Utils
from CommonClient import ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled, logger, server_loop
from NetUtils import ClientStatus

from ..items import BASE_ID, GAME_NAME, item_name_to_id, starting_names
from .checks import CheckDetector, LocationTable
from .flag_block import FlagBlockFinder
from .game import GameState, read_game_state
from .give import ItemGiver
from .goal import GoalDetector
from .inventory import ITEM_EFFECTS, START_INVENTORY_LOCATION, desired_value, effective_items, slot_label
from .learning import LearningMode
from .memory import ConnectionLost, ConnectStatus, MemoryAccess, MemoryAccessError
from .seed_check import SeedCheck, SeedCheckResult, SeedStatus
from .seed_warning import CORE_LOCATIONS, SeedWarning

DEFAULT_POLL_INTERVAL = 0.5
RECONNECT_DELAY = 5.0
SUPPORTED_SLOT_DATA_VERSION = 1

ITEM_ID_TO_NAME: dict[int, str] = {item_id: name for name, item_id in item_name_to_id.items()}


class MP3CommandProcessor(ClientCommandProcessor):
    ctx: "MP3Context"

    def _cmd_dolphin(self) -> None:
        """Shows the state of the Dolphin connection."""
        self.output(self.ctx.status_text())

    def _cmd_learning(self, value: str = "") -> None:
        """Learning mode on/off: /learning on|off (no argument: status)."""
        learning = self.ctx.learning
        if value.lower() in ("on", "1"):
            learning.enabled = True
        elif value.lower() in ("off", "0"):
            learning.flush()
            learning.enabled = False
        self.output(f"Learning mode {'on' if learning.enabled else 'off'}, log file: {learning.log_path}, "
                    f"{learning.entries_written} entries, {learning.warnings} warnings")

    def _cmd_blocks(self) -> None:
        """Shows the flag blocks found per world."""
        finder = self.ctx.finder
        if not finder.blocks:
            self.output("No flag blocks known.")
        for world, addresses in sorted(finder.blocks.items()):
            self.output(f"{self.ctx.table.world_name(world)}: " + ", ".join(f"0x{a:08X}" for a in addresses))
        for world, addresses in sorted(finder.rejected.items()):
            self.output(f"rejected (implausible) {self.ctx.table.world_name(world)}: "
                        + ", ".join(f"0x{a:08X}" for a in addresses))
        self.output(f"Scans: {finder.scan_count}, last {finder.last_scan_seconds:.2f} s")

    def _cmd_seed(self) -> None:
        """Shows the result of the seed check (does the ISO belong to this slot?)."""
        self.output(self.ctx.seed_check.result.message())

    def _cmd_seedwarn(self, value: str = "") -> None:
        """Leviathan seed warnings: /seedwarn on|off (no argument: status)."""
        value = value.lower()
        if value and value not in ("on", "off"):
            self.output("Usage: /seedwarn on|off")
            return
        if value:
            self.ctx.seed_warning.enabled = value == "on"
        self.output(f"Leviathan seed warnings {'on' if self.ctx.seed_warning.enabled else 'off'}.")

    def _cmd_inventory(self) -> None:
        """Shows target and current value of the inventory slots the client manages (as of the last poll)."""
        for line in self.ctx.inventory_lines():
            self.output(line)

    def _cmd_poll(self, seconds: str = "") -> None:
        """Set the poll interval in seconds: /poll 0.5"""
        if seconds:
            try:
                value = float(seconds)
            except ValueError:
                self.output("Number expected, e.g. /poll 0.5")
                return
            self.ctx.poll_interval = min(max(value, 0.1), 5.0)
        self.output(f"Poll interval: {self.ctx.poll_interval} s")


class MP3Context(CommonContext):
    command_processor = MP3CommandProcessor
    game = GAME_NAME
    items_handling = 0b111  # E10: all items come from the server, own ones too

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
        self.seed_check = SeedCheck()
        self.seed_warning = SeedWarning()
        self.giver = ItemGiver(memory, logger)
        self.goal = GoalDetector()
        self.goal_detected = False  # end sequence seen in this client session (T17)
        self.slot_data: dict[str, Any] = {}
        self._announced = 0  # this many entries of items_received have been announced
        self._announced_identity: tuple | None = None
        self._unknown_items: set[int] = set()
        self.dolphin_status = "Dolphin connection not started yet."
        self.game_state: GameState | None = None
        self.current_world: int | None = None
        self.sync_task: asyncio.Task | None = None
        self._was_ingame = False
        self._last_status_message = ""

    # ---- server ------------------------------------------------------------------------------------------------ #

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
                logger.warning(f"slot_data_version {version}, this client knows {SUPPORTED_SLOT_DATA_VERSION}.")
            if self.slot_data.get("base_id", BASE_ID) != BASE_ID:
                logger.error("base_id of the seed does not match this client. Location IDs would be wrong.")
            self._check_slot_data_items()
            identity = getattr(self, "connected_identity", None)
            if identity != self._announced_identity:
                self._announced_identity = identity
                self._announced = 0
                self.seed_warning.core_items.clear()
                self.seed_warning.reset_visit()
            core_locations = sorted(CORE_LOCATIONS & self.server_locations)
            if core_locations:
                Utils.async_start(self.send_msgs([{"cmd": "LocationScouts", "locations": core_locations,
                                                   "create_as_hint": 0}]), name="Scout Leviathan cores")
            # CommonClient sends locations_checked itself on Connected; locations only get there once the seed ID
            # matches this seed/slot (T18). The check runs in the next ingame poll.
            self.watcher_event.set()
        elif cmd == "ReceivedItems":
            self.announce_received_items()
        elif cmd == "LocationInfo":
            for location_id in CORE_LOCATIONS & self.locations_info.keys():
                scout = self.locations_info[location_id]
                recipient = self.slot_info.get(scout.player)
                for_this_slot = scout.player == self.slot or (recipient and self.slot in recipient.group_members)
                self.seed_warning.core_items[location_id] = ITEM_ID_TO_NAME.get(scout.item) if for_this_slot else None

    def _check_slot_data_items(self) -> None:
        """Item IDs and names from ``slot_data`` must match this APWorld (otherwise a different version)."""
        items = self.slot_data.get("items") or {}
        for name, info in items.items():
            local = item_name_to_id.get(name)
            if local is None or local != info.get("id"):
                logger.error(f"Item {name!r} (ID {info.get('id')}) does not match this APWorld (ID {local}). "
                             f"Client and seed are different versions.")
            elif name not in ITEM_EFFECTS:
                logger.error(f"Item {name!r}: no effect known to the client, it will not be given in the game.")

    def announce_received_items(self) -> None:
        """Announces every newly received item once in the client window (name, from whom, where). After a reconnect
        the server sends the list from the start; entries already announced are not repeated."""
        items = self.items_received
        if len(items) <= self._announced:
            return
        for item in items[self._announced:]:
            name = ITEM_ID_TO_NAME.get(item.item, f"unknown item {item.item}")
            if item.location == START_INVENTORY_LOCATION and item.player == 0:
                logger.info(f"Received: {name} (starting inventory)")
                continue
            sender = self.player_names.get(item.player, f"player {item.player}")
            if item.player == self.slot:
                sender = "yourself"
            where = ""
            try:
                location = self.location_names.lookup_in_slot(item.location, item.player)
                if location and not location.startswith("Unknown"):
                    where = f" ({location})"
            except Exception:  # noqa: BLE001 - data package missing: leave out the location
                pass
            logger.info(f"Received: {name} from {sender}{where}")
        self._announced = len(items)

    def make_gui(self):
        ui = super().make_gui()
        ui.base_title = "Archipelago Metroid Prime 3 Client"
        return ui

    @property
    def server_connected(self) -> bool:
        return (self.slot is not None and self.server is not None and self.server.socket is not None
                and not self.server.socket.closed)

    # ---- location checks --------------------------------------------------------------------------------------- #

    async def report_locations(self, pickup_indices: set[int]) -> set[int]:
        """Reports newly detected locations. Each location is sent at most once (``locations_checked``); locations
        the server already reported as checked are not sent again. Without a server connection the locations are
        noted; CommonClient sends ``locations_checked`` with the next ``Connected``."""
        ids = {self.table.location_id(i) for i in pickup_indices}
        new = ids - self.locations_checked
        if not new:
            return set()
        self.locations_checked |= new
        for location_id in sorted(new):
            index = location_id - self.table.base_id
            logger.info(f"Location {index} collected: {self.table.names.get(index, location_id)}")
        if not self.server_connected:
            logger.info(f"{len(new)} location(s) noted, they will be sent after connecting to the server.")
            return set()
        to_send = new - self.checked_locations
        if self.server_locations:
            to_send &= self.server_locations
        if to_send:
            await self.send_msgs([{"cmd": "LocationChecks", "locations": sorted(to_send)}])
        return to_send

    # ---- seed check (T18 part 2) ------------------------------------------------------------------------------- #

    def seed_identity(self) -> tuple[str, int] | None:
        """``(seed_name, slot)`` the ISO is checked against: the connected server, otherwise the last successful
        connection (locations detected offline only go to that slot; CommonClient clears them on a switch)."""
        if self.server_connected and self.server_seed_name and self.slot:
            return self.server_seed_name, self.slot
        identity = getattr(self, "connected_identity", None)
        if identity:
            seed_name, _team, slot = identity
            if seed_name and slot:
                return seed_name, slot
        return None

    def update_seed_check(self) -> SeedCheckResult:
        before = self.seed_check.result
        result = self.seed_check.update(self.memory, self.seed_identity())
        if result != before:
            level = logging.INFO if result.status in (SeedStatus.OK, SeedStatus.WAITING) else logging.ERROR
            logger.log(level, result.message())
            if before.ok:
                # other ISO or other seed/slot: what was detected belonged to the old game
                self.detector.reset()
                self.giver.reset()
                self.seed_warning.reset_visit()
        return result

    # ---- item giving (T07) ------------------------------------------------------------------------------------- #

    def counted_items(self) -> list[str]:
        """All items that go into the target: starting items (``slot_data``) + received items (E11)."""
        starting = self.slot_data.get("starting_items") or starting_names()
        received: list[tuple[str, int]] = []
        for item in self.items_received:
            name = ITEM_ID_TO_NAME.get(item.item)
            if name is None or name not in ITEM_EFFECTS:
                if item.item not in self._unknown_items:
                    self._unknown_items.add(item.item)
                    logger.error(f"Received item {item.item} is unknown to this client and will not be given.")
                continue
            received.append((name, item.location))
        return effective_items(starting, received)

    async def give_items(self, state: GameState) -> None:
        """Item giving by target/current comparison (SPEC E9, E11, ``give.ItemGiver``).

        Only with a server connection (``items_received`` is empty otherwise) and a valid seed ID. The giver only
        writes once ``state.inventory_valid`` (PowerBeam.capacity > 0, E9).
        """
        if not self.seed_check.result.ok or not self.server_connected:
            self.giver.reset()
            return
        self.giver.step(state, self.counted_items())

    def inventory_lines(self) -> list[str]:
        giver = self.giver
        if not giver.last_targets:
            return ["No comparison yet (not ingame, seed not checked or no server connection)."]
        blocked = giver.blocked()
        lines = [f"Item comparison: {len(self.items_received)} items received, {giver.writes_total} writes, "
                 f"{giver.failures_total} failures"]
        for slot, target in sorted(giver.last_targets.items()):
            current = giver.last_inventory.get(slot, (0, 0))
            note = "ok" if desired_value(target, current) == current else "missing"
            if slot in giver.given_up:
                note = "given up (game resets it)"
            elif slot in blocked:
                note = f"blocked for {blocked[slot]:.0f} s"
            lines.append(f"  {slot_label(slot)} (slot {slot}, {target.rule}): target {target.amount}/{target.capacity}, "
                         f"current {current[0]}/{current[1]} - {note}")
        return lines

    def observe_goal(self, state: GameState) -> bool:
        """Goal detection (T17, ``goal.GoalDetector``), one poll. Returns True while the end sequence runs.

        Only with a valid seed ID. Every confirmed start of the end sequence is logged; the goal itself is reported
        by ``send_goal``.
        """
        if not self.goal.available or not self.seed_check.result.ok:
            self.goal.reset()
            return False
        was_confirmed = self.goal.confirmed
        seen = self.goal.observe(self.memory, state)
        if self.goal.confirmed and not was_confirmed:
            self.goal_detected = True
            logger.info(f"Goal reached: {self.goal.goal_event} (end sequence on Phaaze detected). "
                        f"Item giving paused while it runs.")
        return seen

    async def send_goal(self) -> None:
        """Send ``CLIENT_GOAL`` once per server connection (also if the goal was detected while offline)."""
        if not self.goal_detected or self.finished_game or not self.server_connected:
            return
        self.finished_game = True
        logger.info("Goal sent to the server (CLIENT_GOAL).")
        await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])

    # ---- Dolphin loop ------------------------------------------------------------------------------------------ #

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
                lines.append(f"Ingame, world {self.table.world_name(state.world_id)}, "
                             f"ItemPercentage {state.item_percentage}")
            else:
                lines.append(f"Not ingame: {state.reason}")
        lines.append(self.seed_check.result.message())
        lines.append(f"Locations detected: {len(self.locations_checked)}, items received: {len(self.items_received)}, "
                     f"inventory writes: {self.giver.writes_total}, "
                     f"learning mode {'on' if self.learning.enabled else 'off'}")
        goal = "sent" if self.finished_game else ("detected, not sent yet" if self.goal_detected else "not reached")
        lines.append(f"Goal ({self.goal.goal_event}): {goal}, end sequence seen {self.goal.detections} time(s)")
        return "\n".join(lines)

    def _leave_game(self) -> None:
        """Menu, loading or lost connection: forget everything tied to the game session."""
        self.finder.reset()
        self.detector.reset_pending()
        self.learning.reset()
        self.giver.reset()
        self.goal.reset()
        self.current_world = None
        self._was_ingame = False

    async def poll_once(self) -> float:
        """One poll. Returns the delay until the next one."""
        if not self.memory.connected:
            if self._was_ingame or self.dolphin_status.startswith("Connected to Dolphin"):
                self._status("Lost connection to Dolphin, reconnecting ...", logging.WARNING)
            self._leave_game()
            self.seed_warning.reset_visit()
            self.game_state = None
            result = self.memory.connect()
            if result.status is not ConnectStatus.CONNECTED:
                level = logging.ERROR if result.status is ConnectStatus.WRONG_GAME else logging.INFO
                self._status(result.message + f" Next attempt in {RECONNECT_DELAY:.0f} s.", level)
                return RECONNECT_DELAY
            self._status(result.message)
        try:
            if not self.memory.check_game_id():
                self._leave_game()
                self._status(f"Game ID changed ({self.memory.last_game_id!r}). Disconnected, nothing will be "
                             f"written.", logging.ERROR)
                return RECONNECT_DELAY
            state = read_game_state(self.memory)
            self.game_state = state
            await self.send_goal()  # goal detected while offline: report as soon as the server is back
            if not state.ingame:
                if self._was_ingame:
                    logger.info(f"No longer ingame ({state.reason}), pausing.")
                    self._leave_game()
                return self.poll_interval
            if not self._was_ingame:
                logger.info(f"Ingame: {self.table.world_name(state.world_id)}")
                self._was_ingame = True
            if state.world_id != self.current_world:
                if self.current_world is not None:
                    logger.info(f"World change: {self.table.world_name(self.current_world)} -> "
                                f"{self.table.world_name(state.world_id)}")
                self.current_world = state.world_id
                self.detector.reset_pending()
            seed = self.update_seed_check()
            await self.poll_checks(state, seed.ok)
            if self.observe_goal(state):
                # end sequence: the game strips suit and grapples on purpose, do not give them back (T17)
                self.giver.reset()
            else:
                await self.give_items(state)
            if seed.ok:
                warning = self.seed_warning.observe(self.memory, state)
                if warning:
                    logger.warning(warning, extra={"compact_gui": True})
            await self.send_goal()
            return self.poll_interval
        except ConnectionLost as exc:
            self.memory.disconnect()
            self._leave_game()
            self._status(f"Lost connection to Dolphin ({exc}). Next attempt in {RECONNECT_DELAY:.0f} s.",
                         logging.WARNING)
            return RECONNECT_DELAY
        except MemoryAccessError as exc:
            # invalid pointer in the middle of loading or similar: drop this poll
            logger.debug(f"Poll dropped: {exc}")
            self._leave_game()
            return self.poll_interval

    async def poll_checks(self, state: GameState, seed_ok: bool) -> None:
        """Read the world's flag block, detect locations (only with a matching seed ID), learning mode."""
        if not self.table.has_world(state.world_id):
            return  # world without locations (e.g. Phaaze)
        flag_read = self.finder.read_flags(state.world_id)
        if flag_read is None:
            return  # block not found (yet), rescan is throttled
        if seed_ok:
            new = self.detector.update(self.table.collected(state.world_id, flag_read.flags))
            if new:
                await self.report_locations(new)
        self.learning.update(state.world_id, flag_read.flags, state.item_percentage, state.inventory_valid,
                             flag_read.blocks, flag_read.disagree)

    async def dolphin_sync_loop(self) -> None:
        logger.info("Starting Dolphin connection. Status: /dolphin")
        while not self.exit_event.is_set():
            try:
                delay = await self.poll_once()
            except Exception:  # noqa: BLE001 - the loop must never die
                logger.error("Unexpected error in the Dolphin loop:\n" + traceback.format_exc())
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
    parser.add_argument("--name", default=None, help="slot name")
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL,
                        help=f"poll interval in seconds (default {DEFAULT_POLL_INTERVAL})")
    parser.add_argument("--no-learning", action="store_true", help="turn off the learning mode (E19)")
    parser.add_argument("--learning-log", default=None, help="path of the learning mode log file (JSON lines)")
    parser.add_argument("url", nargs="?", help="Archipelago URL archipelago://name:pass@host:port")
    parsed = parser.parse_args(args)
    from CommonClient import handle_url_arg
    parsed = handle_url_arg(parsed, parser=parser)

    async def _main() -> None:
        ctx = MP3Context(parsed.connect, parsed.password, poll_interval=parsed.poll_interval,
                         learning=not parsed.no_learning, learning_log=parsed.learning_log)
        if parsed.name:
            ctx.auth = parsed.name
        logger.info(f"Learning mode {'on' if ctx.learning.enabled else 'off'}, log file: {ctx.learning.log_path}")
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
