"""FastMCP tool definitions for the 9 agent-facing MCP operations.

Uses the mcp 2.x SDK (MCPServer). Each tool is a function decorated with
``@mcp.tool()`` that returns a JSON-serializable dict.
"""

from __future__ import annotations

from typing import Optional

from mcp.server.mcpserver import MCPServer

from agent_memory.services import core
from agent_memory.schemas import Handoff
from agent_memory.storage.database import Database

mcp = MCPServer("agent-memory")

# The Database instance is injected at startup; tools access it via closure.
_db: Optional[Database] = None


def bind_database(db: Database) -> None:
    global _db
    _db = db


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized; call bind_database() first")
    return _db


# ---------------------------------------------------------------------------
# 1. resolve_project
# ---------------------------------------------------------------------------


@mcp.tool()
async def resolve_project(
    workspace: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict:
    """Identify project identity from a workspace path or explicit project ID.

    Returns project, workspace, repository identity and resolution status.
    """
    db = get_db()
    return await core.resolve_project(db, workspace_path=workspace, project_id=project_id)


# ---------------------------------------------------------------------------
# 2. get_project_context
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_project_context(
    project_id: str,
    task_id: Optional[str] = None,
    include: Optional[list[str]] = None,
    max_output_tokens: int = 2000,
) -> dict:
    """Return compact project background sections within a token budget.

    Sections: project_summary, active_tasks, recent_handoffs,
    accepted_constraints.
    """
    db = get_db()
    return await core.get_project_context(
        db,
        project_id,
        task_id=task_id,
        include=include,
        max_output_tokens=max_output_tokens,
    )


# ---------------------------------------------------------------------------
# 3. search_memory
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_memory(
    project_id: str,
    query: str,
    filters: Optional[dict] = None,
    limit: int = 8,
) -> dict:
    """Search project knowledge using FTS5 lexical index with optional
    sqlite-vec vector RRF fusion. Falls back to LIKE when no index.
    """
    db = get_db()
    return await core.search_memory(db, project_id, query, limit=limit, filters=filters)


# ---------------------------------------------------------------------------
# 4. get_memory
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_memory(memory_id: str) -> Optional[dict]:
    """Fetch a specific knowledge item with its revision history and evidence."""
    db = get_db()
    return await core.get_memory(db, memory_id, include_revisions=True)


# ---------------------------------------------------------------------------
# 5. get_task_state
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_task_state(
    task_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict:
    """Get task status, latest handoff, and recent events.

    Provide task_id for a specific task, or project_id to get the
    most recently active task in that project.
    """
    db = get_db()
    return await core.get_task_state(db, task_id=task_id, project_id=project_id)


# ---------------------------------------------------------------------------
# 6. get_latest_handoff
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_latest_handoff(
    task_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> Optional[dict]:
    """Get the most recent valid handoff for a task or workspace.

    If HEAD SHA has advanced, the handoff may be stale; the caller should
    verify compatibility before continuing.
    """
    db = get_db()
    handoff = await core.get_latest_handoff(db, task_id=task_id, workspace_id=workspace_id)
    if handoff is None:
        return None
    return {
        "handoff": handoff.model_dump(),
        "is_stale": False,
        "needs_revalidation": bool(handoff.source_head_sha),
    }


# ---------------------------------------------------------------------------
# 7. create_handoff
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_handoff(
    task_id: str,
    summary: str,
    completed: Optional[list[str]] = None,
    pending: Optional[list[str]] = None,
    blockers: Optional[list[str]] = None,
    decisions: Optional[list[str]] = None,
    verification_refs: Optional[list[str]] = None,
    next_actions: Optional[list[str]] = None,
    source_agent: str = "unknown",
    source_session_id: Optional[str] = None,
    source_run_id: Optional[str] = None,
    source_workspace_id: Optional[str] = None,
    source_head_sha: Optional[str] = None,
) -> dict:
    """Submit a new handoff record for a task. Increments revision.

    The receiving agent should read this before starting work.
    """
    db = get_db()
    h = Handoff(
        task_id=task_id,
        source_agent=source_agent,
        source_session_id=source_session_id,
        source_run_id=source_run_id,
        source_workspace_id=source_workspace_id,
        source_head_sha=source_head_sha,
        summary=summary,
        completed=completed or [],
        pending=pending or [],
        blockers=blockers or [],
        decisions=decisions or [],
        verification_refs=verification_refs or [],
        next_actions=next_actions or [],
    )
    result = await core.create_handoff(db, h)
    return {
        "handoff_id": result.handoff_id,
        "revision": result.revision,
        "task_id": task_id,
    }


# ---------------------------------------------------------------------------
# 8. submit_memory_candidate
# ---------------------------------------------------------------------------


@mcp.tool()
async def submit_memory_candidate(
    project_id: str,
    idempotency_key: str,
    memories: list[dict],
    run_id: Optional[str] = None,
) -> dict:
    """Submit structured memory candidates for review.

    Idempotent per (project_id, idempotency_key, title).
    Does NOT auto-accept; approval is a separate admin operation.
    """
    db = get_db()
    return await core.submit_memory_candidate(
        db,
        project_id,
        idempotency_key,
        memories,
        run_id=run_id,
    )


# ---------------------------------------------------------------------------
# 9. update_task_state
# ---------------------------------------------------------------------------


@mcp.tool()
async def update_task_state(
    task_id: str,
    expected_revision: int,
    state: str,
    reason: Optional[str] = None,
) -> dict:
    """Update task status with optimistic locking.

    States: pending, active, blocked, completed, cancelled.
    Raises VERSION_CONFLICT if expected_revision is stale.
    """
    db = get_db()
    task = await core.update_task_state(
        db, task_id, expected_revision, state, reason=reason
    )
    return {
        "task_id": task_id,
        "new_revision": task.revision,
        "status": task.status.value,
    }
