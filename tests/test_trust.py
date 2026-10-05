"""Trust inheritance: tier computation, lineage graph, quarantine cascade, release."""
from __future__ import annotations

import pytest

from sentinel.ledger import Ledger
from sentinel.models import (
    TRUST_TIER_EXTERNAL,
    TRUST_TIER_INTERNAL,
    TRUST_TIER_USER,
    MemoryKind,
    MemoryStatus,
)
from sentinel.trust import compute_derived_tier, quarantine_with_descendants, release


@pytest.fixture
def ledger(tmp_path) -> Ledger:
    db_path = str(tmp_path / "trust_test.db")
    return Ledger(db_path=db_path)


def test_compute_derived_tier_picks_min_of_parents() -> None:
    assert compute_derived_tier([0, 1, 2], own_tier=0) == 0
    assert compute_derived_tier([1, 2], own_tier=0) == 1
    assert compute_derived_tier([2, 2], own_tier=0) == 2


def test_compute_derived_tier_falls_back_to_own_tier_when_no_parents() -> None:
    assert compute_derived_tier([], own_tier=1) == 1


def test_derived_entry_inherits_min_parent_tier_via_ledger_append(ledger: Ledger) -> None:
    user_fact = ledger.append(
        "user says X", MemoryKind.FACT, "user", TRUST_TIER_USER
    )
    tainted_fact = ledger.append(
        "attacker says Y", MemoryKind.FACT, "email:attacker", TRUST_TIER_EXTERNAL
    )

    # min(parent tiers) wins regardless of own_tier -- the least-trusted parent
    # (tier 0, the user fact) drags the derived tier down to 0 here.
    derived_tier = compute_derived_tier(
        [user_fact.trust_tier, tainted_fact.trust_tier], own_tier=TRUST_TIER_INTERNAL
    )
    assert derived_tier == TRUST_TIER_USER

    derived = ledger.append(
        "derived summary of X and Y",
        MemoryKind.FACT,
        "agent",
        derived_tier,
        parent_ids=[user_fact.id, tainted_fact.id],
    )
    assert derived.trust_tier == TRUST_TIER_USER
    assert derived.parent_ids == [user_fact.id, tainted_fact.id]

    # And with two tier-2 parents, the derived tier correctly stays at tier 2.
    another_tainted = ledger.append(
        "attacker says Z", MemoryKind.FACT, "email:attacker", TRUST_TIER_EXTERNAL
    )
    all_external_tier = compute_derived_tier(
        [tainted_fact.trust_tier, another_tainted.trust_tier], own_tier=TRUST_TIER_INTERNAL
    )
    assert all_external_tier == TRUST_TIER_EXTERNAL


def test_quarantine_with_descendants_cascades_two_generations(ledger: Ledger) -> None:
    root = ledger.append("root fact", MemoryKind.FACT, "email:attacker", TRUST_TIER_EXTERNAL)
    child = ledger.append(
        "child derived from root", MemoryKind.FACT, "agent", TRUST_TIER_EXTERNAL,
        parent_ids=[root.id],
    )
    grandchild = ledger.append(
        "grandchild derived from child", MemoryKind.FACT, "agent", TRUST_TIER_EXTERNAL,
        parent_ids=[child.id],
    )
    unrelated = ledger.append("unrelated fact", MemoryKind.FACT, "user", TRUST_TIER_USER)

    changed = quarantine_with_descendants(ledger, root.id)

    assert set(changed) == {root.id, child.id, grandchild.id}
    assert ledger.get(root.id).status == MemoryStatus.QUARANTINED
    assert ledger.get(child.id).status == MemoryStatus.QUARANTINED
    assert ledger.get(grandchild.id).status == MemoryStatus.QUARANTINED
    assert ledger.get(unrelated.id).status == MemoryStatus.ACTIVE


def test_release_undoes_single_node_without_cascading(ledger: Ledger) -> None:
    root = ledger.append("root fact", MemoryKind.FACT, "email:attacker", TRUST_TIER_EXTERNAL)
    child = ledger.append(
        "child derived from root", MemoryKind.FACT, "agent", TRUST_TIER_EXTERNAL,
        parent_ids=[root.id],
    )
    quarantine_with_descendants(ledger, root.id)
    assert ledger.get(root.id).status == MemoryStatus.QUARANTINED
    assert ledger.get(child.id).status == MemoryStatus.QUARANTINED

    release(ledger, root.id)

    assert ledger.get(root.id).status == MemoryStatus.ACTIVE
    assert ledger.get(child.id).status == MemoryStatus.QUARANTINED
