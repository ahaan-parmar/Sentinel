"""Quarantine cascade + hash-chain rollback behavior."""
from __future__ import annotations

import sqlite3

import pytest

from sentinel.ledger import Ledger
from sentinel.models import TRUST_TIER_EXTERNAL, TRUST_TIER_USER, MemoryKind, MemoryStatus
from sentinel.trust import quarantine_with_descendants


@pytest.fixture
def ledger(tmp_path) -> Ledger:
    db_path = str(tmp_path / "qr_test.db")
    return Ledger(db_path=db_path)


def test_quarantine_marks_lineage_and_spares_active_entries(ledger: Ledger) -> None:
    bad_root = ledger.append("bad root", MemoryKind.FACT, "email:attacker", TRUST_TIER_EXTERNAL)
    bad_child = ledger.append(
        "bad child", MemoryKind.FACT, "agent", TRUST_TIER_EXTERNAL, parent_ids=[bad_root.id]
    )
    clean = ledger.append("clean independent fact", MemoryKind.FACT, "user", TRUST_TIER_USER)

    changed = quarantine_with_descendants(ledger, bad_root.id)

    assert set(changed) == {bad_root.id, bad_child.id}
    assert ledger.get(bad_root.id).status == MemoryStatus.QUARANTINED
    assert ledger.get(bad_child.id).status == MemoryStatus.QUARANTINED
    assert ledger.get(clean.id).status == MemoryStatus.ACTIVE


def test_rollback_quarantines_only_tampered_lineage(ledger: Ledger) -> None:
    # Pre-tamper clean history.
    ledger.snapshot("pre-tamper-clean")
    bad_root = ledger.append("bad root", MemoryKind.FACT, "email:attacker", TRUST_TIER_EXTERNAL)
    bad_child = ledger.append(
        "bad child derived from bad root",
        MemoryKind.FACT,
        "agent",
        TRUST_TIER_EXTERNAL,
        parent_ids=[bad_root.id],
    )
    # Independent entry added after the bad lineage but NOT descended from it --
    # must survive rollback untouched.
    independent_after = ledger.append(
        "independent fact added later", MemoryKind.FACT, "user", TRUST_TIER_USER
    )

    # Tamper bad_root's content directly in the db file, breaking the chain at bad_root.
    conn = sqlite3.connect(ledger.db_path)
    conn.execute(
        "UPDATE memories SET content = ? WHERE id = ?",
        ("tampered content", bad_root.id),
    )
    conn.commit()
    conn.close()

    ok, broken_id = ledger.verify_chain()
    assert ok is False
    assert broken_id == bad_root.id

    changed = ledger.rollback_to_last_clean_snapshot()

    assert set(changed) == {bad_root.id, bad_child.id}
    assert ledger.get(bad_root.id).status == MemoryStatus.QUARANTINED
    assert ledger.get(bad_child.id).status == MemoryStatus.QUARANTINED
    assert ledger.get(independent_after.id).status == MemoryStatus.ACTIVE


def test_rollback_on_intact_chain_is_a_noop(ledger: Ledger) -> None:
    ledger.append("fine fact", MemoryKind.FACT, "user", TRUST_TIER_USER)
    changed = ledger.rollback_to_last_clean_snapshot()
    assert changed == []
