from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectState(BaseModel):
    schema_version: int = 1
    project_id: str
    workroot: str
    created_at: datetime
    updated_at: datetime
    notes_enabled: bool = True
    memory_enabled: bool = True
    index_enabled: bool = True
    safety_policy: str = "default"


class SessionState(BaseModel):
    session_id: str
    workroot: str
    created_at: datetime
    updated_at: datetime
    status: str = "running"
    goal: str = ""
    active: bool = True
    error: str | None = None
    crash_count: int = 0


class GoalState(BaseModel):
    goal_id: str
    session_id: str
    text: str
    parsed: dict[str, Any] | None = None
    status: Literal[
        "queued",
        "understanding",
        "planning",
        "executing",
        "testing",
        "complete",
        "failed",
    ] = "queued"
    created_at: datetime
    updated_at: datetime


class ToolCall(BaseModel):
    call_id: str
    session_id: str
    tool: str
    params: dict[str, Any]
    status: Literal["requested", "running", "success", "blocked", "failed"] = (
        "requested"
    )
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    duration_ms: int | None = None


class ProviderCall(BaseModel):
    call_id: str
    provider_id: str
    model: str
    role: str
    status: str
    attempt: int = 1
    duration_ms: int | None = None
    error: str | None = None
    fallback: str | None = None
    fallback_reason: str | None = None


class CouncilRole(BaseModel):
    role: str
    provider_id: str | None = None
    model: str | None = None
    status: str = "pending"
    completed_at: datetime | None = None
    summary: str | None = None


class FusionResult(BaseModel):
    role: str
    model: str
    output: str | None = None
    confidence: float = 0.0
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SafetyDecision(BaseModel):
    decision: Literal["allow", "block", "warn"] = "allow"
    action: str
    reason: str
    path: str | None = None
    model_config = {"arbitrary_types_allowed": True}


class LocationClassification(BaseModel):
    target: str
    classification: str
    risk: Literal["low", "medium", "high"] = "low"
    policy_decision: str = "allowed"


class BrowserSession(BaseModel):
    session_id: str
    url: str
    state: Literal["starting", "ready", "closed"] = "ready"
    profile_path: str
    created_at: datetime


class CompactionRecord(BaseModel):
    session_id: str
    reason: str
    compressed_items: int = 0
    created_at: datetime
    snapshot: dict[str, Any] = Field(default_factory=dict)


class EventRecord(BaseModel):
    time: datetime
    session_id: str
    event: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ErrorRecord(BaseModel):
    time: datetime
    session_id: str
    error: str
    context: str | None = None
    recoverable: bool = False
