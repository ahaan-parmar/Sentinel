"""Pure trust/lineage logic. No IO, no SQL — data in, data out."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import networkx as nx

from sentinel.models import MemoryEntry, MemoryStatus

if TYPE_CHECKING:
    from sentinel.ledger import Ledger

logger = logging.getLogger(__name__)


def compute_derived_tier(parent_tiers: list[int], own_tier: int) -> int:
    """A derived memory is only as trustworthy as its least-trusted ingredient."""
    if not parent_tiers:
        return own_tier
    return min(parent_tiers)


def build_lineage_graph(entries: list[MemoryEntry]) -> "nx.DiGraph":
    """Build a DiGraph with edges parent_id -> child_id for all given entries."""
    graph: nx.DiGraph = nx.DiGraph()
    for entry in entries:
        graph.add_node(entry.id)
    for entry in entries:
        for parent_id in entry.parent_ids:
            graph.add_edge(parent_id, entry.id)
    return graph


def descendants_of(graph: "nx.DiGraph", memory_id: str) -> set[str]:
    """All transitive descendants of memory_id in the lineage graph."""
    if memory_id not in graph:
        return set()
    return nx.descendants(graph, memory_id)


def quarantine_with_descendants(ledger: "Ledger", memory_id: str) -> list[str]:
    """Mark memory_id and all its lineage descendants as quarantined. Returns affected ids."""
    entries = ledger.list_all()
    graph = build_lineage_graph(entries)
    affected = {memory_id} | descendants_of(graph, memory_id)
    changed: list[str] = []
    for entry_id in affected:
        if ledger.get(entry_id) is None:
            continue
        ledger.set_status(entry_id, MemoryStatus.QUARANTINED)
        changed.append(entry_id)
    logger.info("quarantined %d memories rooted at %s", len(changed), memory_id)
    return changed


def release(ledger: "Ledger", memory_id: str) -> None:
    """Set a single memory back to active. Does not cascade to descendants."""
    ledger.set_status(memory_id, MemoryStatus.ACTIVE)
    logger.info("released memory %s back to active", memory_id)
