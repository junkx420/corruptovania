"""Regions of the Metroid Prime 3 APWorld: one AP region per logic node (data/logic.py).

Connections become entrances (several connections between the same two nodes are merged with OR), event sources
become event locations with a locked event item, pickup nodes hold the 99 AP locations. A location's access rule is
its ``escape_requirement`` from the data (E22: the way back from a dead end; ``{"and": []}`` = no rule).

Nodes and event sources that cannot be reached even with every item (and the slot's tricks) are left out, so that
every created region and location is reachable with all items (Archipelago's general reachability test). The logic
is monotonic once "before event X" counts as satisfied (E18), so leaving them out changes nothing.

Tricks (E23, T30): ``create_regions(world, tricks)`` takes the slot's trick levels {trick name: 0-5} (default: every
trick off, the behaviour before T30); the trick leaves of the requirement trees are evaluated with them. Offer only
data/tricks.py USABLE_TRICKS (data/README.md "Tricks").
"""

from __future__ import annotations

import functools
from collections import Counter
from typing import TYPE_CHECKING, Mapping, NamedTuple

from BaseClasses import ItemClassification, Region

from .data import game as game_data
from .data import logic as logic_data
from .items import GAME_NAME, MP3Item, RECORDS, pool_names, starting_names
from .locations import LOCATIONS, MP3Location, location_name_to_id, node_of
from .rules import NEVER, Rule, RuleCompiler, StaticState, trick_levels

if TYPE_CHECKING:
    from . import MP3World

Node = tuple[str, str, str]

START_NODE: Node = tuple(game_data.START_LOCATION)
GOAL_EVENT: str = game_data.VICTORY_REQUIREMENT["name"]


def node_name(node: Node) -> str:
    return " - ".join(node)


class EventSource(NamedTuple):
    location_name: str
    event: str
    node: Node
    requirement: dict


def _event_sources() -> list[EventSource]:
    result = []
    for event, info in logic_data.EVENTS.items():
        sources = info["sources"]
        for k, src in enumerate(sources, 1):
            label = f"Event: {event}" if len(sources) == 1 else f"Event: {event} [{k}]"
            result.append(EventSource(label, event, tuple(src["node"]), src["requirement"]))
    return result


EVENT_SOURCES: list[EventSource] = _event_sources()


def _merged_connections() -> dict[tuple[Node, Node], list[dict]]:
    merged: dict[tuple[Node, Node], list[dict]] = {}
    for conn in logic_data.CONNECTIONS:
        merged.setdefault((tuple(conn["from"]), tuple(conn["to"])), []).append(conn["requirement"])
    return merged


CONNECTIONS: dict[tuple[Node, Node], list[dict]] = _merged_connections()


def all_items_counts() -> Counter:
    """Item counts of the full pool plus the starting items."""
    return Counter(pool_names() + starting_names())


class Graph(NamedTuple):
    nodes: frozenset[Node]  # nodes reachable with all items
    sources: tuple[EventSource, ...]  # event sources reachable with all items
    events: frozenset[str]


def _tricks_key(tricks: Mapping[str, int] | None) -> tuple[tuple[str, int], ...]:
    return tuple(sorted((name, level) for name, level in trick_levels(tricks).items() if level > 0))


def reachable_graph(tricks: Mapping[str, int] | None = None) -> Graph:
    """Least fixpoint of nodes and events with every item and the given trick levels (default: no tricks)."""
    return _reachable_graph(_tricks_key(tricks))


@functools.lru_cache(maxsize=8)
def _reachable_graph(tricks: tuple[tuple[str, int], ...]) -> Graph:
    compiler = RuleCompiler(player=0, tricks=dict(tricks))
    conn_rules = {key: compiler._or([compiler.compile(r) for r in reqs]) for key, reqs in CONNECTIONS.items()}
    source_rules = [(k, src, compiler.compile(src.requirement)) for k, src in enumerate(EVENT_SOURCES)]
    state = StaticState(all_items_counts())
    nodes: set[Node] = {START_NODE}
    sources: set[int] = set()
    changed = True
    while changed:
        changed = False
        for (a, b), rule in conn_rules.items():
            if a in nodes and b not in nodes and rule(state):
                nodes.add(b)
                changed = True
        for k, src, rule in source_rules:
            if k not in sources and src.node in nodes and rule(state):
                sources.add(k)
                if src.event not in state.events:
                    state.events.add(src.event)
                changed = True
    ordered = tuple(src for k, src in enumerate(EVENT_SOURCES) if k in sources)
    return Graph(frozenset(nodes), ordered, frozenset(state.events))


def all_nodes() -> list[Node]:
    return [(r, a, n) for r, region in logic_data.REGIONS.items() for a, area in region["areas"].items()
            for n in area["nodes"]]


def create_regions(world: "MP3World", tricks: Mapping[str, int] | None = None) -> None:
    """Regions, entrances, locations and event locations of one slot; ``tricks`` = its trick levels (E23)."""
    multiworld, player = world.multiworld, world.player
    graph = reachable_graph(tricks)
    compiler = RuleCompiler(player, tricks)

    menu = Region(world.origin_region_name, player, multiworld)
    multiworld.regions.append(menu)

    regions: dict[Node, Region] = {}
    for node in all_nodes():
        if node in graph.nodes:
            region = Region(node_name(node), player, multiworld)
            regions[node] = region
            multiworld.regions.append(region)

    menu.connect(regions[START_NODE], "Start")

    for (a, b), reqs in CONNECTIONS.items():
        if a not in regions or b not in regions:
            continue
        rule: Rule = compiler._or([compiler.compile(r) for r in reqs])
        if rule is NEVER:
            continue
        regions[a].connect(regions[b], f"{node_name(a)} -> {node_name(b)}", rule)

    for loc in LOCATIONS:
        region = regions[node_of(loc)]
        location = MP3Location(player, loc["name"], location_name_to_id[loc["name"]], region)
        location.access_rule = compiler.compile(loc["escape_requirement"])
        region.locations.append(location)

    for src in graph.sources:
        region = regions[src.node]
        location = MP3Location(player, src.location_name, None, region)
        location.access_rule = compiler.compile(src.requirement)
        location.place_locked_item(MP3Item(src.event, ItemClassification.progression, None, player))
        region.locations.append(location)


def starting_resources(names: list[str] | None = None) -> dict[str, int]:
    """Resource amounts from the starting items ``names`` (default: all of data/items.py STARTING_ITEMS, E11)."""
    totals: Counter = Counter()
    for name in starting_names() if names is None else names:
        for stage_resource, qty in RECORDS[name]["stages"][0]:
            totals[stage_resource] += qty
    return dict(totals)


__all__ = ["create_regions", "reachable_graph", "node_name", "START_NODE", "GOAL_EVENT", "GAME_NAME",
           "starting_resources", "EVENT_SOURCES"]
