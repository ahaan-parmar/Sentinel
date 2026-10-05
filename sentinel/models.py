"""Shared pydantic contracts for Sentinel. All agents import from here only."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MemoryKind(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    RULE = "rule"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    QUARANTINED = "quarantined"


class SourceType(str, Enum):
    EMAIL = "email"
    URL = "url"
    USER = "user"


class ActionStatus(str, Enum):
    EXECUTED = "executed"
    BLOCKED = "blocked"
    PENDING_APPROVAL = "pending_approval"


class AgentMode(str, Enum):
    PLAIN = "plain"
    SENTINEL = "sentinel"


# Trust tiers: 0 = user-authored (most trusted), 1 = internal/derived, 2 = external/untrusted (email, url)
TRUST_TIER_USER = 0
TRUST_TIER_INTERNAL = 1
TRUST_TIER_EXTERNAL = 2


class MemoryEntry(BaseModel):
    id: str
    content: str
    kind: MemoryKind
    source: str
    trust_tier: int = Field(ge=0, le=2)
    parent_ids: list[str] = Field(default_factory=list)
    timestamp: str
    prev_hash: str
    hash: str
    status: MemoryStatus = MemoryStatus.ACTIVE


class MemoryCreate(BaseModel):
    content: str
    kind: MemoryKind
    source: str
    trust_tier: int = Field(ge=0, le=2)
    parent_ids: list[str] = Field(default_factory=list)


class BlockedWrite(BaseModel):
    reason: str
    content: str
    kind: MemoryKind
    source: str


class ChatRequest(BaseModel):
    mode: AgentMode
    message: str
    day: int


class ActionResult(BaseModel):
    tool: str
    args: dict
    status: ActionStatus
    blame: dict[str, float] = Field(default_factory=dict)
    action_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    actions: list[ActionResult]


class IngestRequest(BaseModel):
    source: str
    source_type: SourceType
    content: str
    day: int


class IngestResponse(BaseModel):
    memory_ids: list[str]
    blocked: list[BlockedWrite]


class GraphNodeType(str, Enum):
    SOURCE = "source"
    MEMORY = "memory"
    DERIVED = "derived"
    TOOL_CALL = "tool_call"


class GraphNode(BaseModel):
    id: str
    type: GraphNodeType
    label: str
    trust_tier: Optional[int] = None
    status: Optional[MemoryStatus] = None
    blame: Optional[float] = None


class GraphEdgeType(str, Enum):
    WROTE = "wrote"
    DERIVED_FROM = "derived_from"
    CAUSED = "caused"


class GraphEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    type: GraphEdgeType


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class ReviewQueueItem(BaseModel):
    id: str
    reason: str
    content: str
    kind: MemoryKind
    source: str
    timestamp: str


class PendingAction(BaseModel):
    action_id: str
    tool: str
    args: dict
    risk_score: float
    tainted_memory_ids: list[str] = Field(default_factory=list)
    day: int


class VerifyResponse(BaseModel):
    ok: bool
    broken_at: Optional[str] = None


class ReportResponse(BaseModel):
    entry_point: Optional[str]
    dwell_time_days: Optional[int]
    affected_memories: list[str]
    blocked_action: Optional[dict]
    fix_applied: bool


class ToolCall(BaseModel):
    tool: str
    args: dict


RISKY_TOOLS = {"send_email", "http_request"}
