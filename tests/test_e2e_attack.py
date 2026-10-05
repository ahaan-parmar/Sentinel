"""End-to-end attack scenario via FastAPI's TestClient against sentinel.api.app.

sentinel/api.py builds its Ledger/Memory/ToolExecutor/SentinelAgent as module-level
globals at import time, reading SENTINEL_DB_PATH (via Ledger's _default_db_path())
at that moment. To get an isolated db file instead of colliding with the demo's
sentinel.db (and other test modules' ledgers), we set SENTINEL_DB_PATH to a fresh
tmp directory BEFORE importing sentinel.api for the first time in this process,
then use the app's own POST /reset (which reseeds via scripts/demo_seed.seed)
to populate it -- /reset recomputes paths from the same env var at call time, so
it stays pointed at our isolated location rather than falling back to a default.

This is a module-level, import-time side effect (unusual for a test file) rather
than a monkeypatched fixture, specifically because sentinel.api's globals are
constructed once at import -- a later env var change would not retroactively
affect the already-constructed `ledger` instance. We accept the resulting serial
coupling (this module must not run after another module has already imported
sentinel.api with a different env var) since the harness guarantees a fresh
process per pytest invocation and this is the only module in this suite that
imports sentinel.api.
"""
from __future__ import annotations

import os
import tempfile

import pytest

_ISOLATED_DB_DIR = tempfile.mkdtemp(prefix="sentinel_e2e_")
os.environ["SENTINEL_DB_PATH"] = os.path.join(_ISOLATED_DB_DIR, "sentinel_e2e.db")
os.environ.setdefault("SENTINEL_LLM_BACKEND", "scripted")

from fastapi.testclient import TestClient  # noqa: E402

from sentinel.api import app  # noqa: E402
from sentinel.models import ActionStatus, AgentMode  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def reseed_scenario():
    """Reset the isolated db to the day-1 seeded scenario before every test."""
    response = client.post("/reset")
    assert response.status_code == 200
    yield


def test_plain_mode_leaks_invoice_to_attacker() -> None:
    """Absent Sentinel, the poisoned tier-2 fact silently redirects the send."""
    response = client.post(
        "/chat", json={"mode": AgentMode.PLAIN.value, "message": "please send my invoice", "day": 5}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["actions"]) == 1
    action = body["actions"][0]
    assert action["tool"] == "send_email"
    assert action["args"]["to"] == "attacker@evil.com"
    assert action["status"] == ActionStatus.EXECUTED.value


def test_sentinel_mode_pauses_and_blames_poisoned_memory() -> None:
    """Sentinel mode taint-checks the same request and pauses it instead of sending."""
    response = client.post(
        "/chat", json={"mode": AgentMode.SENTINEL.value, "message": "please send my invoice", "day": 5}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["actions"]) == 1
    action = body["actions"][0]
    assert action["tool"] == "send_email"
    assert action["args"]["to"] == "attacker@evil.com"
    assert action["status"] == ActionStatus.PENDING_APPROVAL.value

    # Blame should map the poisoned memory id to full (1.0) blame.
    assert action["blame"]
    assert max(action["blame"].values()) == pytest.approx(1.0)

    memories = client.get("/memories").json()
    poisoned = [m for m in memories if m["source"] == "email:newsletter@attacker.example"]
    assert len(poisoned) == 1
    assert poisoned[0]["id"] in action["blame"]
