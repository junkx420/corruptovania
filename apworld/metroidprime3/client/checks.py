"""Flag bytes -> AP locations (SPEC E12, apworld/metroidprime3/location_flags.py)."""

from __future__ import annotations

from dataclasses import dataclass

from ..data import locations as location_data
from ..items import BASE_ID
from ..location_flags import LOCATION_DETAILS, LOCATION_FLAGS, WORLD_NAMES

# worlds without locations (not in location_flags.py), only for log messages; Phaaze measured in T08/T17
EXTRA_WORLD_NAMES: dict[int, str] = {0x4B07619AB6125B33: "Phaaze"}


@dataclass(frozen=True)
class ByteInfo:
    """What a byte in a world's block means according to the table."""
    role: str  # "location" | "extra" (other_bytes of a location) | "unknown"
    pickup_index: int | None = None
    location_name: str | None = None
    room: str | None = None
    status: str | None = None  # location_flags.py status: "certain" | "probable" | "uncertain"


class LocationTable:
    def __init__(self, base_id: int = BASE_ID) -> None:
        self.base_id = base_id
        self.names = {loc["id"]: loc["name"] for loc in location_data.LOCATIONS}
        self.rooms = {loc["id"]: loc["area"] for loc in location_data.LOCATIONS}
        self.by_world: dict[int, list[tuple[int, int]]] = {}
        self.byte_info: dict[tuple[int, int], ByteInfo] = {}
        for index, (world, byte, _object_id) in sorted(LOCATION_FLAGS.items()):
            self.by_world.setdefault(world, []).append((index, byte))
            status = str(LOCATION_DETAILS.get(index, {}).get("status", ""))
            self.byte_info[(world, byte)] = ByteInfo("location", index, self.names.get(index), self.rooms.get(index),
                                                     status)
        for index, details in LOCATION_DETAILS.items():
            world = LOCATION_FLAGS[index][0]
            for byte in details.get("other_bytes", ()):  # type: ignore[union-attr]
                self.byte_info.setdefault((world, int(byte)),
                                          ByteInfo("extra", index, self.names.get(index), self.rooms.get(index)))

    def has_world(self, world_id: int | None) -> bool:
        return world_id in self.by_world

    @staticmethod
    def world_name(world_id: int | None) -> str:
        if world_id is None:
            return "?"
        return WORLD_NAMES.get(world_id) or EXTRA_WORLD_NAMES.get(world_id, f"0x{world_id:016X}")

    def collected(self, world_id: int, flags: bytes) -> set[int]:
        """Pickup indices of the world whose byte is set."""
        return {index for index, byte in self.by_world.get(world_id, ()) if flags[byte]}

    def location_id(self, pickup_index: int) -> int:
        return self.base_id + pickup_index

    def describe(self, world_id: int, byte: int) -> ByteInfo:
        return self.byte_info.get((world_id, byte), ByteInfo("unknown"))


class CheckDetector:
    """Debounces detection: a location only counts as collected once its byte was set in ``confirm_polls``
    consecutive polls (protects against briefly valid foreign data). Confirmed locations are never reported twice."""

    def __init__(self, confirm_polls: int = 2) -> None:
        self.confirm_polls = max(1, confirm_polls)
        self.confirmed: set[int] = set()
        self._streak: dict[int, int] = {}

    def reset_pending(self) -> None:
        """After menu/loading/world change: drop half-finished detections, confirmed ones stay."""
        self._streak = {}

    def reset(self) -> None:
        """Seed ID invalid or another slot (T18): forget confirmed locations too, they belonged to another game."""
        self._streak = {}
        self.confirmed = set()

    def update(self, collected: set[int]) -> set[int]:
        """``collected`` = set locations of the current world. Returns the newly confirmed locations."""
        self._streak = {i: self._streak.get(i, 0) + 1 for i in collected if i not in self.confirmed}
        new = {i for i, n in self._streak.items() if n >= self.confirm_polls}
        for i in new:
            del self._streak[i]
        self.confirmed |= new
        return new
