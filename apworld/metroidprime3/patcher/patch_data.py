"""AP patch data (JSON, format in docs/AP_PATCH_TOOL.md) and its translation into MP3Randomizer input.

T05b writes this format in ``generate_output``; :func:`build_patch_data` is the helper for that.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any

from . import layout, seed_id

FORMAT_NAME = "metroidprime3-ap-patch"
FORMAT_VERSION = 1

# Starter Preset values as Randovania's patch data factory produces them (seed IVG2J7OR, docs/AP_DEV_SETUP.md 4):
# start G.F.S. Valhalla - Docking Bay 5 (world/area asset IDs), start items Power Beam, Charge Beam, Morph Ball Bombs,
# Scan Visor, Morph Ball, Space Jump Boots, HyperModeOriginal = 1 (no corrupted hypermode); Combat Visor is always
# present in the game and not part of the string. Suit cosmetic = default (0).
STANDARD_STARTING_ITEMS = "custom 0000000010010000000001100100100000000010000"
STANDARD_STARTING_LOCATION = "custom c133f919c108bdf9 d8cf355d3e9e3741"

_STARTING_ITEMS_RE = re.compile(r"^custom [0-9a-f]{43}$")
_STARTING_LOCATION_RE = re.compile(r"^custom [0-9a-f]{1,16} [0-9a-f]{1,16}$")
_SEED_ID_RE = re.compile(r"^[0-9a-f]{32}$")

_REQUIRED_KEYS = {"format", "version", "seed_name", "slot", "player_name", "pickups"}
_OPTIONAL_KEYS = {"seed_id", "starting_items", "starting_location"}


class PatchDataError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class PatchData:
    seed_name: str
    slot: int
    player_name: str
    seed_id: bytes
    pickups: dict[int, str]  # pickup index 1-99 -> displayed item name
    starting_items: str = STANDARD_STARTING_ITEMS
    starting_location: str = STANDARD_STARTING_LOCATION

    def layout_string(self) -> str:
        return layout.layout_string_for_pickups(self.pickups)

    def to_json(self) -> dict[str, Any]:
        return {
            "format": FORMAT_NAME,
            "version": FORMAT_VERSION,
            "seed_name": self.seed_name,
            "slot": self.slot,
            "player_name": self.player_name,
            "seed_id": self.seed_id.hex(),
            "pickups": {str(index): self.pickups[index] for index in sorted(self.pickups)},
            "starting_items": self.starting_items,
            "starting_location": self.starting_location,
        }

    def randomizer_patch_data(self) -> dict[str, Any]:
        """Same keys as Randovania's prime3 patcher JSON (``layout patcher-data``), AP settings fixed."""
        return {
            "seed": self.layout_string(),
            "starting_items": self.starting_items,
            "starting_location": self.starting_location,
            "random_door_colors": False,
            "random_welding_colors": False,
            "missile_required_mains": False,  # E15, --ap-mode forces it off anyway
            "ship_missile_required_mains": False,
            "phaaze_skip": False,
            "mp3_update": False,  # E7: PAL, the hdiffs only fit NTSC-U
            "disable_deflicker": False,
            "ap_mode": True,
        }


def build_patch_data(
    seed_name: str,
    slot: int,
    player_name: str,
    pickups: dict[int, str],
    starting_items: str = STANDARD_STARTING_ITEMS,
    starting_location: str = STANDARD_STARTING_LOCATION,
) -> PatchData:
    """Patch data for one slot. ``pickups``: own item -> its item name, item of another world -> ``layout.AP_ITEM``."""
    data = PatchData(
        seed_name=seed_name,
        slot=slot,
        player_name=player_name,
        seed_id=seed_id.make_seed_id(seed_name, slot),
        pickups=dict(pickups),
        starting_items=starting_items,
        starting_location=starting_location,
    )
    validate(data)
    return data


def validate(data: PatchData) -> None:
    if not isinstance(data.seed_name, str) or not data.seed_name:
        raise PatchDataError("seed_name must be a non-empty string")
    if isinstance(data.slot, bool) or not isinstance(data.slot, int) or data.slot < 1:
        raise PatchDataError("slot must be an integer >= 1")
    if not isinstance(data.player_name, str) or not data.player_name:
        raise PatchDataError("player_name must be a non-empty string")
    if data.seed_id != seed_id.make_seed_id(data.seed_name, data.slot):
        raise PatchDataError("seed_id does not match seed_name/slot (make_seed_id)")
    missing = [i for i in range(1, layout.PICKUP_COUNT) if i not in data.pickups]
    extra = sorted(set(data.pickups) - set(range(1, layout.PICKUP_COUNT)))
    if missing or extra:
        raise PatchDataError(f"pickups must contain exactly the indices 1-99 (missing {missing}, unexpected {extra})")
    for index, name in sorted(data.pickups.items()):
        if name not in layout.DISPLAYABLE_ITEMS:
            raise PatchDataError(f"pickup {index}: {name!r} cannot be shown by the patcher")
    if not _STARTING_ITEMS_RE.match(data.starting_items):
        raise PatchDataError(f"starting_items must look like 'custom <43 hex digits>': {data.starting_items!r}")
    if not _STARTING_LOCATION_RE.match(data.starting_location):
        raise PatchDataError(f"starting_location must look like 'custom <world> <area>': {data.starting_location!r}")


def from_json(raw: dict[str, Any]) -> PatchData:
    if not isinstance(raw, dict):
        raise PatchDataError("patch data must be a JSON object")
    keys = {key for key in raw if not key.startswith("_")}
    if missing := _REQUIRED_KEYS - keys:
        raise PatchDataError(f"missing keys: {sorted(missing)}")
    if unknown := keys - _REQUIRED_KEYS - _OPTIONAL_KEYS:
        raise PatchDataError(f"unknown keys: {sorted(unknown)} (comments must start with '_')")
    if raw["format"] != FORMAT_NAME:
        raise PatchDataError(f"format must be {FORMAT_NAME!r}, got {raw['format']!r}")
    if raw["version"] != FORMAT_VERSION:
        raise PatchDataError(f"unsupported version {raw['version']!r} (this tool reads {FORMAT_VERSION})")

    pickups_raw = raw["pickups"]
    if not isinstance(pickups_raw, dict):
        raise PatchDataError("pickups must be an object {\"<index>\": \"<item name>\"}")
    pickups: dict[int, str] = {}
    for key, value in pickups_raw.items():
        if not re.fullmatch(r"[1-9][0-9]?", key):
            raise PatchDataError(f"pickup key {key!r} is not an index 1-99")
        if not isinstance(value, str):
            raise PatchDataError(f"pickup {key}: item name must be a string")
        pickups[int(key)] = value

    slot = raw["slot"]
    seed_name = raw["seed_name"]
    if isinstance(slot, bool) or not isinstance(slot, int):
        raise PatchDataError("slot must be an integer")
    if not isinstance(seed_name, str):
        raise PatchDataError("seed_name must be a string")
    expected_id = seed_id.make_seed_id(seed_name, slot)
    if "seed_id" in raw:
        if not isinstance(raw["seed_id"], str) or not _SEED_ID_RE.match(raw["seed_id"]):
            raise PatchDataError("seed_id must be 32 lowercase hex digits")
        given_id = bytes.fromhex(raw["seed_id"])
    else:
        given_id = expected_id

    data = PatchData(
        seed_name=seed_name,
        slot=slot,
        player_name=raw["player_name"],
        seed_id=given_id,
        pickups=pickups,
        starting_items=raw.get("starting_items", STANDARD_STARTING_ITEMS),
        starting_location=raw.get("starting_location", STANDARD_STARTING_LOCATION),
    )
    validate(data)
    return data


def load(path: Path) -> PatchData:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PatchDataError(f"{path}: invalid JSON: {error}") from error
    return from_json(raw)


def dump(data: PatchData, path: Path) -> None:
    Path(path).write_text(json.dumps(data.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
