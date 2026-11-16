"""Core identity and lifecycle entities.

These Pydantic models define the stable schemas used by:
- SQLite storage layer (Phase 1)
- FastMCP tools (Phase 2)
- HTTP event API (Phase 1/2)
- Agent adapters (Phase 3+)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _new_uuid() -> str:
    return str(uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class KnowledgeStatus(str, Enum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class KnowledgeScope(str, Enum):
    RUN = "run"
    TASK = "task"
    PROJECT = "project"
    GLOBAL = "global"


class EvidenceKind(str, Enum):
    GIT_COMMIT = "git_commit"
    FILE_PATH = "file_path"
    TEST_RESULT = "test_result"
    TOOL_OUTPUT = "tool_output"
    USER_CONFIRMATION = "user_confirmation"
    AGENT_STATEMENT = "agent_statement"


# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------


class SchemaModel(BaseModel):
    """Base for all contract models; adds schema_version."""

    schema_version: str = Field(default="1.0")


# ---------------------------------------------------------------------------
# Project / Repository / Workspace
# ---------------------------------------------------------------------------


class Project(SchemaModel):
    project_id: str = Field(default_factory=_new_uuid)
    name: str
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_at: str = Field(default_factory=_utcnow)
    updated_at: str = Field(default_factory=_utcnow)


class Repository(SchemaModel):
    repository_id: str = Field(default_factory=_new_uuid)
    project_id: str
    remote_url_hash: str
    root_fingerprint: str
    created_at: str = Field(default_factory=_utcnow)


class Workspace(SchemaModel):
    workspace_id: str = Field(default_factory=_new_uuid)
    repository_id: str
    canonical_path: str
    worktree_id: Optional[str] = None
    created_at: str = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Session / Run
# ---------------------------------------------------------------------------


class AgentType(str, Enum):
    PI = "pi"
    CODEX = "codex"
    OPENCODE = "opencode"
    ORCA = "orca"
    UNKNOWN = "unknown"


class Session(SchemaModel):
    session_id: str = Field(default_factory=_new_uuid)
    agent_type: AgentType
    native_session_id: Optional[str] = None
    workspace_id: str
    created_at: str = Field(default_factory=_utcnow)


class Run(SchemaModel):
    run_id: str = Field(default_factory=_new_uuid)
    session_id: str
    task_id: Optional[str] = None
    status: RunStatus = RunStatus.RUNNING
    head_sha_start: Optional[str] = None
    head_sha_end: Optional[str] = None
    started_at: str = Field(default_factory=_utcnow)
    ended_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


class EventEnvelope(SchemaModel):
    """Unified envelope for all hook events."""

    event_id: str = Field(default_factory=_new_uuid)
    event_type: str  # e.g. "run.settled", "checkpoint.created"
    agent: AgentType
    session_id: str
    run_id: str
    project_id: Optional[str] = None
    workspace_id: Optional[str] = None
    task_id: Optional[str] = None
    sequence_no: int = 0
    occurred_at: str = Field(default_factory=_utcnow)
    payload: dict = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, v: str) -> str:
        allowed = {
            "run.started",
            "run.settled",
            "run.interrupted",
            "checkpoint.created",
            "session.start",
            "session.end",
            "session.compacted",
            "turn.end",
            "memory.extraction_requested",
            "memory.extraction_completed",
        }
        if v not in allowed:
            raise ValueError(f"Unknown event_type: {v!r}")
        return v


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------


class Checkpoint(SchemaModel):
    checkpoint_id: str = Field(default_factory=_new_uuid)
    run_id: str
    source_revision: Optional[str] = None
    summary: str
    created_at: str = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Handoff
# ---------------------------------------------------------------------------


class Handoff(SchemaModel):
    handoff_id: str = Field(default_factory=_new_uuid)
    task_id: str
    source_agent: str
    source_session_id: Optional[str] = None
    source_run_id: Optional[str] = None
    source_workspace_id: Optional[str] = None
    source_head_sha: Optional[str] = None
    state: str = "in_progress"
    summary: str
    completed: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    verification_refs: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    revision: int = 1
    created_at: str = Field(default_factory=_utcnow)
    updated_at: str = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Knowledge / Memory
# ---------------------------------------------------------------------------


class EvidenceRef(SchemaModel):
    kind: EvidenceKind
    value: str


class Knowledge(SchemaModel):
    memory_id: str = Field(default_factory=_new_uuid)
    project_id: str
    scope: KnowledgeScope = KnowledgeScope.PROJECT
    type: str  # e.g. "adr", "problem_solution", "constraint"
    status: KnowledgeStatus = KnowledgeStatus.CANDIDATE
    title: str
    content: str
    revision: int = 1
    current_source_revision: Optional[str] = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    supersedes_memory_id: Optional[str] = None
    created_at: str = Field(default_factory=_utcnow)
    updated_at: str = Field(default_factory=_utcnow)


class MemoryCandidate(SchemaModel):
    """Payload submitted by an agent via MCP submit_memory_candidate."""

    project_id: str
    run_id: Optional[str] = None
    idempotency_key: str
    memories: list[dict]  # each dict matches Knowledge minus ids/timestamps


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


class Task(SchemaModel):
    task_id: str = Field(default_factory=_new_uuid)
    project_id: str
    title: str
    status: TaskStatus = TaskStatus.PENDING
    revision: int = 1
    owner_session_id: Optional[str] = None
    created_at: str = Field(default_factory=_utcnow)
    updated_at: str = Field(default_factory=_utcnow)
