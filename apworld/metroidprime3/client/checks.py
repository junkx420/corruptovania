"""Flag-Bytes -> AP-Locations (SPEC E12, apworld/metroidprime3/location_flags.py)."""

from __future__ import annotations

from dataclasses import dataclass

from ..data import locations as location_data
from ..items import BASE_ID
from ..location_flags import LOCATION_DETAILS, LOCATION_FLAGS, WORLD_NAMES


@dataclass(frozen=True)
class ByteInfo:
    """Was ein Byte im Block einer Welt laut Tabelle bedeutet."""
    role: str  # "location" | "extra" (other_bytes eines Orts) | "unknown"
    pickup_index: int | None = None
    location_name: str | None = None
    room: str | None = None
    status: str | None = None  # sicher | wahrscheinlich


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
        return WORLD_NAMES.get(world_id, f"0x{world_id:016X}")

    def collected(self, world_id: int, flags: bytes) -> set[int]:
        """Pickup-Indizes der Welt, deren Byte gesetzt ist."""
        return {index for index, byte in self.by_world.get(world_id, ()) if flags[byte]}

    def location_id(self, pickup_index: int) -> int:
        return self.base_id + pickup_index

    def describe(self, world_id: int, byte: int) -> ByteInfo:
        return self.byte_info.get((world_id, byte), ByteInfo("unknown"))


class CheckDetector:
    """Entprellt die Erkennung: Ein Ort gilt erst als eingesammelt, wenn sein Byte in ``confirm_polls``
    aufeinanderfolgenden Abfragen gesetzt war (schützt vor kurzzeitig gültigen Fremddaten). Bereits bestätigte Orte
    werden nie zweimal gemeldet."""

    def __init__(self, confirm_polls: int = 2) -> None:
        self.confirm_polls = max(1, confirm_polls)
        self.confirmed: set[int] = set()
        self._streak: dict[int, int] = {}

    def reset_pending(self) -> None:
        """Nach Menü/Laden/Weltwechsel: halbe Erkennungen verwerfen, bestätigte bleiben."""
        self._streak = {}

    def update(self, collected: set[int]) -> set[int]:
        """``collected`` = gesetzte Orte der aktuellen Welt. Liefert die neu bestätigten Orte."""
        self._streak = {i: self._streak.get(i, 0) + 1 for i in collected if i not in self.confirmed}
        new = {i for i, n in self._streak.items() if n >= self.confirm_polls}
        for i in new:
            del self._streak[i]
        self.confirmed |= new
        return new
