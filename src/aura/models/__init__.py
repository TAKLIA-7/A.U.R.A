"""AURA typed data models."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:8]
    return f"{prefix}{short}" if prefix else short


# ── Enums ─────────────────────────────────────────────────────────────────────

class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionResult(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    APPROVAL_REQUIRED = "approval_required"
    PENDING = "pending"
    ERROR = "error"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    INTERCEPTED = "intercepted"
    ASSESSING = "assessing"
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    APPROVAL_PENDING = "approval_pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXECUTED = "executed"
    FAILED = "failed"


class EventLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ── Actions ───────────────────────────────────────────────────────────────────

class ActionRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: _uid("req_"))
    tool: str
    operation: str = ""
    target: str = ""
    arguments: Dict[str, Any] = Field(default_factory=dict)
    data_classification: str = "internal"
    reversible: bool = True


class ActionResult(BaseModel):
    request_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None


# ── JEV ───────────────────────────────────────────────────────────────────────

class JEVContextPayload(BaseModel):
    request_id: str
    user_intent: str
    action: Dict[str, Any]
    identity: Dict[str, Any]
    session: Dict[str, Any]
    policy_context: Dict[str, Any]


class JEVAssessment(BaseModel):
    assessment_id: str = Field(default_factory=lambda: _uid("assess_"))
    request_id: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    risk_factors: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    recommended_action: DecisionResult = DecisionResult.ALLOW
    requires_human_review: bool = False
    provider: str = "mock"
    latency_ms: float = 0.0
    raw_response: Optional[Dict[str, Any]] = None


# ── Decisions ─────────────────────────────────────────────────────────────────

class PolicyDecision(BaseModel):
    request_id: str
    assessment_id: Optional[str] = None
    decision: DecisionResult
    reason: str
    policy_rule_id: Optional[str] = None
    requires_human_review: bool = False
    enforced: bool = False


# ── Runs ──────────────────────────────────────────────────────────────────────

class RunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: _uid("run_"))
    session_id: str = ""
    user_prompt: str = ""
    provider: str = ""
    model: str = ""
    status: RunStatus = RunStatus.RUNNING
    started_at: datetime = Field(default_factory=_now)
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    total_tool_calls: int = 0
    allowed_actions: int = 0
    blocked_actions: int = 0
    pending_approvals: int = 0
    jev_assessments: int = 0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    error: Optional[str] = None
    timeline: List[Dict[str, Any]] = Field(default_factory=list)

    def add_event(self, event_type: str, detail: Optional[Dict] = None) -> None:
        self.timeline.append({
            "timestamp": _now().isoformat(),
            "event_type": event_type,
            "detail": detail or {},
        })


# ── Audit Events ──────────────────────────────────────────────────────────────

class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: _uid("evt_"))
    timestamp: datetime = Field(default_factory=_now)
    level: EventLevel = EventLevel.INFO
    event_type: str
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    request_id: Optional[str] = None
    assessment_id: Optional[str] = None
    actor: Optional[Dict[str, Any]] = None
    action: Optional[Dict[str, Any]] = None
    jev: Optional[Dict[str, Any]] = None
    decision: Optional[Dict[str, Any]] = None
    execution: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"schema_version": "1.0"})

    def to_jsonl(self) -> str:
        import json
        data = self.model_dump(mode="json", exclude_none=True)
        return json.dumps(data, default=str)
