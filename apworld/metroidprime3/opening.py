"""Opening chain for small starting inventories (E23, T31).

With every removable starting item kept, the start has three checks in logic (4, 11, 17) and T29's one local early
Screw Attack is enough for Archipelago's fill. With any starting item removed only two checks are left (4 and 11), and
every further item opens just zero to three more: the opening is a narrow chain, sometimes one that needs two items at
once (Morph Ball + Morph Ball Bombs). Archipelago's restrictive fill places progression backwards and often uses up the
few early checks for items that are not needed early; it then fails with "No more spots to place".
``local_early_items`` cannot help enough, because it only reaches the two checks of sphere 1 (measured in T31: 0.3-5 %
failures with the best pairs, docs/AP_OPTIONS.md).

So ``pre_fill`` places a short chain **forwards**, in the player's own world. A step puts one of the player's own
progression items on an open check if it opens at least one new check, or, when no single item does, two items that
open something new and leave at least one check open. Steps are chosen at random, weighted by how many checks they
open, until ``OPENING_TARGET`` own checks are open; a dead end backtracks. Every item is placed where the logic
already allows it, so the chain never makes the seed unbeatable; it only fixes which items sit on the first few checks.
The chain's items are locked, so the main fill and progression balancing leave them alone.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, NamedTuple

from BaseClasses import CollectionState, Item, Location, LocationProgressType

if TYPE_CHECKING:
    from . import MP3World

OPENING_TARGET = 8  # own checks open before the main fill starts (measured in T31, docs/AP_OPTIONS.md)
OPENING_MAX_ITEMS = 12  # at most this many items are placed by the chain
OPENING_MAX_NODES = 60  # search budget (steps tried, backtracking included)


class _Node(NamedTuple):
    state: CollectionState
    used: frozenset[Location]  # checks the chain already filled (in the search; placed at the end)
    pool: tuple[Item, ...]  # the player's progression items not yet in the chain


def _open(world: "MP3World", node: _Node) -> list[Location]:
    return [loc for loc in world.multiworld.get_locations(world.player)
            if loc.address is not None and loc.progress_type != LocationProgressType.EXCLUDED
            and loc.item is None and loc not in node.used and loc.can_reach(node.state)]


def _with(world: "MP3World", state: CollectionState, items: tuple[Item, ...]) -> CollectionState:
    state = state.copy()
    for item in items:
        state.collect(item, prevent_sweep=True)
    state.sweep_for_advancements(locations=[loc for loc in world.multiworld.get_locations(world.player)
                                            if loc.address is None])
    return state


def _distinct(pool: tuple[Item, ...]) -> list[Item]:
    seen: dict[str, Item] = {}
    for item in pool:
        seen.setdefault(item.name, item)
    return [seen[name] for name in sorted(seen)]


def _steps(world: "MP3World", node: _Node, open_now: list[Location]) -> list[tuple[tuple[Item, ...], int]]:
    """Possible next steps (items, checks open afterwards): single items that open at least the check they use,
    otherwise pairs that open something new and leave at least one check open."""
    def after(items: tuple[Item, ...]) -> int:
        return len(_open(world, node._replace(state=_with(world, node.state, items)))) - len(items)

    distinct = _distinct(node.pool)
    singles = [((item,), n) for item in distinct if (n := after((item,))) >= len(open_now)]
    if singles or len(open_now) < 2:
        return singles
    return [((a, b), n) for a, b in itertools.combinations(distinct, 2)
            if (n := after((a, b))) >= 1 and n + 2 > len(open_now)]


def _search(world: "MP3World", node: _Node, target: int, max_items: int, budget: list[int]
            ) -> list[tuple[Item, Location]] | None:
    open_now = _open(world, node)
    if len(open_now) >= target:
        return []
    if budget[0] <= 0 or not open_now:
        return None
    steps = _steps(world, node, open_now)
    steps = [(items, n) for items, n in steps if len(node.used) + len(items) <= max_items]
    rng = world.random
    while steps and budget[0] > 0:
        budget[0] -= 1
        k = rng.choices(range(len(steps)), weights=[max(1, n - len(open_now) + 1) for _, n in steps])[0]
        items, _ = steps.pop(k)
        spots = list(open_now)
        placement = []
        for item in items:
            fitting = [loc for loc in spots if loc.can_fill(node.state, item, check_access=False)]
            if not fitting:
                break
            spot = rng.choice(fitting)
            spots.remove(spot)
            placement.append((item, spot))
        if len(placement) != len(items):
            continue
        pool = list(node.pool)
        for item in items:
            pool.remove(item)
        child = _Node(_with(world, node.state, items), node.used | {spot for _, spot in placement}, tuple(pool))
        rest = _search(world, child, target, max_items, budget)
        if rest is not None:
            return placement + rest
    return None


def place_opening(world: "MP3World", target: int | None = None, max_items: int | None = None) -> list[Location]:
    """Place the opening chain of ``world`` (see module doc); returns the filled locations in placement order.

    Defaults: ``OPENING_TARGET`` open checks, at most ``OPENING_MAX_ITEMS`` items. If the search finds no chain within
    its budget nothing is placed (the main fill then runs as without the chain).
    """
    target = OPENING_TARGET if target is None else target
    max_items = OPENING_MAX_ITEMS if max_items is None else max_items
    multiworld, player = world.multiworld, world.player
    pool = tuple(item for item in multiworld.itempool if item.player == player and item.advancement)
    root = _Node(_with(world, CollectionState(multiworld), ()), frozenset(), pool)
    chain = _search(world, root, target, max_items, [OPENING_MAX_NODES]) or []
    for item, location in chain:
        multiworld.itempool.remove(item)
        location.place_locked_item(item)
    return [location for _, location in chain]
