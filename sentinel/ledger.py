"""SQLite-backed append-only ledger of MemoryEntry rows, hash-chained for tamper detection."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from sentinel.models import MemoryEntry, MemoryKind, MemoryStatus
from sentinel.trust import build_lineage_graph, descendants_of

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    trust_tier INTEGER NOT NULL,
    parent_ids TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL,
    status TEXT NOT NULL,
    row_seq INTEGER
);

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    last_row_seq INTEGER NOT NULL,
    timestamp TEXT NOT NULL
);
"""


def _default_db_path() -> str:
    return os.environ.get("SENTINEL_DB_PATH", os.path.join(os.getcwd(), "sentinel.db"))


def _canonical_hash(
    id_: str,
    content: str,
    kind: str,
    source: str,
    trust_tier: int,
    parent_ids: list[str],
    timestamp: str,
    prev_hash: str,
) -> str:
    """sha256 over a canonical concat of the entry's chained fields."""
    parts = [
        id_,
        content,
        kind,
        source,
        str(trust_tier),
        json.dumps(parent_ids, sort_keys=True, separators=(",", ":")),
        timestamp,
        prev_hash,
    ]
    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
    return MemoryEntry(
        id=row["id"],
        content=row["content"],
        kind=MemoryKind(row["kind"]),
        source=row["source"],
        trust_tier=row["trust_tier"],
        parent_ids=json.loads(row["parent_ids"]),
        timestamp=row["timestamp"],
        prev_hash=row["prev_hash"],
        hash=row["hash"],
        status=MemoryStatus(row["status"]),
    )


class Ledger:
    """Append-only, hash-chained store for MemoryEntry rows. Never deletes rows."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _default_db_path()
        # FastAPI runs sync routes in a threadpool, so the connection must be shared
        # across threads; serialize access with a lock since sqlite3 connections
        # aren't safe for concurrent use even with check_same_thread=False.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _last_entry_row(self) -> sqlite3.Row | None:
        cur = self._conn.execute(
            "SELECT * FROM memories ORDER BY row_seq DESC LIMIT 1"
        )
        return cur.fetchone()

    def append(
        self,
        content: str,
        kind: MemoryKind,
        source: str,
        trust_tier: int,
        parent_ids: list[str] | None = None,
    ) -> MemoryEntry:
        """Append a new entry, chained to the current tip. Rows are never mutated except status."""
        parent_ids = parent_ids or []
        with self._lock:
            last_row = self._last_entry_row()
            prev_hash = last_row["hash"] if last_row is not None else GENESIS_HASH
            next_seq = (last_row["row_seq"] + 1) if last_row is not None else 0

            entry_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()
            kind_value = kind.value if isinstance(kind, MemoryKind) else kind
            entry_hash = _canonical_hash(
                entry_id, content, kind_value, source, trust_tier, parent_ids, timestamp, prev_hash
            )

            self._conn.execute(
                """INSERT INTO memories
                   (id, content, kind, source, trust_tier, parent_ids, timestamp, prev_hash, hash, status, row_seq)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    content,
                    kind_value,
                    source,
                    trust_tier,
                    json.dumps(parent_ids),
                    timestamp,
                    prev_hash,
                    entry_hash,
                    MemoryStatus.ACTIVE.value,
                    next_seq,
                ),
            )
            self._conn.commit()
        logger.info("appended memory %s (seq=%d)", entry_id, next_seq)
        return MemoryEntry(
            id=entry_id,
            content=content,
            kind=kind,
            source=source,
            trust_tier=trust_tier,
            parent_ids=parent_ids,
            timestamp=timestamp,
            prev_hash=prev_hash,
            hash=entry_hash,
            status=MemoryStatus.ACTIVE,
        )

    def get(self, id_: str) -> MemoryEntry | None:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM memories WHERE id = ?", (id_,))
            row = cur.fetchone()
        return _row_to_entry(row) if row is not None else None

    def list_all(self) -> list[MemoryEntry]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM memories ORDER BY row_seq ASC")
            rows = cur.fetchall()
        return [_row_to_entry(row) for row in rows]

    def set_status(self, id_: str, status: MemoryStatus) -> None:
        status_value = status.value if isinstance(status, MemoryStatus) else status
        with self._lock:
            self._conn.execute(
                "UPDATE memories SET status = ? WHERE id = ?", (status_value, id_)
            )
            self._conn.commit()
        logger.info("set status of %s to %s", id_, status_value)

    def verify_chain(self) -> tuple[bool, str | None]:
        """Recompute hashes in row order, checking prev_hash linkage and hash integrity."""
        entries = self.list_all()
        expected_prev = GENESIS_HASH
        for entry in entries:
            if entry.prev_hash != expected_prev:
                return False, entry.id
            recomputed = _canonical_hash(
                entry.id,
                entry.content,
                entry.kind.value,
                entry.source,
                entry.trust_tier,
                entry.parent_ids,
                entry.timestamp,
                entry.prev_hash,
            )
            if recomputed != entry.hash:
                return False, entry.id
            expected_prev = entry.hash
        return True, None

    def snapshot(self, label: str) -> str:
        """Record a marker at the current chain tip. Snapshots are never deleted."""
        with self._lock:
            last_row = self._last_entry_row()
            last_seq = last_row["row_seq"] if last_row is not None else -1
            snapshot_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                "INSERT INTO snapshots (snapshot_id, label, last_row_seq, timestamp) VALUES (?, ?, ?, ?)",
                (snapshot_id, label, last_seq, timestamp),
            )
            self._conn.commit()
        logger.info("recorded snapshot %s (%s) at row_seq=%d", snapshot_id, label, last_seq)
        return snapshot_id

    def _snapshots_desc(self) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM snapshots ORDER BY last_row_seq DESC"
            )
            return cur.fetchall()

    def rollback_to_last_clean_snapshot(self) -> list[str]:
        """Quarantine the tampered lineage after the break point, sparing independently clean writes.

        Finds the first chain break (if any). Walks snapshots newest-first to find one taken
        at or before the break point (a "clean" snapshot). Everything after the break is then
        quarantined EXCEPT entries that are not descendants of the break point's lineage —
        those are independently clean and are left untouched. Returns the ids quarantined.
        """
        ok, broken_id = self.verify_chain()
        if ok:
            logger.info("chain is intact, nothing to roll back")
            return []

        entries = self.list_all()
        by_id = {e.id: e for e in entries}
        broken_entry = by_id.get(broken_id) if broken_id else None
        if broken_entry is None:
            logger.warning("chain broken at unknown/missing id %s; cannot localize tamper", broken_id)
            return []

        # pick the latest snapshot whose tip predates the tampered row, i.e. "last clean snapshot"
        clean_snapshots = [
            s for s in self._snapshots_desc() if s["last_row_seq"] < self._row_seq(broken_id)
        ]
        if clean_snapshots:
            logger.info(
                "last clean snapshot %s at row_seq=%d", clean_snapshots[0]["snapshot_id"], clean_snapshots[0]["last_row_seq"]
            )

        # lineage: quarantine the tampered entry and its descendants only, not unrelated siblings
        graph = build_lineage_graph(entries)
        tainted = {broken_id} | descendants_of(graph, broken_id)

        changed: list[str] = []
        for entry in entries:
            if entry.id in tainted and entry.status != MemoryStatus.QUARANTINED:
                self.set_status(entry.id, MemoryStatus.QUARANTINED)
                changed.append(entry.id)
        logger.warning("rollback quarantined %d memories due to tamper at %s", len(changed), broken_id)
        return changed

    def _row_seq(self, id_: str) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT row_seq FROM memories WHERE id = ?", (id_,))
            row = cur.fetchone()
        return row["row_seq"] if row is not None else -1
