"""FastMCP tool input/output contracts."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------

MCP_ERROR_CODES = [
    "PROJECT_UNRESOLVED",
    "PROJECT_ACCESS_DENIED",
    "SESSION_NOT_FOUND",
    "TASK_CONFLICT",
    "VERSION_CONFLICT",
    "INVALID_EVIDENCE",
    "APPROVAL_REQUIRED",
    "MEMORY_DUPLICATE",
    "EMBEDDING_UNAVAILABLE",
    "INVALID_SCHEMA_VERSION",
]


class McpToolError(BaseModel):
    code: str
    message: str


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class ResolveProjectInput(BaseModel):
    workspace: Optional[str] = None
    project_id: Optional[str] = None


class GetProjectContextInput(BaseModel):
    project_id: str
    task_id: Optional[str] = None
    include: list[str] = Field(default_factory=lambda: ["project_summary", "active_tasks"])
    max_output_tokens: int = 2000


class SearchMemoryInput(BaseModel):
    project_id: str
    query: str
    filters: Optional[dict] = None
    limit: int = 8


class GetMemoryInput(BaseModel):
    memory_id: str


class GetTaskStateInput(BaseModel):
    task_id: Optional[str] = None
    project_id: Optional[str] = None


class GetLatestHandoffInput(BaseModel):
    task_id: Optional[str] = None
    workspace_id: Optional[str] = None


class CreateHandoffInput(BaseModel):
    task_id: str
    summary: str
    completed: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    verification_refs: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    source_head_sha: Optional[str] = None


class SubmitMemoryCandidateInput(BaseModel):
    project_id: str
    run_id: Optional[str] = None
    idempotency_key: str
    memories: list[dict]


class UpdateTaskStateInput(BaseModel):
    task_id: str
    expected_revision: int
    state: str
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


class ProjectIdentity(BaseModel):
    project_id: str
    name: str
    workspace_id: Optional[str] = None
    repository_id: Optional[str] = None


class ProjectContext(BaseModel):
    project_id: str
    sections: dict[str, str]
    truncated: bool = False
    references: list[str] = Field(default_factory=list)


class MemorySearchResult(BaseModel):
    results: list[dict]
    retrieval_mode: str = "hybrid"  # "hybrid" | "lexical_only"


class MemoryDetail(BaseModel):
    memory: dict
    revisions: list[dict] = Field(default_factory=list)


class TaskState(BaseModel):
    task: dict
    latest_handoff: Optional[dict] = None
    recent_events: list[dict] = Field(default_factory=list)


class HandoffResult(BaseModel):
    handoff: dict
    is_stale: bool = False
    needs_revalidation: bool = False


class HandoffCreated(BaseModel):
    handoff_id: str
    revision: int
    task_id: str


class MemoryCandidateResult(BaseModel):
    candidate_ids: list[str]
    validation_status: list[str] = Field(default_factory=list)
    duplicate_count: int = 0


class TaskStateUpdated(BaseModel):
    task_id: str
    new_revision: int
    status: str

