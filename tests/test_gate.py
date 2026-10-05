"""Write gate rules + review queue round-trip."""
from __future__ import annotations

import os

import pytest

from sentinel.gate import (
    add_to_review_queue,
    check_write,
    list_review_queue,
    remove_from_review_queue,
)
from sentinel.models import TRUST_TIER_EXTERNAL, TRUST_TIER_INTERNAL, TRUST_TIER_USER, MemoryKind


@pytest.fixture(autouse=True)
def isolated_review_db(tmp_path, monkeypatch):
    """gate.py reads SENTINEL_DB_PATH at call time, so point it at a scratch file
    per test to avoid colliding with the demo's sentinel_review.db."""
    db_path = str(tmp_path / "review_test.db")
    monkeypatch.setenv("SENTINEL_DB_PATH", db_path)
    yield db_path


@pytest.mark.parametrize("kind", [MemoryKind.PREFERENCE, MemoryKind.RULE])
def test_tier2_preference_and_rule_blocked(kind: MemoryKind) -> None:
    allowed, reason = check_write("some content", kind, "email:x", TRUST_TIER_EXTERNAL)
    assert allowed is False
    assert reason is not None


def test_tier2_fact_allowed() -> None:
    allowed, reason = check_write("some fact", MemoryKind.FACT, "email:x", TRUST_TIER_EXTERNAL)
    assert allowed is True
    assert reason is None


@pytest.mark.parametrize("tier", [TRUST_TIER_USER, TRUST_TIER_INTERNAL])
@pytest.mark.parametrize("kind", [MemoryKind.FACT, MemoryKind.PREFERENCE, MemoryKind.RULE])
def test_tier0_and_tier1_always_allowed(tier: int, kind: MemoryKind) -> None:
    allowed, reason = check_write("anything", kind, "user", tier)
    assert allowed is True
    assert reason is None


def test_review_queue_add_list_remove_roundtrip() -> None:
    assert list_review_queue() == []

    item_id = add_to_review_queue(
        "blocked content", MemoryKind.PREFERENCE, "email:attacker", "tier 2 preference blocked"
    )

    queue = list_review_queue()
    assert len(queue) == 1
    assert queue[0].id == item_id
    assert queue[0].content == "blocked content"
    assert queue[0].kind == MemoryKind.PREFERENCE
    assert queue[0].source == "email:attacker"
    assert queue[0].reason == "tier 2 preference blocked"

    remove_from_review_queue(item_id)
    assert list_review_queue() == []
