"""Client part 1 (T06): signature search, game ID, menu/loading, location checks, learning mode - with fake memory."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import unittest

from ..client import flag_block, game
from ..client.checks import CheckDetector, LocationTable
from ..client.context import RECONNECT_DELAY, MP3Context
from ..client.flag_block import FlagBlockFinder
from ..client.learning import LearningMode
from ..client.memory import MEM1_START, ConnectStatus, NotConnected
from ..items import BASE_ID
from ..location_flags import LOCATION_FLAGS
from ..patcher.seed_id import make_seed_id
from .fake_memory import FakeMemory

NORION = 0x6FB8EF2A9523C343
VALHALLA = 0xC133F919C108BDF9
OLYMPUS = 0x37A9E86F0A0CAF6F

STATIC_LIMIT = 0x80700000  # everything below is DOL/static data (state pointers, game ID, build string)
TEST_SEED = "T07TestSeed"


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def connected_memory() -> FakeMemory:
    memory = FakeMemory()
    assert memory.connect().status is ConnectStatus.CONNECTED
    return memory


class TestFlagBlockFinder(unittest.TestCase):
    def test_finds_block(self) -> None:
        memory = connected_memory()
        w = memory.place_block(0x80A13AA0, NORION)
        finder = FlagBlockFinder(memory)
        self.assertEqual(finder.get(NORION), [w])
        self.assertEqual(finder.scan_count, 1)

    def test_finds_block_at_chunk_border(self) -> None:
        memory = connected_memory()
        w = memory.place_block(MEM1_START + 0x300000 + 4, NORION)  # guard in one chunk, MLVL ID in the next
        memory.place_block(MEM1_START + 0x500000 - 4, VALHALLA)
        finder = FlagBlockFinder(memory)
        self.assertEqual(finder.get(NORION), [w])
        self.assertEqual(finder.get(VALHALLA), [MEM1_START + 0x500000 - 4])

    def test_block_moved_is_found_again(self) -> None:
        memory = connected_memory()
        clock = FakeClock()
        old = memory.place_block(0x80A1FD40, VALHALLA)
        memory.set_flag(old, 1)
        finder = FlagBlockFinder(memory, clock=clock)
        self.assertEqual(finder.get(VALHALLA), [old])
        new = memory.move_block(old, 0x80A49CC0, VALHALLA)  # like T10 after reloading
        read = finder.read_flags(VALHALLA)  # remembered address invalid -> rescan at once
        self.assertEqual(read.blocks, (new,))
        self.assertEqual(read.flags[1], 1)
        self.assertEqual(finder.scan_count, 2)

    def test_cached_block_is_not_rescanned(self) -> None:
        memory = connected_memory()
        memory.place_block(0x80A13AA0, NORION)
        finder = FlagBlockFinder(memory)
        for _ in range(5):
            finder.read_flags(NORION)
        self.assertEqual(finder.scan_count, 1)

    def test_signature_checks(self) -> None:
        memory = connected_memory()
        finder = FlagBlockFinder(memory)
        good = memory.place_block(0x80A00000, NORION)
        self.assertTrue(finder.validate(good, NORION))
        self.assertFalse(finder.validate(good, VALHALLA))  # other world
        bad_guard = memory.place_block(0x80A10000, NORION)
        memory.poke(bad_guard - 4, b"\0\0\0\0")
        bad_count = memory.place_block(0x80A20000, NORION)
        memory.poke_u32(bad_count + flag_block.OFF_FLAG_COUNT, 0x200)
        bad_savw = memory.place_block(0x80A30000, VALHALLA, savw_ok=False)
        for address, world in ((bad_guard, NORION), (bad_count, NORION), (bad_savw, VALHALLA)):
            self.assertFalse(finder.validate(address, world), hex(address))
        self.assertEqual(finder.scan().get(NORION), [good])
        self.assertNotIn(VALHALLA, finder.blocks)

    def test_several_blocks_or_merged(self) -> None:
        """Assumption (T14): all valid blocks of the world are merged with OR, differences are reported."""
        memory = connected_memory()
        main = memory.place_block(0x80A13AA0, NORION)
        copy = memory.place_block(0x811EBA40, NORION)  # like T10 snapshot C1
        other = memory.place_block(0x80A49CC0, VALHALLA)
        for b in (1, 6, 8):
            memory.set_flag(main, b)
        memory.set_flag(other, 7)
        read = FlagBlockFinder(memory).read_flags(NORION)
        self.assertEqual(read.blocks, (main, copy))
        self.assertEqual([i for i, v in enumerate(read.flags) if v], [1, 6, 8])
        self.assertEqual(read.disagree, (1, 6, 8))

    def test_implausible_block_rejected(self) -> None:
        """Like T10 "Pirate Homeworld - Command" 0x80A11900: header valid, bytes behind list 1 set -> rejected."""
        memory = connected_memory()
        command = 0x38098524EF78B6D2  # list 1: 209 entries
        good = memory.place_block(0x80A22E20, command)
        junk = memory.place_block(0x80A11900, command)
        memory.set_flag(junk, 1)  # would be location 86
        memory.set_flag(junk, 670)
        finder = FlagBlockFinder(memory)
        read = finder.read_flags(command)
        self.assertEqual(read.blocks, (good,))
        self.assertEqual(finder.rejected[command], [junk])
        self.assertEqual(LocationTable().collected(command, read.flags), set())
        # a remembered block becomes implausible later: rescan, the block drops out
        memory.set_flag(good, 300)
        self.assertIsNone(finder.read_flags(command))

    def test_not_found_rescan_is_throttled(self) -> None:
        memory = connected_memory()
        clock = FakeClock()
        finder = FlagBlockFinder(memory, rescan_interval=2.0, clock=clock)
        self.assertIsNone(finder.read_flags(NORION))
        self.assertIsNone(finder.read_flags(NORION))
        self.assertEqual(finder.scan_count, 1)
        clock.t += 2.5
        memory.place_block(0x80A13AA0, NORION)
        self.assertIsNotNone(finder.read_flags(NORION))
        self.assertEqual(finder.scan_count, 2)

    @unittest.skipUnless(os.environ.get("MP3_MEM1_SNAPSHOT"), "MP3_MEM1_SNAPSHOT (T10 snapshot D2_mem1.bin) missing")
    def test_real_snapshot(self) -> None:
        """Cross-check on the real memory dump from T10 (snapshot D2: Norion, locations 3 and 4 collected)."""
        memory = connected_memory()
        with open(os.environ["MP3_MEM1_SNAPSHOT"], "rb") as f:
            memory.mem1[:] = f.read()
        memory.verified = True  # the snapshot contains the game ID; connect() checked it
        finder = FlagBlockFinder(memory)
        blocks = finder.scan()
        self.assertEqual(blocks[NORION], [0x80A13AA0])
        self.assertEqual(blocks[VALHALLA], [0x80A49CC0])
        self.assertEqual(len(blocks), 14)  # blocks of all worlds with locations are in memory
        command = 0x38098524EF78B6D2
        self.assertEqual(blocks[command], [0x80A22E20])
        self.assertEqual(finder.rejected[command], [0x80A11900])  # garbage behind list 1
        table = LocationTable()
        self.assertEqual(table.collected(NORION, finder.read_flags(NORION).flags), {3, 4})
        self.assertEqual(table.collected(VALHALLA, finder.read_flags(VALHALLA).flags), {11})


class TestMemory(unittest.TestCase):
    def test_wrong_game_id_is_refused(self) -> None:
        memory = FakeMemory(game_id=b"RM3E01")
        result = memory.connect()
        self.assertIs(result.status, ConnectStatus.WRONG_GAME)
        self.assertIn("RM3E01", result.message)
        self.assertFalse(memory.connected)
        self.assertFalse(memory.hooked)
        with self.assertRaises(NotConnected):
            memory.write(0x80995B74, b"\0\0\0\1")
        with self.assertRaises(NotConnected):
            memory.read(0x80680234, 4)
        self.assertEqual(memory.writes, [])

    def test_no_game(self) -> None:
        memory = FakeMemory(game_id=bytes(6))
        self.assertIs(memory.connect().status, ConnectStatus.NO_GAME)

    def test_no_dolphin(self) -> None:
        memory = FakeMemory()
        memory.running = False
        self.assertIs(memory.connect().status, ConnectStatus.NO_DOLPHIN)

    def test_game_state(self) -> None:
        memory = connected_memory()
        memory.set_ingame(NORION, item_percentage=2)
        state = game.read_game_state(memory)
        self.assertTrue(state.ingame)
        self.assertEqual(state.world_id, NORION)
        self.assertEqual(state.item_percentage, 2)
        self.assertTrue(state.inventory_valid)
        memory.set_menu()
        self.assertFalse(game.read_game_state(memory).ingame)
        memory.set_ingame(NORION)
        memory.poke_u32(0x80B81AE0, 0x80001234)  # wrong vtable
        self.assertFalse(game.read_game_state(memory).ingame)


class RecordingContext(MP3Context):
    """MP3Context without a server: ``send_msgs`` is recorded, the server connection is simulated."""

    fake_server = True

    @property
    def server_connected(self) -> bool:  # type: ignore[override]
        return self.fake_server

    async def send_msgs(self, msgs) -> None:  # type: ignore[override]
        self.sent.extend(msgs)


def make_context(memory: FakeMemory, log_path: str, seed_ok: bool = True) -> RecordingContext:
    """Context as after ``Connected`` with seed ``TEST_SEED``, slot 1. ``seed_ok``: the ISO carries the matching ID."""
    ctx = RecordingContext(None, None, memory=memory, learning_log=log_path)
    ctx.sent = []
    ctx.slot = 1
    ctx.team = 0
    ctx.server_seed_name = TEST_SEED
    ctx.connected_identity = (TEST_SEED, 0, 1)
    ctx.missing_locations = {BASE_ID + i for i in LOCATION_FLAGS}
    ctx.server_locations = set(ctx.missing_locations)
    if seed_ok:
        memory.set_seed_id(make_seed_id(TEST_SEED, 1))
    return ctx


def location_checks(ctx: RecordingContext) -> list[int]:
    return [loc for msg in ctx.sent if msg["cmd"] == "LocationChecks" for loc in msg["locations"]]


class TestContext(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = os.path.join(self.tmp.name, "learning.jsonl")
        logging.getLogger("Client").setLevel(logging.CRITICAL)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def poll(self, ctx: MP3Context, times: int = 1) -> float:
        delay = 0.0
        for _ in range(times):
            delay = await ctx.poll_once()
        return delay

    async def test_wrong_game_id_reads_nothing_else(self) -> None:
        memory = FakeMemory(game_id=b"GZLE99")
        ctx = make_context(memory, self.log_path)
        self.assertEqual(await self.poll(ctx), RECONNECT_DELAY)
        self.assertEqual(memory.reads, [(MEM1_START, 6)])
        self.assertEqual(memory.writes, [])
        self.assertIn("GZLE99", ctx.dolphin_status)

    async def test_menu_and_loading_read_nothing(self) -> None:
        memory = FakeMemory()
        block = memory.place_block(0x80A13AA0, NORION)
        memory.set_flag(block, 8)
        memory.set_ingame(NORION)
        memory.set_menu()
        ctx = make_context(memory, self.log_path)
        await self.poll(ctx, 4)
        self.assertEqual(ctx.finder.scan_count, 0)
        self.assertEqual(memory.writes, [])
        self.assertTrue(all(address < STATIC_LIMIT or address == 0x80900000 + game.OFF_CPLAYER
                            for address, _ in memory.reads), memory.reads)
        self.assertEqual(location_checks(ctx), [])

    async def test_new_byte_sends_exactly_one_check(self) -> None:
        memory = FakeMemory()
        block = memory.place_block(0x80A13AA0, NORION)
        memory.set_ingame(NORION, item_percentage=1)
        ctx = make_context(memory, self.log_path)
        await self.poll(ctx, 3)
        self.assertEqual(location_checks(ctx), [])
        memory.set_flag(block, 8)  # location 4, Norion Docking Hub Alpha
        memory.set_item_percentage(2)
        await self.poll(ctx, 6)
        self.assertEqual(location_checks(ctx), [BASE_ID + 4])
        self.assertEqual(BASE_ID + 4, 1297101572)
        self.assertEqual(memory.writes, [])

    async def test_world_change_and_reload_no_duplicates(self) -> None:
        memory = FakeMemory()
        norion = memory.place_block(0x80A13AA0, NORION)
        memory.set_ingame(NORION, item_percentage=1)
        ctx = make_context(memory, self.log_path)
        memory.set_flag(norion, 7)  # location 3
        await self.poll(ctx, 3)
        self.assertEqual(location_checks(ctx), [BASE_ID + 3])
        # flight to Valhalla: loading phase (CPlayer 0), then new world
        memory.set_menu()
        await self.poll(ctx, 2)
        valhalla = memory.place_block(0x80A1FD40, VALHALLA)
        memory.set_ingame(VALHALLA, item_percentage=1)
        await self.poll(ctx, 2)
        memory.set_flag(valhalla, 1)  # location 11
        memory.set_item_percentage(2)
        await self.poll(ctx, 3)
        # reload the save: the block moves, the content stays
        memory.set_menu()
        await self.poll(ctx, 2)
        memory.move_block(valhalla, 0x80A49CC0, VALHALLA)
        memory.set_ingame(VALHALLA, item_percentage=2)
        await self.poll(ctx, 4)
        # back to Norion: the old block is still there, location 3 is not sent again
        memory.set_ingame(NORION, item_percentage=2)
        await self.poll(ctx, 4)
        self.assertEqual(location_checks(ctx), [BASE_ID + 3, BASE_ID + 11])
        self.assertEqual(memory.writes, [])

    async def test_checks_kept_while_server_offline(self) -> None:
        """Server briefly gone (connected before, ID matches that connection): locations are noted."""
        memory = FakeMemory()
        block = memory.place_block(0x80A13AA0, NORION)
        memory.set_ingame(NORION)
        ctx = make_context(memory, self.log_path)
        ctx.fake_server = False
        ctx.server_seed_name = None  # like after reset_server_state, connected_identity stays
        memory.set_flag(block, 8)
        await self.poll(ctx, 3)
        self.assertEqual(location_checks(ctx), [])
        self.assertEqual(ctx.locations_checked, {BASE_ID + 4})  # CommonClient sends them with Connected

    async def test_never_connected_notes_nothing(self) -> None:
        """T18: without ever having been connected to the server the ID cannot be checked -> note nothing."""
        memory = FakeMemory()
        block = memory.place_block(0x80A13AA0, NORION)
        memory.set_ingame(NORION)
        ctx = make_context(memory, self.log_path)
        ctx.fake_server = False
        ctx.server_seed_name = None
        ctx.connected_identity = None
        memory.set_flag(block, 8)
        await self.poll(ctx, 3)
        self.assertEqual(ctx.locations_checked, set())
        self.assertEqual(ctx.seed_check.result.status.value, "waiting")
        self.assertEqual(memory.writes, [])

    async def test_server_already_checked_not_resent(self) -> None:
        memory = FakeMemory()
        block = memory.place_block(0x80A13AA0, NORION)
        memory.set_ingame(NORION)
        ctx = make_context(memory, self.log_path)
        ctx.checked_locations = {BASE_ID + 4}
        memory.set_flag(block, 8)
        memory.set_flag(block, 7)
        await self.poll(ctx, 3)
        self.assertEqual(location_checks(ctx), [BASE_ID + 3])

    async def test_connection_loss_and_reconnect(self) -> None:
        memory = FakeMemory()
        block = memory.place_block(0x80A13AA0, NORION)
        memory.set_ingame(NORION)
        ctx = make_context(memory, self.log_path)
        await self.poll(ctx, 2)
        memory.fail_reads = True
        self.assertEqual(await self.poll(ctx), RECONNECT_DELAY)
        self.assertFalse(memory.connected)
        memory.fail_reads = False
        memory.set_flag(block, 8)
        await self.poll(ctx, 3)
        self.assertTrue(memory.connected)
        self.assertEqual(location_checks(ctx), [BASE_ID + 4])

    async def test_learning_mode_logs_unknown_byte(self) -> None:
        memory = FakeMemory()
        block = memory.place_block(0x80A13AA0, NORION)
        memory.set_ingame(NORION, item_percentage=1)
        ctx = make_context(memory, self.log_path)
        clock = FakeClock()
        ctx.learning.clock = clock
        await self.poll(ctx, 2)
        memory.set_flag(block, 118)  # not assigned to any location in Norion (T10: set together with location 4)
        memory.set_item_percentage(2)
        for _ in range(6):
            clock.t += 0.5
            await self.poll(ctx)
        with open(self.log_path, encoding="utf-8") as f:
            records = [json.loads(line) for line in f]
        pickups = [r for r in records if r["kind"] == "pickup"]
        self.assertEqual(len(pickups), 1)
        entry = pickups[0]
        self.assertEqual(entry["world"], "Norion")
        self.assertEqual(entry["item_percentage"], [1, 2])
        self.assertEqual([b["byte"] for b in entry["bytes"]], [118])
        self.assertEqual(entry["bytes"][0]["role"], "unknown")
        self.assertTrue(any("not assigned to any location" in w for w in entry["warnings"]))
        self.assertTrue(any("without the expected location byte" in w for w in entry["warnings"]))
        self.assertEqual(location_checks(ctx), [])


class TestLearningMode(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "l.jsonl")
        self.clock = FakeClock()
        self.mode = LearningMode(LocationTable(), self.path, logging.getLogger("test"), clock=self.clock,
                                 wall_clock=lambda: "t")
        logging.getLogger("test").setLevel(logging.CRITICAL)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def records(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def step(self, flags: bytearray, percentage: int, dt: float = 0.5) -> None:
        self.clock.t += dt
        self.mode.update(NORION, bytes(flags), percentage, True)

    def test_expected_byte_no_warning(self) -> None:
        flags = bytearray(1024)
        self.step(flags, 1)
        flags[8] = 1  # location 4
        self.step(flags, 2)
        for _ in range(5):
            self.step(flags, 2)
        (entry,) = self.records()
        self.assertEqual(entry["bytes"][0]["location"], 4)
        self.assertEqual(entry["room"], "Docking Hub Alpha")
        self.assertEqual(entry["warnings"], [])

    def test_byte_set_before_percentage(self) -> None:
        """SpecialFunction locations: the byte can come seconds before the ItemPercentage rise (window ``before``)."""
        flags = bytearray(1024)
        self.step(flags, 1)
        flags[53] = 1  # location 9 (SpecialFunction)
        self.step(flags, 1)
        for _ in range(8):
            self.step(flags, 1)
        self.step(flags, 2)
        for _ in range(5):
            self.step(flags, 2)
        (entry,) = self.records()
        self.assertEqual(entry["bytes"][0]["location"], 9)
        self.assertEqual(entry["warnings"], [])

    def test_location_byte_without_pickup(self) -> None:
        flags = bytearray(1024)
        self.step(flags, 1)
        flags[7] = 1  # location 3, but ItemPercentage stays
        self.step(flags, 1)
        for _ in range(25):
            self.step(flags, 1)
        (entry,) = self.records()
        self.assertEqual(entry["kind"], "location_byte_without_pickup")
        self.assertEqual(entry["location"], 3)

    def test_inventory_fill_after_load_is_not_a_pickup(self) -> None:
        flags = bytearray(1024)
        self.clock.t += 0.5
        self.mode.update(NORION, bytes(flags), 0, False)  # intro: inventory 0/0
        self.step(flags, 5)  # inventory filled
        for _ in range(6):
            self.step(flags, 5)
        self.assertEqual(self.records(), [])


class TestTableAndDetector(unittest.TestCase):
    def test_table(self) -> None:
        table = LocationTable()
        flags = bytearray(1024)
        flags[7] = flags[8] = flags[118] = 1
        self.assertEqual(table.collected(NORION, bytes(flags)), {3, 4})
        self.assertEqual(table.collected(VALHALLA, bytes(flags)), set())
        self.assertEqual(table.describe(NORION, 118).role, "unknown")
        self.assertEqual(table.describe(0xC37F4AD853284C78, 231).role, "extra")  # other_bytes of location 64
        self.assertEqual(sum(len(v) for v in table.by_world.values()), 99)

    def test_detector_debounce(self) -> None:
        detector = CheckDetector(confirm_polls=2)
        self.assertEqual(detector.update({4}), set())
        self.assertEqual(detector.update({4}), {4})
        self.assertEqual(detector.update({4}), set())
        self.assertEqual(detector.update({3}), set())
        self.assertEqual(detector.update(set()), set())  # only set briefly: dropped
        self.assertEqual(detector.update({3}), set())
        self.assertEqual(detector.update({3}), {3})
