"""Client part 2 (T07, T18 part 2): effect table, target/current comparison, item giving and seed check with fake memory."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import random
import re
import tempfile
import unittest
from pathlib import Path

from CommonClient import process_server_cmd

from ..client import inventory as inv
from ..client.game import slot_address
from ..client.inventory import (ITEM_EFFECTS, RESOURCE_SLOTS, SLOT_LIMITS, compute_targets, effective_items,
                                plan_writes, used_cells)
from ..client.seed_check import SeedStatus
from ..items import RECORDS, item_name_to_id, pool_names, starting_names
from ..patcher.seed_id import make_seed_id
from .fake_memory import PLAYER_STATE, START_INVENTORY, FakeMemory
from .test_client import NORION, TEST_SEED, FakeClock, location_checks, make_context

REPO = Path(__file__).resolve().parents[3]  # follows the junction Archipelago/worlds/metroidprime3 -> repo
HEADER_JSON = REPO / "randovania" / "games" / "prime3" / "logic_database" / "header.json"
SLOT_LIMITS_MD = REPO / "docs" / "AP_SLOT_LIMITS.md"

NORION_BLOCK = 0x80A13AA0


def start_inventory() -> dict[int, tuple[int, int]]:
    inventory = {slot: (0, 0) for slot in range(inv.SLOT_COUNT)}
    inventory.update(START_INVENTORY)
    return inventory


def settle(items: list[str], inventory: dict[int, tuple[int, int]]) -> dict[int, tuple[int, int]]:
    """Applies the write plan until nothing is left to do (must be stable after one pass)."""
    inventory = dict(inventory)
    for _ in range(2):
        writes = plan_writes(compute_targets(items, used_cells(inventory)), inventory)
        if not writes:
            return inventory
        for write in writes:
            inventory[write.slot] = write.new
    raise AssertionError(f"comparison not stable: {writes}")


def assert_valid(case: unittest.TestCase, inventory: dict[int, tuple[int, int]], label: str = "") -> None:
    """Every written slot <= limit and survives saving (< 2^bits); suit valid (T19)."""
    for slot, (amount, capacity) in inventory.items():
        if slot in SLOT_LIMITS and slot not in inv.READ_ONLY_SLOTS:
            limit = SLOT_LIMITS[slot].limit
            case.assertLessEqual(amount, limit, f"{label} slot {slot} amount")
            case.assertLessEqual(capacity, limit, f"{label} slot {slot} capacity")
    amount, capacity = inventory[inv.SUIT]
    case.assertIn(amount, (0, inv.SUIT_AMOUNT), f"{label} suit amount")
    case.assertEqual(capacity, inv.SUIT_CAPACITY, f"{label} suit capacity")


FULL_POOL_EXPECTED = {
    inv.MISSILE: (245, 245), inv.LOCKED_MISSILES: (0, 0), inv.ENERGY_TANK: (14, 14), inv.SHIP_MISSILE: (11, 11),
    inv.SUIT: (5, 6), inv.FUSES: (9, 9), **{inv.FUSE_1 + i: (1, 1) for i in range(9)},
    **{slot: (1, 1) for slot in (inv.PLASMA_BEAM, inv.NOVA_BEAM, inv.ICE_MISSILE, inv.SEEKER_MISSILE,
                                 inv.GRAPPLE_LASSO, inv.GRAPPLE_SWING, inv.GRAPPLE_VOLTAGE, inv.COMMAND_VISOR,
                                 inv.XRAY_VISOR, inv.SCREW_ATTACK, inv.BOOST_BALL, inv.SPIDER_BALL, inv.HYPER_TANK,
                                 inv.HYPER_BEAM, inv.HYPER_MISSILE, inv.HYPER_BALL, inv.HYPER_GRAPPLE,
                                 inv.SHIP_GRAPPLE)},
}


class TestEffectTable(unittest.TestCase):
    """Effect table against data/items.py (99 pool items + starting items), header.json and AP_SLOT_LIMITS.md."""

    def test_every_item_has_an_effect(self) -> None:
        self.assertEqual(set(ITEM_EFFECTS), set(RECORDS))
        self.assertEqual(len(pool_names()), 99)
        for name in pool_names() + starting_names():
            self.assertIn(name, ITEM_EFFECTS)

    def test_stages_match_data(self) -> None:
        for name, record in RECORDS.items():
            effect = ITEM_EFFECTS[name]
            self.assertEqual(len(effect.stages), len(record["stages"]), name)
            for stage, data_stage in zip(effect.stages, record["stages"]):
                by_slot = {grant.slot: grant for grant in stage}
                self.assertEqual(set(by_slot), {RESOURCE_SLOTS[r] for r, _ in data_stage}, name)
                for resource, qty in data_stage:
                    grant = by_slot[RESOURCE_SLOTS[resource]]
                    if name == "Hazard Shield":  # logic Suit Type 1, pickup +5/+5 (Item.cs), rule suit
                        self.assertEqual((grant.capacity, grant.amount), (5, 5))
                    elif grant.slot == inv.FUSES:  # energy cells total: capacity fixed 9
                        self.assertEqual((grant.capacity, grant.amount), (0, qty), name)
                    else:
                        self.assertEqual((grant.capacity, grant.amount), (qty, qty), name)

    def test_locks_match_data(self) -> None:
        for name, record in RECORDS.items():
            effect = ITEM_EFFECTS[name]
            if record["is_expansion"]:
                self.assertEqual(effect.locked_by, record["lock"]["opened_by"], name)
            else:
                self.assertIsNone(effect.locked_by, name)
        self.assertEqual(ITEM_EFFECTS["Missile Expansion"].locked_slot, inv.LOCKED_MISSILES)
        self.assertIsNone(ITEM_EFFECTS["Ship Missile Expansion"].locked_slot)  # slot 69 is not saved

    def test_hyper_items_unlock_menu(self) -> None:
        for name, record in RECORDS.items():
            has_menu = inv.HYPER_BEAM in {g.slot for g in ITEM_EFFECTS[name].also}
            self.assertEqual(has_menu, record["category"] == "hypermode", name)

    def test_only_writable_slots(self) -> None:
        for name, effect in ITEM_EFFECTS.items():
            for grant in [g for stage in effect.stages for g in stage] + list(effect.also):
                self.assertIn(grant.slot, SLOT_LIMITS, name)
                self.assertNotIn(grant.slot, inv.READ_ONLY_SLOTS, name)

    @unittest.skipUnless(HEADER_JSON.is_file(), "randovania/.../header.json missing (no repo checkout)")
    def test_slots_match_header_json(self) -> None:
        with open(HEADER_JSON, encoding="utf-8") as f:
            items = json.load(f)["resource_database"]["items"]
        by_long_name = {info["long_name"]: info for info in items.values()}
        for resource, slot in RESOURCE_SLOTS.items():
            self.assertEqual(by_long_name[resource]["extra"]["item_id"], slot, resource)
        by_slot = {info["extra"]["item_id"]: info for info in items.values()}
        for slot, limit in SLOT_LIMITS.items():
            if slot in by_slot:
                self.assertEqual(by_slot[slot]["max_capacity"], limit.tab_max, slot)

    @unittest.skipUnless(SLOT_LIMITS_MD.is_file(), "docs/AP_SLOT_LIMITS.md missing (no repo checkout)")
    def test_limits_match_slot_limits_doc(self) -> None:
        text = SLOT_LIMITS_MD.read_text(encoding="utf-8")
        block = re.search(r"```csv\n(.*?)```", text, re.S).group(1)
        rows = list(csv.DictReader(io.StringIO(block), delimiter=";"))
        self.assertEqual({int(r["slot"]) for r in rows}, set(SLOT_LIMITS))
        for row in rows:
            limit = SLOT_LIMITS[int(row["slot"])]
            self.assertEqual(limit.name, row["name"])
            self.assertEqual(limit.tab_max, int(row["tab_max"]), row["name"])
            self.assertEqual(limit.bits, int(row["bits_capacity"]), row["name"])
            self.assertEqual((1 << limit.bits) - 1 if limit.bits else 0, int(row["max_valid"]), row["name"])


class TestTargets(unittest.TestCase):
    """Target computation and write plan without memory."""

    def test_each_pool_item_alone(self) -> None:
        start = settle(starting_names(), start_inventory())
        self.assertEqual(start, start_inventory())  # the ISO's starting inventory already is the target
        special = {
            "Missile Launcher": {inv.MISSILE: (5, 5)},
            "Missile Expansion": {inv.LOCKED_MISSILES: (5, 5)},  # locked, slot 4 stays 0/0
            "Ship Missile": {inv.SHIP_MISSILE: (3, 3)},
            "Ship Missile Expansion": {},  # locked, booked nowhere
            "Hazard Shield": {inv.SUIT: (5, 6)},
            "Energy Tank": {inv.ENERGY_TANK: (1, 1)},
            "Progressive Beam": {inv.PLASMA_BEAM: (1, 1)},
            "Progressive Missile": {inv.ICE_MISSILE: (1, 1)},
            **{f"Energy Cell {i}": {inv.FUSES: (1, 9), inv.FUSE_1 + i - 1: (1, 1)} for i in range(1, 10)},
            **{n: {slot: (1, 1), inv.HYPER_BEAM: (1, 1)} for n, slot in (
                ("Hypermode", inv.HYPER_TANK), ("Hyper Missile", inv.HYPER_MISSILE), ("Hyper Ball", inv.HYPER_BALL),
                ("Hyper Grapple", inv.HYPER_GRAPPLE))},
        }
        for name in sorted(set(pool_names())):
            result = settle(effective_items(starting_names(), [(name, 1)]), start_inventory())
            assert_valid(self, result, name)
            changed = {slot: value for slot, value in result.items() if start[slot] != value}
            if name in special:
                expected = special[name]
            else:
                (stage,) = ITEM_EFFECTS[name].stages
                expected = {stage[0].slot: (1, 1)}
            self.assertEqual(changed, expected, name)

    def test_full_pool(self) -> None:
        result = settle(effective_items(starting_names(), [(n, 1) for n in pool_names()]), start_inventory())
        assert_valid(self, result)
        for slot, value in FULL_POOL_EXPECTED.items():
            self.assertEqual(result[slot], value, inv.slot_label(slot))
        for slot, value in result.items():  # everything survives saving (mod 2^bits, T19)
            if slot in SLOT_LIMITS and SLOT_LIMITS[slot].bits:
                self.assertLess(max(value), 1 << SLOT_LIMITS[slot].bits, slot)

    def test_any_order_and_every_prefix(self) -> None:
        """No item missing, none twice: every order ends the same, every intermediate state is valid, no slot goes
        down (except slot 68 when the launcher arrives, that is how the game moves the load)."""
        rng = random.Random(7)
        for _ in range(15):
            order = pool_names()
            rng.shuffle(order)
            inventory = start_inventory()
            for k in range(1, len(order) + 1):
                before = inventory
                inventory = settle(effective_items(starting_names(), [(n, 1) for n in order[:k]]), inventory)
                assert_valid(self, inventory, f"prefix {k}")
                for slot in inventory:
                    if slot != inv.LOCKED_MISSILES:
                        self.assertGreaterEqual(inventory[slot][1], before[slot][1], (slot, order[k - 1]))
                locked = sum(1 for n in order[:k] if n == "Missile Expansion") * 5
                has_launcher = "Missile Launcher" in order[:k]
                self.assertEqual(inventory[inv.MISSILE][1], (5 + locked) if has_launcher else 0)
                self.assertEqual(inventory[inv.LOCKED_MISSILES][1], 0 if has_launcher else locked)
            for slot, value in FULL_POOL_EXPECTED.items():
                self.assertEqual(inventory[slot], value, inv.slot_label(slot))

    def test_starting_items_not_counted_twice(self) -> None:
        """items_handling 0b111: the server sends the precollected starting items as starting inventory (location -2)."""
        received = [(n, inv.START_INVENTORY_LOCATION) for n in starting_names()] + [("Energy Tank", 5)]
        self.assertEqual(sorted(effective_items(starting_names(), received)), sorted(starting_names() + ["Energy Tank"]))
        extra = received + [("Energy Tank", inv.START_INVENTORY_LOCATION)]  # start_inventory option
        self.assertEqual(effective_items(starting_names(), extra).count("Energy Tank"), 2)

    def test_expansions_before_launcher(self) -> None:
        items = starting_names() + ["Missile Expansion"] * 3
        inventory = settle(items, start_inventory())
        self.assertEqual((inventory[inv.MISSILE], inventory[inv.LOCKED_MISSILES]), ((0, 0), (15, 15)))
        inventory = settle(items + ["Missile Launcher"], inventory)
        self.assertEqual((inventory[inv.MISSILE], inventory[inv.LOCKED_MISSILES]), ((20, 20), (0, 0)))
        ship = settle(starting_names() + ["Ship Missile Expansion"] * 2, start_inventory())
        self.assertEqual(ship[inv.SHIP_MISSILE], (0, 0))
        ship = settle(starting_names() + ["Ship Missile Expansion"] * 2 + ["Ship Missile"], ship)
        self.assertEqual(ship[inv.SHIP_MISSILE], (5, 5))

    def test_ammo_keeps_consumption(self) -> None:
        items = starting_names() + ["Missile Launcher"] + ["Missile Expansion"] * 3
        inventory = settle(items, start_inventory())
        inventory[inv.MISSILE] = (7, 20)  # 13 fired
        self.assertEqual(settle(items, inventory)[inv.MISSILE], (7, 20))
        inventory = settle(items + ["Missile Expansion"], inventory)
        self.assertEqual(inventory[inv.MISSILE], (12, 25))  # capacity +5, amount +5
        inventory[inv.MISSILE] = (10, 10)  # older save
        self.assertEqual(settle(items + ["Missile Expansion"], inventory)[inv.MISSILE], (25, 25))

    def test_suit_rule(self) -> None:
        items = starting_names() + ["Hazard Shield"]
        for current, expected in (((0, 6), (5, 6)), ((5, 11), (5, 6)), ((5, 3), (5, 6)), ((6, 6), (6, 6)),
                                  ((5, 7), (5, 7)), ((0, 0), (5, 6))):
            inventory = start_inventory()
            inventory[inv.SUIT] = current
            self.assertEqual(settle(items, inventory)[inv.SUIT], expected, current)
        self.assertNotIn(inv.SUIT, compute_targets(starting_names()))  # without Hazard Shield: never touch the suit

    def test_used_cell_not_given_again(self) -> None:
        items = starting_names() + ["Energy Cell 1", "Energy Cell 2"]
        inventory = settle(items, start_inventory())
        self.assertEqual(inventory[inv.FUSES], (2, 9))
        inventory[inv.FUSES] = (1, 9)  # cell 1 inserted (T15)
        inventory[inv.FUSE_1] = (0, 1)
        inventory[inv.FUSES_USED] = (1, 9)
        inventory[inv.FUSE_1_USED] = (1, 1)
        self.assertEqual(plan_writes(compute_targets(items, used_cells(inventory)), inventory), [])
        inventory = settle(items + ["Energy Cell 3"], inventory)
        self.assertEqual((inventory[inv.FUSES], inventory[inv.FUSE_1], inventory[inv.FUSE_1 + 2]),
                         ((2, 9), (0, 1), (1, 1)))

    def test_never_lowers_raise_slots(self) -> None:
        inventory = start_inventory()
        inventory[inv.ENERGY_TANK] = (3, 3)
        inventory[inv.FUSES] = (4, 9)
        inventory[inv.GRAPPLE_LASSO] = (1, 1)
        self.assertEqual(plan_writes(compute_targets(starting_names() + ["Energy Tank"]), inventory), [])


def network_item(name: str, location: int = -1, player: int = 0) -> list[int]:
    return [item_name_to_id[name], location, player, 0]


class TestItemContext(unittest.IsolatedAsyncioTestCase):
    """Whole client with fake memory and real CommonClient packets (``process_server_cmd``)."""

    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = os.path.join(self.tmp.name, "learning.jsonl")
        logging.getLogger("Client").setLevel(logging.CRITICAL)
        self.memory = FakeMemory()
        self.block = self.memory.place_block(NORION_BLOCK, NORION)
        self.memory.set_ingame(NORION, item_percentage=1)
        self.ctx = make_context(self.memory, self.log_path)
        self.ctx.player_names = {0: "Archipelago", 1: "Samus", 2: "Finder"}
        self.clock = FakeClock()
        self.ctx.giver.clock = self.clock

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def poll(self, times: int = 1, dt: float = 0.5) -> None:
        for _ in range(times):
            self.clock.t += dt
            await self.ctx.poll_once()

    async def receive(self, items: list[list[int]], index: int | None = None) -> None:
        start = len(self.ctx.items_received) if index is None else index
        await process_server_cmd(self.ctx, {"cmd": "ReceivedItems", "index": start, "items": items})

    def written_slots(self) -> list[int]:
        base = slot_address(PLAYER_STATE, 0)
        return [(address - base) // 0xC for address, _ in self.memory.writes]

    async def test_items_given_and_announced(self) -> None:
        with self.assertLogs("Client", logging.INFO) as logs:
            await self.receive([network_item(n, -2) for n in starting_names()]
                               + [network_item("Missile Launcher", 0x4D503305, 2),
                                  network_item("Grapple Lasso", 0x4D503304, 1),
                                  network_item("Missile Expansion"), network_item("Missile Expansion")])
            await self.poll(3)
        messages = [r.getMessage() for r in logs.records]
        self.assertIn("Received: Missile Launcher from Finder", messages)
        self.assertIn("Received: Grapple Lasso from yourself", messages)
        self.assertEqual(messages.count("Received: Missile Expansion from Archipelago"), 2)
        self.assertEqual(messages.count("Received: Power Beam (starting inventory)"), 1)
        self.assertTrue(any(m.startswith("Written to the game: ") for m in messages))
        self.assertEqual(self.memory.slot(inv.MISSILE), (15, 15))
        self.assertEqual(self.memory.slot(inv.GRAPPLE_LASSO), (1, 1))
        self.assertEqual(self.memory.slot(inv.LOCKED_MISSILES), (0, 0))
        self.assertEqual(sorted(self.written_slots()), [inv.MISSILE, inv.GRAPPLE_LASSO])
        self.assertEqual(self.ctx.giver.failures_total, 0)

    async def test_settle_and_gating(self) -> None:
        await self.receive([network_item("Screw Attack")])
        self.memory.set_menu()
        await self.poll(3)
        self.assertEqual(self.memory.writes, [])
        self.memory.set_ingame(NORION, power_beam=0)  # intro: inventory still 0/0
        await self.poll(3)
        self.assertEqual(self.memory.writes, [])
        self.memory.set_ingame(NORION)
        await self.poll()  # first valid poll: settling
        self.assertEqual(self.memory.writes, [])
        await self.poll()
        self.assertEqual(self.memory.slot(inv.SCREW_ATTACK), (1, 1))

    async def test_reconnect_and_double_receive(self) -> None:
        package = [network_item("Energy Tank"), network_item("Missile Launcher"), network_item("Missile Expansion")]
        with self.assertLogs("Client", logging.INFO) as logs:
            await self.receive(package, index=0)
            await self.receive(package, index=0)  # the server sends everything again from the start
            await self.receive(package[:1], index=1)  # index does not match -> CommonClient requests a sync
            await self.poll(3)
            self.ctx.items_received = []  # connection gone (reset_server_state)
            self.ctx.fake_server = False
            await self.poll(3)
            self.ctx.fake_server = True  # reconnect: full list from index 0
            await self.receive(package, index=0)
            await self.poll(3)
        self.assertEqual(len(self.ctx.items_received), 3)
        self.assertIn({"cmd": "Sync"}, self.ctx.sent)
        messages = [r.getMessage() for r in logs.records]
        self.assertEqual(messages.count("Received: Missile Expansion from Archipelago"), 1)
        self.assertEqual(self.memory.slot(inv.ENERGY_TANK), (1, 1))
        self.assertEqual(self.memory.slot(inv.MISSILE), (10, 10))
        self.assertEqual(sorted(self.written_slots()), [inv.MISSILE, inv.ENERGY_TANK])  # once each

    async def test_death_and_older_save(self) -> None:
        old_save = self.memory.save()  # save before all items
        await self.receive([network_item("Missile Launcher"), network_item("Energy Tank"),
                            network_item("Grapple Lasso")] + [network_item("Missile Expansion")] * 2)
        await self.poll(3)
        self.memory.set_slot(inv.MISSILE, 4, 15)  # 11 fired
        new_save = self.memory.save()  # saved at the ship
        await self.receive([network_item("Missile Expansion"), network_item("Progressive Beam")])
        await self.poll(3)
        self.assertEqual(self.memory.slot(inv.MISSILE), (9, 20))
        expected = {inv.MISSILE: 20, inv.ENERGY_TANK: 1, inv.GRAPPLE_LASSO: 1, inv.PLASMA_BEAM: 1}
        # death + continue (loading phase with CPlayer 0) to the last save
        self.memory.set_menu()
        await self.poll(2)
        self.memory.load(new_save, NORION)
        await self.poll(3)
        for slot, capacity in expected.items():
            self.assertEqual(self.memory.slot(slot)[1], capacity, inv.slot_label(slot))
        self.assertEqual(self.memory.slot(inv.MISSILE), (9, 20))
        # older save without a loading phase (only CGameState is new)
        self.memory.load(old_save, NORION)
        await self.poll(3)
        for slot, capacity in expected.items():
            self.assertEqual(self.memory.slot(slot)[1], capacity, inv.slot_label(slot))
        self.assertEqual(self.memory.slot(inv.MISSILE), (20, 20))
        self.assertEqual(self.memory.slot(inv.LOCKED_MISSILES), (0, 0))
        self.assertEqual(self.ctx.giver.failures_total, 0)
        assert_valid(self, self.memory.inventory())

    async def test_used_energy_cell_not_given_again(self) -> None:
        await self.receive([network_item("Energy Cell 1")])
        await self.poll(3)
        self.assertEqual((self.memory.slot(inv.FUSES), self.memory.slot(inv.FUSE_1)), ((1, 9), (1, 1)))
        saved_before_use = self.memory.save()
        self.memory.use_cell(1)
        await self.poll(4)
        self.assertEqual((self.memory.slot(inv.FUSES), self.memory.slot(inv.FUSE_1)), ((0, 9), (0, 1)))
        await self.receive([network_item("Energy Cell 2")])
        await self.poll(3)
        self.assertEqual((self.memory.slot(inv.FUSES), self.memory.slot(inv.FUSE_1), self.memory.slot(inv.FUSE_1 + 1)),
                         ((1, 9), (0, 1), (1, 1)))
        saved_after_use = self.memory.save()
        self.memory.set_menu()
        await self.poll(2)
        self.memory.load(saved_after_use, NORION)
        await self.poll(3)
        self.assertEqual((self.memory.slot(inv.FUSES), self.memory.slot(inv.FUSE_1)), ((1, 9), (0, 1)))
        # death before inserting: in the save cell 1 is not inserted yet -> it is back, cell 2 is given again
        self.memory.load(saved_before_use, NORION)
        await self.poll(3)
        self.assertEqual((self.memory.slot(inv.FUSES), self.memory.slot(inv.FUSE_1), self.memory.slot(inv.FUSE_1 + 1)),
                         ((2, 9), (1, 1), (1, 1)))

    async def test_whole_pool_in_game(self) -> None:
        await self.receive([network_item(n, -2) for n in starting_names()] + [network_item(n) for n in pool_names()])
        await self.poll(4)
        inventory = self.memory.inventory()
        assert_valid(self, inventory)
        for slot, value in FULL_POOL_EXPECTED.items():
            self.assertEqual(inventory[slot], value, inv.slot_label(slot))
        writes = len(self.memory.writes)
        await self.poll(5)
        self.assertEqual(len(self.memory.writes), writes)  # stable, nothing twice
        self.assertTrue(all(slot not in inv.READ_ONLY_SLOTS for slot in self.written_slots()))

    async def test_location_still_sent_while_giving(self) -> None:
        await self.receive([network_item("Grapple Lasso")])
        await self.poll(2)
        self.memory.set_flag(self.block, 8)  # location 4
        self.memory.set_item_percentage(2)
        await self.poll(3)
        self.assertEqual(location_checks(self.ctx), [0x4D503304])
        self.assertEqual(self.memory.slot(inv.GRAPPLE_LASSO), (1, 1))

    async def test_wrong_or_vanilla_seed_writes_and_sends_nothing(self) -> None:
        await self.receive([network_item("Grapple Lasso"), network_item("Missile Launcher")])
        self.memory.set_flag(self.block, 8)
        for seed_id, status in ((make_seed_id("AnotherSeed", 1), SeedStatus.MISMATCH),
                                (make_seed_id(TEST_SEED, 2), SeedStatus.MISMATCH),  # other slot
                                (None, SeedStatus.VANILLA)):
            self.memory.set_seed_id(seed_id)
            with self.assertLogs("Client", logging.ERROR) as logs:
                await self.poll(5)
            self.assertIs(self.ctx.seed_check.result.status, status)
            self.assertTrue(any("no location checks" in r.getMessage() for r in logs.records))
            self.assertEqual(self.memory.writes, [])
            self.assertEqual(location_checks(self.ctx), [])
            self.assertEqual(self.ctx.locations_checked, set())
        self.memory.set_seed_id(make_seed_id(TEST_SEED, 1))  # correct ISO loaded
        await self.poll(4)
        self.assertIs(self.ctx.seed_check.result.status, SeedStatus.OK)
        self.assertEqual(location_checks(self.ctx), [0x4D503304])
        self.assertEqual(self.memory.slot(inv.GRAPPLE_LASSO), (1, 1))

    async def test_seed_switch_forgets_confirmed_checks(self) -> None:
        self.memory.set_flag(self.block, 8)
        await self.poll(3)
        self.assertEqual(location_checks(self.ctx), [0x4D503304])
        self.memory.set_seed_id(make_seed_id("OtherSeed", 1))
        await self.poll(2)
        self.assertEqual(self.ctx.detector.confirmed, set())
        # another slot connected (CommonClient clears locations_checked on a switch), matching ISO
        self.ctx.server_seed_name, self.ctx.connected_identity = "OtherSeed", ("OtherSeed", 0, 1)
        self.ctx.locations_checked = set()
        self.ctx.sent = []
        await self.poll(3)
        self.assertEqual(location_checks(self.ctx), [0x4D503304])

    async def test_server_offline_gives_nothing(self) -> None:
        await self.receive([network_item("Grapple Lasso")])
        self.ctx.fake_server = False
        await self.poll(4)
        self.assertEqual(self.memory.writes, [])

    async def test_readback_throttle_no_write_loop(self) -> None:
        self.memory.revert[inv.GRAPPLE_LASSO] = (0, 0)  # the game resets the slot at once
        await self.receive([network_item("Grapple Lasso")])
        with self.assertLogs("Client", logging.WARNING) as logs:
            await self.poll(2)
            self.assertEqual(self.written_slots(), [inv.GRAPPLE_LASSO])
            await self.poll(6)  # 3 s: failure detected, blocked for 5 s
            self.assertEqual(self.written_slots(), [inv.GRAPPLE_LASSO])
            await self.poll(6)  # after 6 s: second attempt, then blocked for 10 s
            self.assertEqual(self.written_slots(), [inv.GRAPPLE_LASSO] * 2)
            await self.poll(400)  # 200 s: at most max_failures attempts, then given up
        self.assertEqual(self.written_slots(), [inv.GRAPPLE_LASSO] * self.ctx.giver.max_failures)
        self.assertIn(inv.GRAPPLE_LASSO, self.ctx.giver.given_up)
        self.assertTrue(any(r.levelno == logging.ERROR and "will not be written again" in r.getMessage()
                            for r in logs.records))
        # after the next load it is tried again
        del self.memory.revert[inv.GRAPPLE_LASSO]
        self.memory.set_menu()
        await self.poll(2)
        self.memory.set_ingame(NORION)
        await self.poll(2)
        self.assertEqual(self.memory.slot(inv.GRAPPLE_LASSO), (1, 1))

    async def test_consumption_after_write_is_no_failure(self) -> None:
        await self.receive([network_item("Missile Launcher")] + [network_item("Missile Expansion")] * 3)
        await self.poll(2)
        self.assertEqual(self.memory.slot(inv.MISSILE), (20, 20))
        self.memory.set_slot(inv.MISSILE, 14, 20)  # fired right away
        await self.poll(4)
        self.assertEqual(self.memory.slot(inv.MISSILE), (14, 20))
        self.assertEqual(self.ctx.giver.failures_total, 0)

    async def test_inventory_command_lines(self) -> None:
        await self.receive([network_item("Hazard Shield")])
        await self.poll(3)
        lines = self.ctx.inventory_lines()
        self.assertTrue(any("Suit (slot 17, suit): target 5/6, current 5/6 - ok" in line for line in lines), lines)
