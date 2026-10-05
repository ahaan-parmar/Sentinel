"""FastAPI app. Route handlers are thin -- all logic delegates to agent.py and the
other sentinel modules; this file wires them together and shapes HTTP responses."""
from __future__ import annotations

import gc
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sentinel import gate as gate_module
from sentinel import tools as tools_module
from sentinel import trust
from sentinel.agent import SentinelAgent
from sentinel.gate import add_to_review_queue, list_review_queue
from sentinel.ledger import Ledger
from sentinel.memory import Memory, WriteBlocked
from sentinel.models import (
    TRUST_TIER_EXTERNAL,
    TRUST_TIER_USER,
    BlockedWrite,
    ChatRequest,
    ChatResponse,
    GraphEdge,
    GraphEdgeType,
    GraphNode,
    GraphNodeType,
    GraphResponse,
    IngestRequest,
    IngestResponse,
    MemoryEntry,
    MemoryKind,
    ReportResponse,
    ReviewQueueItem,
    SourceType,
    VerifyResponse,
)
from sentinel.tools import ToolExecutor

logger = logging.getLogger(__name__)

app = FastAPI(title="Sentinel")

# CORS: wide open for localhost dev UI on any port.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single shared instances for the whole process -- no DI framework, hackathon speed.
ledger = Ledger()
memory = Memory(ledger)
executor = ToolExecutor()
sentinel_agent = SentinelAgent(ledger, memory, executor)

# Session-local state for /report's fix_applied and dwell-time reconstruction.
# MemoryEntry has no "day" field (only an ISO timestamp), and /ingest is the only
# place a demo "day" is ever supplied for a memory, so we track it here.
_fix_applied = False
_ingest_day_by_memory: dict[str, int] = {}


def _classify_kind(content: str) -> MemoryKind:
    """Hackathon heuristic: content reads as an explicit preference/rule ("prefer",
    "always", or a "send X to Y" redirect instruction) -> PREFERENCE, else FACT."""
    lowered = content.lower()
    if "prefer" in lowered or "always" in lowered:
        return MemoryKind.PREFERENCE
    if "send" in lowered and " to " in lowered:
        return MemoryKind.PREFERENCE
    return MemoryKind.FACT


def _trust_tier_for(source_type: SourceType) -> int:
    return TRUST_TIER_USER if source_type == SourceType.USER else TRUST_TIER_EXTERNAL


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    return sentinel_agent.handle_chat(request)


@app.post("/ingest", response_model=IngestResponse)
def ingest(request: IngestRequest) -> IngestResponse:
    kind = _classify_kind(request.content)
    trust_tier = _trust_tier_for(request.source_type)
    memory_ids: list[str] = []
    blocked: list[BlockedWrite] = []
    try:
        entry = memory.add(request.content, kind, request.source, trust_tier)
        memory_ids.append(entry.id)
        _ingest_day_by_memory[entry.id] = request.day
    except WriteBlocked as exc:
        # Blocked writes are both reported back to the caller and persisted to the
        # review queue, so a human can see them via /review-queue.
        add_to_review_queue(request.content, kind, request.source, exc.reason)
        blocked.append(
            BlockedWrite(reason=exc.reason, content=request.content, kind=kind, source=request.source)
        )
    return IngestResponse(memory_ids=memory_ids, blocked=blocked)


@app.get("/memories", response_model=list[MemoryEntry])
def get_memories() -> list[MemoryEntry]:
    return ledger.list_all()


@app.get("/graph", response_model=GraphResponse)
def get_graph() -> GraphResponse:
    entries = ledger.list_all()

    # Highlight memory nodes that were ever implicated in a blamed (paused) action.
    blame_by_memory: dict[str, float] = {}
    for record in sentinel_agent.recorded_actions:
        for memory_id, score in record["result"].blame.items():
            blame_by_memory[memory_id] = max(blame_by_memory.get(memory_id, 0.0), score)

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    for entry in entries:
        node_type = GraphNodeType.DERIVED if entry.parent_ids else GraphNodeType.MEMORY
        nodes.append(
            GraphNode(
                id=entry.id,
                type=node_type,
                label=entry.content[:80],
                trust_tier=entry.trust_tier,
                status=entry.status,
                blame=blame_by_memory.get(entry.id),
            )
        )
        for parent_id in entry.parent_ids:
            edges.append(GraphEdge(from_=parent_id, to=entry.id, type=GraphEdgeType.DERIVED_FROM))

    for index, record in enumerate(sentinel_agent.recorded_actions):
        action = record["result"]
        if not action.blame:
            continue
        node_id = action.action_id or f"action-{index}"
        nodes.append(
            GraphNode(
                id=node_id,
                type=GraphNodeType.TOOL_CALL,
                label=f"{action.tool}({action.args})",
            )
        )
        for memory_id in action.blame:
            edges.append(GraphEdge(from_=memory_id, to=node_id, type=GraphEdgeType.CAUSED))

    return GraphResponse(nodes=nodes, edges=edges)


@app.get("/review-queue", response_model=list[ReviewQueueItem])
def get_review_queue() -> list[ReviewQueueItem]:
    return list_review_queue()


@app.post("/approve/{action_id}")
def approve(action_id: str):
    return executor.approve(action_id)


@app.post("/deny/{action_id}")
def deny(action_id: str):
    return executor.deny(action_id)


@app.post("/quarantine/{memory_id}")
def quarantine(memory_id: str) -> dict:
    global _fix_applied
    quarantined = trust.quarantine_with_descendants(ledger, memory_id)
    _fix_applied = True
    return {"quarantined": quarantined}


@app.post("/release/{memory_id}")
def release(memory_id: str) -> dict:
    trust.release(ledger, memory_id)
    return {"ok": True}


@app.post("/rollback")
def rollback() -> dict:
    global _fix_applied
    ledger.rollback_to_last_clean_snapshot()
    _fix_applied = True
    return {"ok": True}


@app.get("/verify", response_model=VerifyResponse)
def verify() -> VerifyResponse:
    ok, broken_at = ledger.verify_chain()
    return VerifyResponse(ok=ok, broken_at=broken_at)


@app.get("/report", response_model=ReportResponse)
def report() -> ReportResponse:
    entries_by_id = {entry.id: entry for entry in ledger.list_all()}
    lineage = trust.build_lineage_graph(list(entries_by_id.values()))

    # Candidate = (timestamp, memory_id, day attempted, blocked ActionResult) for every
    # tier-2 memory with non-zero blame recorded in any paused action this session.
    candidates: list[tuple[str, str, int, dict]] = []
    for record in sentinel_agent.recorded_actions:
        action = record["result"]
        for memory_id, score in action.blame.items():
            if score <= 0:
                continue
            entry = entries_by_id.get(memory_id)
            if entry is None or entry.trust_tier != 2:
                continue
            candidates.append((entry.timestamp, memory_id, record["day"], action.model_dump(mode="json")))

    if not candidates:
        return ReportResponse(
            entry_point=None,
            dwell_time_days=None,
            affected_memories=[],
            blocked_action=None,
            fix_applied=_fix_applied,
        )

    candidates.sort(key=lambda candidate: candidate[0])
    _, entry_memory_id, attempted_day, blocked_action = candidates[0]
    entry = entries_by_id[entry_memory_id]
    ingest_day = _ingest_day_by_memory.get(entry_memory_id, 0)
    affected = {entry_memory_id} | trust.descendants_of(lineage, entry_memory_id)

    return ReportResponse(
        entry_point=entry.source,
        dwell_time_days=attempted_day - ingest_day,
        affected_memories=sorted(affected),
        blocked_action=blocked_action,
        fix_applied=_fix_applied,
    )


@app.post("/reset")
def reset() -> dict:
    """Wipe the demo environment's db files and reseed. Nothing in the ledger is ever
    deleted row-by-row by design, so a full "reset" means a fresh sqlite file."""
    global ledger, memory, executor, sentinel_agent, _fix_applied, _ingest_day_by_memory

    from scripts import demo_seed  # local import: avoids a circular import at module load

    db_paths = {ledger.db_path, gate_module._db_path(), tools_module._db_path()}
    ledger.close()
    # gate.py/tools.py open a fresh sqlite3 connection per call via `with _connect() as
    # conn:` -- that context manager only ends the transaction, it does not close the
    # connection (sqlite3 quirk), so a GC pass here helps release any lingering file
    # handles before we try to delete the underlying files on Windows.
    gc.collect()
    for path in db_paths:
        if not path or not os.path.exists(path):
            continue
        try:
            os.remove(path)
        except OSError:
            logger.warning("could not remove %s during /reset (file still locked)", path)

    ledger = Ledger()
    memory = Memory(ledger)
    executor = ToolExecutor()
    sentinel_agent = SentinelAgent(ledger, memory, executor)
    _fix_applied = False
    _ingest_day_by_memory = {}

    demo_seed.seed(ledger=ledger, memory=memory)
    return {"ok": True}
