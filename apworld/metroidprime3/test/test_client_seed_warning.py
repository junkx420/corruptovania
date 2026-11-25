"""Leviathan seed entry warnings with fake Dolphin memory and CommonClient packets."""

import asyncio
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from CommonClient import process_server_cmd
from NetUtils import NetworkSlot, SlotType

from ..client import inventory as inv
from ..items import BASE_ID, item_name_to_id
from ..patcher.seed_id import make_seed_id
from .fake_memory import FakeMemory
from .test_client import NORION, TEST_SEED, make_context

BRYYO = 0xCD79C43EB6C801FD
ELYSIA = 0x94BCA72AB1CFEC05
PIRATE_HOMEWORLD = 0xDE97D48188CA8C99


class TestSeedWarning(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.memory = FakeMemory()
        self.memory.set_ingame(NORION)
        self.ctx = make_context(self.memory, str(Path(temporary.name) / "learning.jsonl"))
        self.ctx.learning.enabled = False
        await self.connect()

    async def connect(self, seed_name: str = TEST_SEED) -> None:
        self.ctx.server_seed_name = seed_name
        with patch("CommonClient.Utils.persistent_store"):
            await process_server_cmd(self.ctx, {"cmd": "Connected", "team": 0, "slot": 1, "players": [],
                                                "slot_info": {3: NetworkSlot("Link", self.ctx.game, SlotType.group,
                                                                            (1, 2))},
                                                "missing_locations": [BASE_ID + i for i in (97, 98, 99)],
                                                "checked_locations": [], "slot_data": {"slot_data_version": 1}})
        await asyncio.sleep(0)  # run the scout request queued by on_package

    async def scout(self, *placements: tuple[int, str, int]) -> None:
        locations = [[item_name_to_id[item], BASE_ID + index, recipient, 0]
                     for index, item, recipient in placements]
        await process_server_cmd(self.ctx, {"cmd": "LocationInfo", "locations": locations})

    async def warnings(self, polls: int = 1) -> list[str]:
        with self.assertLogs("Client", logging.DEBUG) as logs:
            logging.getLogger("Client").debug("Polling fake memory")
            for _ in range(polls):
                await self.ctx.poll_once()
        warnings = [record for record in logs.records
                    if record.getMessage().startswith("WARNING - LEVIATHAN SEED:")]
        for record in warnings:
            self.assertEqual(record.levelno, logging.WARNING)
            self.assertNotIn("\n", record.getMessage())
        return [record.getMessage() for record in warnings]

    async def test_all_worlds_warn_once_per_entry(self) -> None:
        await self.scout(*[(index, "Energy Tank", 1) for index in (97, 98, 99)])
        for world, label, missing in [
            (BRYYO, "Bryyo Seed", "Hyper Ball"),
            (ELYSIA, "SkyTown Elysia Seed", "Hyper Missile and at least 4 missiles"),
            (PIRATE_HOMEWORLD, "Pirate Homeworld Seed", "Hyper Grapple and Grapple Voltage"),
        ]:
            with self.subTest(world=label):
                self.memory.set_world(world)
                messages = await self.warnings(polls=4)
                self.assertEqual(len(messages), 1)
                self.assertIn(f"{label} exit requires {missing}", messages[0])
        self.memory.set_menu()
        self.assertEqual(await self.warnings(), [])
        self.memory.set_ingame(PIRATE_HOMEWORLD)
        self.assertEqual(await self.warnings(), [])
        self.memory.set_world(BRYYO)
        self.assertEqual(len(await self.warnings()), 1)
        self.assertEqual([msg for msg in self.ctx.sent if msg["cmd"] == "LocationScouts"],
                         [{"cmd": "LocationScouts", "locations": [BASE_ID + i for i in (97, 98, 99)],
                           "create_as_hint": 0}])

    async def test_inventory_satisfies_each_exit(self) -> None:
        await self.scout(*[(index, "Energy Tank", 1) for index in (97, 98, 99)])
        for world, slots in [
            (BRYYO, [(inv.HYPER_BALL, 1, 1)]),
            (ELYSIA, [(inv.HYPER_MISSILE, 1, 1), (inv.MISSILE, 4, 10)]),
            (PIRATE_HOMEWORLD, [(inv.HYPER_GRAPPLE, 1, 1), (inv.GRAPPLE_VOLTAGE, 1, 1)]),
        ]:
            with self.subTest(world=world):
                for slot, amount, capacity in slots:
                    self.memory.set_slot(slot, amount, capacity)
                self.memory.set_world(world)
                self.assertEqual(await self.warnings(polls=3), [])

    async def test_core_pickups_supply_the_missing_upgrade(self) -> None:
        await self.scout((98, "Hyper Ball", 1), (97, "Hyper Missile", 1), (99, "Hyper Grapple", 3))
        self.memory.set_slot(inv.MISSILE, 4, 10)
        self.memory.set_slot(inv.GRAPPLE_VOLTAGE, 1, 1)
        for world in (BRYYO, ELYSIA, PIRATE_HOMEWORLD):
            with self.subTest(world=world):
                self.memory.set_world(world)
                self.assertEqual(await self.warnings(polls=3), [])

    async def test_core_pickups_leave_other_exit_requirements(self) -> None:
        await self.scout((97, "Hyper Missile", 1), (99, "Hyper Grapple", 1))
        self.memory.set_slot(inv.MISSILE, 3, 10)
        self.memory.set_world(ELYSIA)
        self.assertIn("exit requires at least 4 missiles (have 3)", (await self.warnings())[0])
        self.memory.set_world(PIRATE_HOMEWORLD)
        self.assertIn("exit requires Grapple Voltage", (await self.warnings())[0])

    async def test_waits_for_scout_and_inventory_and_warns_for_foreign_pickup(self) -> None:
        self.memory.set_world(BRYYO)
        self.assertEqual(await self.warnings(), [])
        self.memory.set_ingame(BRYYO, power_beam=0)
        await self.scout((98, "Hyper Ball", 2))
        self.assertEqual(await self.warnings(), [])
        self.memory.set_ingame(BRYYO)
        self.assertIn("exit requires Hyper Ball", (await self.warnings(polls=3))[0])

    async def test_command_disables_and_enables_warnings(self) -> None:
        await self.scout((98, "Energy Tank", 1))
        command = self.ctx.command_processor(self.ctx)
        command("/seedwarn off")
        self.memory.set_world(BRYYO)
        self.assertEqual(await self.warnings(polls=3), [])
        command("/seedwarn on")
        self.assertEqual(len(await self.warnings(polls=3)), 1)

    async def test_offline_cache_is_cleared_for_a_different_seed(self) -> None:
        await self.scout((98, "Energy Tank", 1))
        self.ctx.reset_server_state()
        self.ctx.fake_server = False
        self.memory.set_world(BRYYO)
        self.assertEqual(len(await self.warnings()), 1)

        self.ctx.fake_server = True
        await self.connect("OtherSeed")
        self.assertEqual(await self.warnings(), [])  # ISO still belongs to the old seed
        self.memory.set_seed_id(make_seed_id("OtherSeed", 1))
        self.assertEqual(await self.warnings(), [])  # still waiting for the new seed's scout
        await self.scout((98, "Energy Tank", 1))
        self.assertEqual(len(await self.warnings(polls=3)), 1)
