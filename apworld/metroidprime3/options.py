"""Options of the Metroid Prime 3 APWorld: Archipelago's standard options plus starting items and tricks (E23, T31)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from Options import Choice, OptionDict, OptionError, OptionSet, PerGameCommonOptions
from schema import And, Optional, Or, Schema

from .data import tricks as trick_data

# Removable starting items (E23). Power Beam, Combat Visor and Scan Visor always stay: the client needs Power Beam > 0
# to recognise the game state, and scanning is mandatory.
REMOVABLE_STARTING_ITEMS: tuple[str, ...] = ("Charge Beam", "Space Jump Boots", "Morph Ball", "Morph Ball Bombs")
FIXED_STARTING_ITEMS: tuple[str, ...] = ("Power Beam", "Combat Visor", "Scan Visor")

# Trick level names offered by the YAML (Corruptovania levels 0-3; data/game.py TRICK_LEVEL_NAMES says "disabled"
# for 0). Levels above data/tricks.py USABLE_MAX_LEVEL are not offered (E23 "off ... advanced").
TRICK_LEVELS: dict[str, int] = {"off": 0, "beginner": 1, "intermediate": 2, "advanced": 3}
USABLE_TRICKS: dict[str, int] = dict(trick_data.USABLE_TRICKS)


def _level_names(max_level: int) -> list[str]:
    return [name for name, level in TRICK_LEVELS.items() if level <= max_level]


def _trick_value(max_level: int):
    """Allowed override values for one trick: a level name up to ``max_level``, the number 0..max_level, or ``false``
    (YAML 1.1 reads a bare ``off`` as false)."""
    names = _level_names(max_level)
    return Or(And(str, lambda v, names=names: v.lower() in names),
              And(int, lambda v, top=max_level: not isinstance(v, bool) and 0 <= v <= top),
              And(bool, lambda v: v is False))


def _trick_list() -> str:
    return "\n".join(f"    {name}: up to {_level_names(level)[-1]}" for name, level in USABLE_TRICKS.items())


class StartingItems(OptionSet):
    """Which of the removable starting items you keep. Every item you leave out is shuffled into the item pool instead
    (one Missile Expansion leaves the pool for it, so there are still 99 items).

    Removable: Charge Beam, Space Jump Boots, Morph Ball, Morph Ball Bombs.
    Power Beam, Combat Visor and Scan Visor are always kept.

    With any item removed the opening of the game is narrow: before the main fill, the world places a short random
    chain of your own progression items on your first checks until eight checks are open (always in logic, so it
    never blocks you). Archipelago's start_inventory still works on top of this.
    """
    display_name = "Kept Starting Items"
    valid_keys = REMOVABLE_STARTING_ITEMS
    default = frozenset(REMOVABLE_STARTING_ITEMS)


class TrickLevel(Choice):
    """EXPERIMENTAL. Global trick level the logic may expect from you. Only tricks the logic data rates as usable are
    affected, each capped at its highest offered level (Invisible Objects and Open Barriers from Behind stop at
    intermediate). The escape logic (getting out of a dead end again) never expects tricks.

    off: no tricks (default). beginner / intermediate / advanced: Corruptovania's trick levels 1-3.
    """
    display_name = "Trick Level (experimental)"
    option_off = 0
    option_beginner = 1
    option_intermediate = 2
    option_advanced = 3
    default = 0


class TrickOverrides(OptionDict):
    """EXPERIMENTAL. Per-trick levels that replace the global Trick Level for that trick. Value: off, beginner,
    intermediate or advanced (or 0-3), at most the trick's highest offered level. Offered tricks (example:
    {"Bomb Jump": "advanced", "Combat": "off"}):
    """
    display_name = "Trick Overrides (experimental)"
    valid_keys = tuple(USABLE_TRICKS)
    default = {}
    schema = Schema({Optional(name): _trick_value(level) for name, level in USABLE_TRICKS.items()})


TrickOverrides.__doc__ += "\n" + _trick_list() + "\n"


def trick_level_value(value: str | int) -> int:
    if isinstance(value, str):
        try:
            return TRICK_LEVELS[value.lower()]
        except KeyError:
            raise OptionError(f"unknown trick level {value!r}, expected one of {list(TRICK_LEVELS)}") from None
    return int(value)


def resolve_tricks(global_level: int, overrides: Mapping[str, str | int]) -> dict[str, int]:
    """The slot's trick levels {trick name: level} for ``regions.create_regions``; only tricks above 0 are listed.

    Global level per usable trick, capped at its highest offered level; an override replaces it (schema-checked).
    """
    result: dict[str, int] = {}
    for name, top in USABLE_TRICKS.items():
        level = trick_level_value(overrides[name]) if name in overrides else min(global_level, top)
        if not 0 <= level <= top:
            raise OptionError(f"trick {name!r}: level {level} is above the offered maximum {top}")
        if level:
            result[name] = level
    return result


@dataclass
class MP3Options(PerGameCommonOptions):
    starting_items: StartingItems
    trick_level: TrickLevel
    trick_overrides: TrickOverrides
