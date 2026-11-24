"""Evaluation of the requirement trees in data/logic.py as Archipelago rules.

A compiled rule is a function ``rule(state) -> bool`` that only uses ``state.has(name, player, count)`` and
``state.count(name, player)``. That makes it work on an Archipelago ``CollectionState`` and on the small
``StaticState`` below (used to prune what is unreachable even with all items).

Semantics (data/README.md, SPEC E18):
- ``and``/``or``: empty ``and`` = always, empty ``or`` = never.
- ``item``: resource amount >= ``amount``. Resources come from the item stages (n-th copy gives stage n, the last
  stage repeats), starting items are precollected and count the same way. Launcher lock: ammo of an item whose
  ``lock.opened_by`` is another item only counts while that item is held (possession logic, data README).
- ``event``: event item held. ``event`` with ``negate`` ("before event X") = satisfied (E18, the escape gate is
  already part of the connection requirements).
- ``trick``: never satisfied in the MVP. ``item`` with ``negate`` and ``node``: never satisfied.
- ``damage``: ``starting_energy + energy_per_tank * tanks > ceil(reduction * int(amount * strictness))``,
  reduction = smallest factor of the held reduction items (data/game.py SETTINGS["damage"]).
- ``misc``/``version``: static switches from SETTINGS, ``negate`` = value < amount.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Callable, Iterable

from .data import game as game_data
from .data import logic as logic_data
from .items import RECORDS

Rule = Callable[[object], bool]


def _always(state) -> bool:
    return True


def _never(state) -> bool:
    return False


ALWAYS: Rule = _always
NEVER: Rule = _never


class _Provider:
    """One item that gives a resource: cumulative amount by number of copies and the lock it depends on."""

    __slots__ = ("item", "per_stage", "needs")

    def __init__(self, item: str, resource: str, record: dict) -> None:
        self.item = item
        self.per_stage = [sum(q for r, q in stage if r == resource) for stage in record["stages"]]
        lock = record.get("lock")
        self.needs = None
        if lock and lock["item"] == resource and lock["opened_by"] != item:
            self.needs = lock["opened_by"]

    def amount(self, copies: int) -> int:
        stages = self.per_stage
        n = len(stages)
        if copies <= n:
            return sum(stages[:copies])
        return sum(stages) + (copies - n) * stages[-1]

    def copies_for(self, amount: int) -> int | None:
        """Smallest number of copies that gives at least ``amount``; None if impossible."""
        total = 0
        for k, q in enumerate(self.per_stage):
            if total >= amount:
                return k
            total += q
        if total >= amount:
            return len(self.per_stage)
        last = self.per_stage[-1]
        if last <= 0:
            return None
        return len(self.per_stage) + math.ceil((amount - total) / last)


def _build_providers() -> dict[str, list[_Provider]]:
    providers: dict[str, list[_Provider]] = {}
    for name, record in RECORDS.items():
        resources = {r for stage in record["stages"] for r, _ in stage}
        for resource in sorted(resources):
            providers.setdefault(resource, []).append(_Provider(name, resource, record))
    return providers


PROVIDERS = _build_providers()


class RuleCompiler:
    """Compiles requirement trees into rules for one player. Templates are compiled once and shared."""

    def __init__(self, player: int) -> None:
        self.player = player
        settings = game_data.SETTINGS
        self.misc = settings["misc_resources"]
        self.version = settings["version_resources"]
        self.damage = settings["damage"]
        self._templates: dict[str, Rule] = {}
        self._items: dict[tuple[str, int], Rule] = {}

    # ------------------------------------------------------------------ public
    def compile(self, req: dict) -> Rule:
        if "and" in req:
            return self._and([self.compile(r) for r in req["and"]])
        if "or" in req:
            return self._or([self.compile(r) for r in req["or"]])
        kind = req["type"]
        name = req.get("name")
        amount = req.get("amount", 1)
        negate = req.get("negate", False)
        if kind == "template":
            if name not in self._templates:
                self._templates[name] = self.compile(logic_data.TEMPLATES[name])
            return self._templates[name]
        if kind == "item":
            return NEVER if negate else self.resource_at_least(name, amount)
        if kind == "event":
            if negate:
                return ALWAYS  # "before event X" (E18)
            player = self.player
            return lambda state: state.has(name, player)
        if kind == "trick":
            return NEVER  # MVP: no tricks
        if kind == "damage":
            return self._damage(name, amount)
        if kind in ("misc", "version"):
            have = (self.misc if kind == "misc" else self.version).get(name, 0)
            return ALWAYS if ((have < amount) if negate else (have >= amount)) else NEVER
        if kind == "node":
            return NEVER
        raise ValueError(f"unknown requirement type {kind!r}")

    def resource_at_least(self, resource: str, amount: int) -> Rule:
        key = (resource, amount)
        if key not in self._items:
            self._items[key] = self._resource_rule(resource, amount)
        return self._items[key]

    # ------------------------------------------------------------------ helpers
    def _resource_rule(self, resource: str, amount: int) -> Rule:
        if amount <= 0:
            return ALWAYS
        providers = PROVIDERS.get(resource, [])
        if not providers:
            return NEVER
        player = self.player
        if len(providers) == 1 and providers[0].needs is None:
            copies = providers[0].copies_for(amount)
            if copies is None:
                return NEVER
            item = providers[0].item
            return lambda state: state.has(item, player, copies)
        provs = tuple(providers)

        def rule(state) -> bool:
            total = 0
            for p in provs:
                if p.needs is not None and not state.has(p.needs, player):
                    continue
                n = state.count(p.item, player)
                if n:
                    total += p.amount(n)
                    if total >= amount:
                        return True
            return False

        return rule

    def _damage(self, name: str, amount: int) -> Rule:
        settings = self.damage
        needed_base = int(amount * settings["strictness"])
        start, per_tank = settings["starting_energy"], settings["energy_per_tank"]

        def tanks_for(factor: float) -> int:
            needed = math.ceil(factor * needed_base)
            # smallest t with start + per_tank * t > needed
            return max(0, math.floor((needed - start) / per_tank) + 1)

        options = [self.resource_at_least("Energy Tank", tanks_for(1.0))]
        for item, factor in settings["reductions"].get(name, []):
            tanks = self.resource_at_least("Energy Tank", tanks_for(factor))
            options.append(tanks if item is None else self._and([self.resource_at_least(item, 1), tanks]))
        return self._or(options)

    @staticmethod
    def _and(rules: list[Rule]) -> Rule:
        rules = [r for r in rules if r is not ALWAYS]
        if any(r is NEVER for r in rules):
            return NEVER
        rules = list(dict.fromkeys(rules))
        if not rules:
            return ALWAYS
        if len(rules) == 1:
            return rules[0]
        if len(rules) == 2:
            a, b = rules
            return lambda state: a(state) and b(state)
        rs = tuple(rules)
        return lambda state: all(r(state) for r in rs)

    @staticmethod
    def _or(rules: list[Rule]) -> Rule:
        rules = [r for r in rules if r is not NEVER]
        if any(r is ALWAYS for r in rules):
            return ALWAYS
        rules = list(dict.fromkeys(rules))
        if not rules:
            return NEVER
        if len(rules) == 1:
            return rules[0]
        if len(rules) == 2:
            a, b = rules
            return lambda state: a(state) or b(state)
        rs = tuple(rules)
        return lambda state: any(r(state) for r in rs)


class StaticState:
    """Minimal stand-in for CollectionState: fixed item counts plus a growing set of events."""

    def __init__(self, counts: dict[str, int] | Counter, events: Iterable[str] = ()) -> None:
        self.counts = dict(counts)
        self.events = set(events)

    def count(self, name: str, player: int) -> int:
        if name in self.events:
            return 1
        return self.counts.get(name, 0)

    def has(self, name: str, player: int, count: int = 1) -> bool:
        return self.count(name, player) >= count
