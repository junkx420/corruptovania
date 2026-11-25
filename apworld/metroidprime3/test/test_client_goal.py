"""Goal detection (T17, measured in T08): end sequence after Aurora Unit 313 = Phaaze + slot 41 HyperModePhaaze 0/1."""

from __future__ import annotations

import logging
import os
import tempfile
import unittest

from NetUtils import ClientStatus

from ..client import inventory as inv
from ..client.game import read_game_state
from ..client.goal import PHAAZE_WORLD_ID, SLOT_HYPER_MODE_PHAAZE, GoalDetector, ending_sequence
from ..patcher.seed_id import make_seed_id
from .fake_memory import FakeMemory
from .test_client import NORION, FakeClock, make_context
from .test_client_items import network_item

PHAAZE = PHAAZE_WORLD_ID


def goal_messages(ctx) -> list[dict]:
    return [msg for msg in ctx.sent if msg["cmd"] == "StatusUpdate" and msg["status"] == ClientStatus.CLIENT_GOAL]


class TestEndingCondition(unittest.TestCase):
    """``ending_sequence`` and ``GoalDetector`` on fake memory, values as measured live (T08/T17)."""

    def setUp(self) -> None:
        self.memory = FakeMemory()
        self.memory.connect()

    def seen(self) -> bool:
        return ending_sequence(self.memory, read_game_state(self.memory))

    def test_phaaze_course(self) -> None:
        self.memory.set_ingame(PHAAZE)
        self.memory.set_slot(SLOT_HYPER_MODE_PHAAZE, 0, 0)  # arrival on Phaaze
        self.assertFalse(self.seen())
        self.memory.set_slot(SLOT_HYPER_MODE_PHAAZE, 1, 1)  # permanent Phaaze Hypermode, final battle
        self.assertFalse(self.seen())
        self.memory.set_slot(SLOT_HYPER_MODE_PHAAZE, 0, 1)  # end cutscene and credits
        self.assertTrue(self.seen())

    def test_other_world_or_values(self) -> None:
        self.memory.set_ingame(NORION)
        self.memory.set_slot(SLOT_HYPER_MODE_PHAAZE, 0, 1)
        self.assertFalse(self.seen())
        self.memory.set_ingame(PHAAZE)
        for value in ((1, 1), (0, 0), (1, 0), (0, 2)):
            self.memory.set_slot(SLOT_HYPER_MODE_PHAAZE, *value)
            self.assertFalse(self.seen(), value)

    def test_menu_and_empty_inventory(self) -> None:
        self.memory.set_ingame(PHAAZE)
        self.memory.set_slot(SLOT_HYPER_MODE_PHAAZE, 0, 1)
        self.memory.set_menu()
        self.assertFalse(self.seen())
        self.memory.set_ingame(PHAAZE, power_beam=0)  # inventory not filled yet
        self.assertFalse(self.seen())

    def test_detector_needs_consecutive_polls(self) -> None:
        detector = GoalDetector(confirm_polls=2)
        self.memory.set_ingame(PHAAZE)
        self.memory.set_slot(SLOT_HYPER_MODE_PHAAZE, 0, 1)
        state = read_game_state(self.memory)
        self.assertFalse(detector.reached(self.memory, state))
        self.memory.set_slot(SLOT_HYPER_MODE_PHAAZE, 1, 1)  # glitch: not two in a row
        self.assertFalse(detector.reached(self.memory, state))
        self.memory.set_slot(SLOT_HYPER_MODE_PHAAZE, 0, 1)
        self.assertFalse(detector.reached(self.memory, state))
        self.assertTrue(detector.reached(self.memory, state))
        self.assertTrue(detector.reached(self.memory, state))
        self.assertEqual(detector.detections, 1)

    def test_client_never_writes_slot_41(self) -> None:
        self.assertIn(SLOT_HYPER_MODE_PHAAZE, inv.READ_ONLY_SLOTS)
        for effect in inv.ITEM_EFFECTS.values():
            grants = [g for stage in effect.stages for g in stage] + list(effect.also)
            self.assertNotIn(SLOT_HYPER_MODE_PHAAZE, [g.slot for g in grants])


class TestGoalContext(unittest.IsolatedAsyncioTestCase):
    """Whole client: CLIENT_GOAL once, no item giving during the end sequence, wrong seed, offline."""

    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        logging.getLogger("Client").setLevel(logging.CRITICAL)
        self.memory = FakeMemory()
        self.memory.set_ingame(PHAAZE, item_percentage=43)
        self.memory.set_slot(SLOT_HYPER_MODE_PHAAZE, 1, 1)
        self.ctx = make_context(self.memory, os.path.join(self.tmp.name, "learning.jsonl"))
        self.ctx.player_names = {0: "Archipelago", 1: "Samus", 2: "Finder"}
        self.clock = FakeClock()
        self.ctx.giver.clock = self.clock
        from CommonClient import process_server_cmd
        await process_server_cmd(self.ctx, {"cmd": "ReceivedItems", "index": 0, "items": [
            network_item("Hazard Shield"), network_item("Grapple Lasso"), network_item("Grapple Swing")]})

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def poll(self, times: int = 1) -> None:
        for _ in range(times):
            self.clock.t += 0.5
            await self.ctx.poll_once()

    def start_ending(self) -> None:
        """As measured at 15:54:10: suit 5 -> 0, grapples 1 -> 0 (capacity stays), slot 41 1/1 -> 0/1."""
        self.memory.set_slot(inv.SUIT, 0, 6)
        self.memory.set_slot(inv.GRAPPLE_LASSO, 0, 1)
        self.memory.set_slot(inv.GRAPPLE_SWING, 0, 1)
        self.memory.set_slot(SLOT_HYPER_MODE_PHAAZE, 0, 1)

    async def test_goal_sent_once_and_no_writes_in_ending(self) -> None:
        await self.poll(4)  # final battle: items given, no goal
        self.assertEqual(self.memory.slot(inv.SUIT), (5, 6))
        self.assertEqual(goal_messages(self.ctx), [])
        self.memory.writes.clear()
        with self.assertLogs("Client", logging.INFO) as logs:
            self.start_ending()
            await self.poll(10)  # end cutscene + credits
        self.assertEqual(len(goal_messages(self.ctx)), 1)
        self.assertTrue(self.ctx.finished_game)
        self.assertEqual(self.memory.writes, [])  # suit and grapples stay as the game set them
        self.assertEqual(self.memory.slot(inv.SUIT), (0, 6))
        messages = [r.getMessage() for r in logs.records]
        self.assertEqual(sum(m.startswith("Goal reached: Aurora Unit 313") for m in messages), 1)
        self.assertIn("Goal sent to the server (CLIENT_GOAL).", messages)
        self.assertIn("Goal (Aurora Unit 313): sent, end sequence seen 1 time(s)", self.ctx.status_text())

    async def test_repeat_after_reload(self) -> None:
        save = self.memory.save()
        await self.poll(4)
        before_fight = self.memory.save()
        self.start_ending()
        await self.poll(3)
        # savestate/reload before the final battle: slot 41 1/1 again, items given again, then the ending once more
        self.memory.load(before_fight, PHAAZE)
        await self.poll(4)
        self.assertEqual(self.memory.slot(SLOT_HYPER_MODE_PHAAZE), (1, 1))
        self.assertEqual(self.memory.slot(inv.SUIT), (5, 6))
        self.start_ending()
        with self.assertLogs("Client", logging.INFO) as logs:
            await self.poll(3)
        self.assertEqual(self.ctx.goal.detections, 2)
        self.assertTrue(any(r.getMessage().startswith("Goal reached") for r in logs.records))
        self.assertEqual(len(goal_messages(self.ctx)), 1)  # reported once per connection
        self.assertTrue(save)

    async def test_wrong_seed_no_goal(self) -> None:
        self.memory.set_seed_id(make_seed_id("OtherSeed", 1))
        self.start_ending()
        await self.poll(5)
        self.assertEqual(goal_messages(self.ctx), [])
        self.assertFalse(self.ctx.goal_detected)

    async def test_detected_offline_sent_after_connect(self) -> None:
        await self.poll(2)
        self.ctx.fake_server = False
        self.start_ending()
        await self.poll(3)
        self.assertTrue(self.ctx.goal_detected)
        self.assertEqual(goal_messages(self.ctx), [])
        self.memory.set_menu()  # credits over, back in the menu
        await self.poll(2)
        self.ctx.fake_server = True
        await self.poll(1)
        self.assertEqual(len(goal_messages(self.ctx)), 1)

    async def test_no_goal_without_ending(self) -> None:
        self.memory.set_slot(SLOT_HYPER_MODE_PHAAZE, 0, 0)
        await self.poll(5)
        self.memory.set_ingame(NORION)
        self.memory.set_slot(SLOT_HYPER_MODE_PHAAZE, 0, 1)
        await self.poll(5)
        self.assertEqual(goal_messages(self.ctx), [])
