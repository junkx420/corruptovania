"""Goal detection (event "Aurora Unit 313", ``slot_data["goal_event"]``), measured live in T08/T17.

Measurement (PAL RM3P01, PrimeHack, 2026-11-25, seed 61579369889909122189; ``docs/AP_PLAYTEST_T08.md``, T17):

- Phaaze (MLVL ``0x4B07619AB6125B33``) has no locations; its flag block (25 bytes set) did **not** change between the
  dump before the final battle and the dumps after the victory, in the end cutscene and in the credits.
- Slot 41 (HyperModePhaaze): ``0/0`` on arrival, ``1/1`` about a minute after landing (permanent Phaaze Hypermode) and
  through the whole final battle. When the end cutscene starts after the victory over Aurora Unit 313, the game sets
  it to ``0/1`` (same frame: suit amount 5 -> 0, Grapple Lasso/Swing/Voltage amount 1 -> 0). It stays ``0/1`` through
  the cutscene and the credits.
- During the end cutscene and the credits the world stays Phaaze and the CPlayer stays valid ("ingame" for the
  client), so the condition is seen by the normal ingame poll.

Condition: ingame, world Phaaze, inventory filled, slot 41 amount 0 **and** capacity 1, in ``confirm_polls``
consecutive polls. The client never writes slot 41 (``inventory.READ_ONLY_SLOTS``), so its own writes cannot fake it.
While the condition holds (end sequence) the client gives no items: the game strips suit and grapples on purpose there.

Not measured: slot 41 after loading a save made on Phaaze (none was made). If it could load as 0/1, the goal would be
reported early; reproduced twice live without that case (T08 runs 2 and 3).
"""

from __future__ import annotations

import struct

from .game import GameState, slot_address
from .memory import MemoryAccess

PHAAZE_WORLD_ID = 0x4B07619AB6125B33
SLOT_HYPER_MODE_PHAAZE = 41
ENDING_SLOT_VALUE = (0, 1)  # (amount, capacity) of slot 41 after the victory over Aurora Unit 313


def ending_sequence(memory: MemoryAccess, state: GameState) -> bool:
    """True while the end sequence after Aurora Unit 313 runs (end cutscene, credits)."""
    if not state.ingame or state.world_id != PHAAZE_WORLD_ID or state.player_state is None:
        return False
    if not state.inventory_valid:
        return False
    raw = memory.read(slot_address(state.player_state, SLOT_HYPER_MODE_PHAAZE), 8)
    return struct.unpack(">II", raw) == ENDING_SLOT_VALUE


class GoalDetector:
    available = True  # measured in T08/T17

    def __init__(self, goal_event: str = "Aurora Unit 313", confirm_polls: int = 2) -> None:
        self.goal_event = goal_event
        self.confirm_polls = confirm_polls
        self.streak = 0  # consecutive polls with the condition
        self.detections = 0  # how often the end sequence started (rising edges), for /dolphin and the log

    def observe(self, memory: MemoryAccess, state: GameState) -> bool:
        """Updates the detector with one poll. Returns whether the end sequence is seen in this poll."""
        seen = ending_sequence(memory, state)
        if seen:
            self.streak += 1
            if self.streak == self.confirm_polls:
                self.detections += 1
        else:
            self.streak = 0
        return seen

    @property
    def confirmed(self) -> bool:
        """The condition held in ``confirm_polls`` consecutive polls (up to now)."""
        return self.streak >= self.confirm_polls

    def reset(self) -> None:
        self.streak = 0

    def reached(self, memory: MemoryAccess, state: GameState) -> bool:
        """Interface from T07: one poll, True once the goal is confirmed."""
        self.observe(memory, state)
        return self.confirmed
