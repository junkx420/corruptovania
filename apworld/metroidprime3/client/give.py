"""Item giving (T07, SPEC E9/E11): target/current comparison per poll, read-back, throttling.

Per poll (``ItemGiver.step``):

1. Only ingame (CPlayer vtable) **and** with a filled inventory (``PowerBeam.capacity > 0``). Menu, loading, intro and
   every change of the game state (new ``PS`` or ``[0x80680234]``, e.g. after continue/loading) reset everything; after
   that the giver only writes after ``settle_polls`` valid polls in a row (inventory just filled from the save).
2. Read the inventory (70 slots) in one go, compute the targets (``inventory.compute_targets``), write plan
   (``inventory.plan_writes``).
3. **Read-back:** what was written in the previous poll is checked now (= shortly after, one poll interval). If the
   game changed the value **and** the slot is below target again, that counts as a failure: warning in the log, the slot
   is blocked for 5, 10, 20, 40 s, and after ``max_failures`` failures it is not written at all until the next
   load/menu (error in the log). So there is never a write loop.
4. Write the remaining slots of the plan (8 bytes each, amount + capacity).

Death/continue and loading an older save reset the inventory to the save (T15); since the target is computed absolutely
from all received items, the next comparison gives exactly what is missing again, nothing twice. The client cannot read
a death state of its own (address unknown): values written during the death animation are overwritten by the game with
the save on continue, after that step 1 applies.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Sequence

from .game import GameState
from .inventory import (SlotTarget, SlotWrite, compute_targets, plan_writes, read_inventory, slot_label, used_cells,
                        write_slot)

DEFAULT_BACKOFF = (5.0, 10.0, 20.0, 40.0)
DEFAULT_MAX_FAILURES = 5


class ItemGiver:
    def __init__(self, memory, log: logging.Logger, clock: Callable[[], float] = time.monotonic,
                 settle_polls: int = 2, backoff: Sequence[float] = DEFAULT_BACKOFF,
                 max_failures: int = DEFAULT_MAX_FAILURES) -> None:
        self.memory = memory
        self.log = log
        self.clock = clock
        self.settle_polls = max(1, settle_polls)
        self.backoff = tuple(backoff)
        self.max_failures = max_failures
        self.writes_total = 0
        self.failures_total = 0
        self.last_targets: dict[int, SlotTarget] = {}
        self.last_inventory: dict[int, tuple[int, int]] = {}
        self._session: tuple[int | None, int | None] | None = None
        self._valid_polls = 0
        self._pending: dict[int, SlotWrite] = {}
        self._failures: dict[int, int] = {}
        self._blocked_until: dict[int, float] = {}
        self.given_up: set[int] = set()

    def reset(self) -> None:
        """Menu, loading, death/continue, lost connection, seed change: settle again, drop pending checks and throttling
        (a new game state is not a failure)."""
        self._session = None
        self._valid_polls = 0
        self._pending.clear()
        self._failures.clear()
        self._blocked_until.clear()
        self.given_up.clear()

    def blocked(self) -> dict[int, float]:
        """Blocked slots -> remaining seconds (for /inventory)."""
        now = self.clock()
        return {slot: until - now for slot, until in self._blocked_until.items() if until > now}

    def step(self, state: GameState, items: Sequence[str]) -> list[SlotWrite]:
        """One comparison. ``items`` = all counting item names (``inventory.effective_items``). Returns the slots
        written."""
        if not state.ingame or not state.inventory_valid or state.player_state is None:
            if self._session is not None:
                self.reset()
            return []
        session = (state.player_state, state.game_state_pointer)
        if session != self._session:
            if self._session is not None:
                self.log.debug("New game state (loading/continue), item comparison settles again.")
            self.reset()
            self._session = session
        self._valid_polls += 1
        if self._valid_polls < self.settle_polls:
            return []

        inventory = read_inventory(self.memory, state.player_state)
        targets = compute_targets(items, used_cells(inventory))
        plan = {write.slot: write for write in plan_writes(targets, inventory)}
        self.last_targets, self.last_inventory = targets, inventory
        now = self.clock()
        self._verify(plan, inventory, now)

        done: list[SlotWrite] = []
        for slot in sorted(plan):
            if slot in self.given_up or self._blocked_until.get(slot, 0.0) > now:
                continue
            write = plan[slot]
            write_slot(self.memory, state.player_state, slot, write.new)
            self._pending[slot] = write
            done.append(write)
        if done:
            self.writes_total += len(done)
            self.log.info("Written to the game: " + ", ".join(w.describe() for w in done))
        return done

    def _verify(self, plan: dict[int, SlotWrite], inventory: dict[int, tuple[int, int]], now: float) -> None:
        """Read-back of the previous writes."""
        for slot, written in self._pending.items():
            current = inventory.get(slot, (0, 0))
            if current != written.new and slot in plan:
                self._fail(slot, written, current, now)
            else:
                self._failures.pop(slot, None)
        self._pending.clear()

    def _fail(self, slot: int, written: SlotWrite, current: tuple[int, int], now: float) -> None:
        count = self._failures.get(slot, 0) + 1
        self._failures[slot] = count
        self.failures_total += 1
        what = (f"{slot_label(slot)} (slot {slot}): wrote {written.new[0]}/{written.new[1]}, "
                f"read back {current[0]}/{current[1]}")
        if count >= self.max_failures:
            self.given_up.add(slot)
            self._blocked_until.pop(slot, None)
            self.log.error(f"{what}. The game keeps resetting the value ({count}x). The slot will not be written "
                           f"again until the next load/menu.")
            return
        delay = self.backoff[min(count - 1, len(self.backoff) - 1)]
        self._blocked_until[slot] = now + delay
        self.log.warning(f"{what}. Changed by the game, next attempt in {delay:.0f} s.")
