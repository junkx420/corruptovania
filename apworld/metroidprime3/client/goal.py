"""Goal detection (event "Aurora Unit 313", ``slot_data["goal_event"]``) - INTERFACE, OPEN until T17.

How the victory over Aurora Unit 313 shows up in memory has not been measured (STATUS T17: memory state after the final
boss). Phaaze has no locations, so it has no flag block in ``location_flags.py`` either; a story relay or an inventory
slot (e.g. 40/41 HyperModePermanent/-Phaaze, T15 open) would only be a guess. Without a measurement the client
therefore **never** reports the goal.

T17 replaces ``GoalDetector.reached`` with the measured condition and sets ``available``. The client calls it in every
ingame poll (only with a valid seed ID) and sends ``StatusUpdate`` with ``CLIENT_GOAL`` on the first ``True``.
"""

from __future__ import annotations

from .game import GameState
from .memory import MemoryAccess


class GoalDetector:
    available = False  # T17: set to True once ``reached`` is measured

    def __init__(self, goal_event: str = "Aurora Unit 313") -> None:
        self.goal_event = goal_event

    def reached(self, memory: MemoryAccess, state: GameState) -> bool:  # noqa: ARG002 - interface for T17
        return False
