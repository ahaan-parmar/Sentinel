"""Write gate: decides whether a memory write is allowed, plus a persisted review queue
for writes that get blocked. No LLM calls here — pure rule logic + simple SQLite storage.

Review queue storage: SQLite file. Uses SENTINEL_DB_PATH env var if set (so it can share
a db file/location with the ledger), otherwise defaults to sentinel/sentinel_review.db.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sentinel.models import MemoryKind, ReviewQueueItem

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path(__file__).resolve().parent / "sentinel_review.db"


def _db_path() -> str:
    # Shared override point with ledger.py, if the other agent's Ledger also reads it.
    return os.environ.get("SENTINEL_DB_PATH", str(_DEFAULT_DB_PATH))


@contextmanager
def _connect():
    # `with sqlite3.Connection` only ends the transaction, not the connection itself —
    # close it explicitly so connections don't accumulate for the life of the process.
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_queue (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                kind TEXT NOT NULL,
                source TEXT NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        with conn:
            yield conn
    finally:
        conn.close()


def check_write(
    content: str, kind: MemoryKind, source: str, trust_tier: int
) -> tuple[bool, str | None]:
    """Block untrusted (tier 2) content unless it's being saved as a plain FACT."""
    if trust_tier == 2 and kind != MemoryKind.FACT:
        reason = (
            "tier 2 (untrusted) content cannot be saved as preference/rule, "
            "only as fact"
        )
        logger.info("blocked write: %s", reason)
        return False, reason
    return True, None


def add_to_review_queue(content: str, kind: MemoryKind, source: str, reason: str) -> str:
    """Persist a blocked write for later human review. Returns the new item's id."""
    item_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO review_queue (id, content, kind, source, reason, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (item_id, content, kind.value, source, reason, timestamp),
        )
    logger.info("added blocked write %s to review queue", item_id)
    return item_id


def list_review_queue() -> list[ReviewQueueItem]:
    """Return all pending review-queue items, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content, kind, source, reason, timestamp FROM review_queue "
            "ORDER BY timestamp ASC"
        ).fetchall()
    return [
        ReviewQueueItem(
            id=row[0],
            content=row[1],
            kind=MemoryKind(row[2]),
            source=row[3],
            reason=row[4],
            timestamp=row[5],
        )
        for row in rows
    ]


def remove_from_review_queue(id: str) -> None:
    """Remove an item from the review queue, e.g. once a human has acted on it."""
    with _connect() as conn:
        conn.execute("DELETE FROM review_queue WHERE id = ?", (id,))
    logger.info("removed %s from review queue", id)
