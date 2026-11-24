"""Locations of the Metroid Prime 3 APWorld (data/locations.py). Pickup index 0 is not an AP location (E13, E17)."""

from __future__ import annotations

from BaseClasses import Location

from .data import locations as location_data
from .items import BASE_ID, GAME_NAME

LOCATIONS: list[dict] = list(location_data.LOCATIONS)

location_name_to_id: dict[str, int] = {loc["name"]: BASE_ID + loc["id"] for loc in LOCATIONS}

# one group per game region (planet/ship), e.g. "Norion"
location_name_groups: dict[str, set[str]] = {}
for _loc in LOCATIONS:
    location_name_groups.setdefault(_loc["region"], set()).add(_loc["name"])


class MP3Location(Location):
    game = GAME_NAME


def pickup_index(location_id: int) -> int:
    return location_id - BASE_ID


def node_of(loc: dict) -> tuple[str, str, str]:
    return loc["region"], loc["area"], loc["node"]
