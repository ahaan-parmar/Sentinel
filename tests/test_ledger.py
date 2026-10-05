"""Hash-chain tamper detection for Ledger."""
from __future__ import annotations

import sqlite3

import pytest

from sentinel.ledger import Ledger
from sentinel.models import MemoryKind, TRUST_TIER_USER


@pytest.fixture
def ledger(tmp_path) -> Ledger:
    db_path = str(tmp_path / "ledger_test.db")
    return Ledger(db_path=db_path)


def _append_chain(ledger: Ledger, n: int) -> list[str]:
    ids = []
    for i in range(n):
        entry = ledger.append(
            f"entry number {i}", MemoryKind.FACT, "user", TRUST_TIER_USER
        )
        ids.append(entry.id)
    return ids


def test_verify_chain_ok_on_untampered_chain(ledger: Ledger) -> None:
    _append_chain(ledger, 5)
    ok, broken_id = ledger.verify_chain()
    assert ok is True
    assert broken_id is None


def test_verify_chain_detects_tampered_content(ledger: Ledger) -> None:
    ids = _append_chain(ledger, 5)
    tampered_id = ids[2]

    conn = sqlite3.connect(ledger.db_path)
    conn.execute(
        "UPDATE memories SET content = ? WHERE id = ?",
        ("this content was tampered with", tampered_id),
    )
    conn.commit()
    conn.close()

    ok, broken_id = ledger.verify_chain()
    assert ok is False
    assert broken_id == tampered_id


def test_verify_chain_detects_tampered_hash(ledger: Ledger) -> None:
    ids = _append_chain(ledger, 4)
    tampered_id = ids[1]

    conn = sqlite3.connect(ledger.db_path)
    conn.execute(
        "UPDATE memories SET hash = ? WHERE id = ?",
        ("0" * 64, tampered_id),
    )
    conn.commit()
    conn.close()

    ok, broken_id = ledger.verify_chain()
    assert ok is False
    assert broken_id == tampered_id
