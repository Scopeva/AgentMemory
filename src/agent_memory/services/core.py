"""Application service layer.

Both FastMCP tools and the FastAPI HTTP API call these functions. No
repository access should be duplicated across MCP and HTTP handlers.
"""

from __future__ import annotations

from typing import Optional

from agent_memory.schemas import (
    Checkpoint,
    EventEnvelope,
    Handoff,
    Knowledge,
    KnowledgeStatus,
    Project,
    Repository,
    Run,
    Session,
    Task,
    TaskStatus,
    Workspace,
)
from agent_memory.storage import repositories as repo
from agent_memory.storage.database import Database
from agent_memory.storage.repositories.knowledge import VersionConflictError
from agent_memory.storage.repositories.tasks import TaskConflictError

# Optional retrieval layer — injected by main.py at startup.
from agent_memory.retrieval.search import SearchService  # noqa: F401


class ProjectUnresolvedError(Exception):
    """Raised when project identity cannot be resolved."""


class TaskConflictServiceError(Exception):
    """Wrapper for TaskConflictError with context."""


class VersionConflictServiceError(Exception):
    """Wrapper for VersionConflictError with context."""


# ---------------------------------------------------------------------------
# Project / Identity
# ---------------------------------------------------------------------------


async def resolve_project(
    db: Database,
    workspace_path: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict:
    """Resolve project identity from a workspace path or explicit project_id.

    Returns a dict with project, workspace, and resolution status.
    """
    from agent_memory.core.projects import identity

    if project_id:
        result = await identity.resolve_project_by_id(db, project_id)
        if result.project is None:
            raise ProjectUnresolvedError(result.reason or "Project not found")
        return {
            "project": result.project,
            "workspace": result.workspace,
            "repository": result.repository,
            "status": result.status,
            "reason": result.reason,
        }

    if workspace_path:
        result = await identity.resolve_project_by_workspace(db, workspace_path)
        if result.status == "unresolved":
            raise ProjectUnresolvedError(result.reason or "Workspace not registered")
        # Resolve repository and project from workspace
        project = None
        repository = None
        if result.workspace:
            # Look up repository by workspace.repository_id
            async with db.connection() as conn:
                cursor = await conn.execute(
                    "SELECT repository_id, project_id FROM workspaces WHERE workspace_id = ?",
                    (result.workspace.workspace_id,),
                )
                row = await cursor.fetchone()
                if row:
                    repository = await repo.projects.get_repository_by_fingerprint(
                        db, row["project_id"], ""
                    ) if False else None
                    # Simpler: fetch project via workspace -> repository join
                    cursor2 = await conn.execute(
                        "SELECT p.project_id, p.name, p.status "
                        "FROM projects p "
                        "JOIN repositories r ON r.project_id = p.project_id "
                        "JOIN workspaces w ON w.repository_id = r.repository_id "
                        "WHERE w.workspace_id = ?",
                        (result.workspace.workspace_id,),
                    )
                    prow = await cursor2.fetchone()
                    if prow:
                        project = Project(
                            project_id=prow["project_id"],
                            name=prow["name"],
                            status=prow["status"],
                        )
        return {
            "project": project,
            "workspace": result.workspace,
            "repository": repository,
            "status": "resolved" if project else "partial",
            "reason": result.reason,
        }

    raise ProjectUnresolvedError("Neither workspace path nor project_id provided")


async def get_project_context(
    db: Database,
    project_id: str,
    task_id: Optional[str] = None,
    include: Optional[list[str]] = None,
    max_output_tokens: int = 2000,
) -> dict:
    """Return compact project context within a token budget.

    This is a Phase 2 skeleton: it assembles available data sections.
    The actual tokenization/truncation strategy can be refined in Phase 6.
    """
    if include is None:
        include = ["project_summary", "active_tasks", "recent_handoffs"]

    project = await repo.projects.get_project(db, project_id)
    if project is None:
        raise ProjectUnresolvedError(f"Project {project_id} not found")

    sections: dict[str, str] = {}

    if "project_summary" in include:
        sections["project_summary"] = f"{project.name} ({project.status.value})"

    if "active_tasks" in include:
        tasks = await repo.tasks.list_tasks_by_project(
            db, project_id, status=TaskStatus.ACTIVE, limit=10
        )
        sections["active_tasks"] = "\n".join(f"- {t.title} [{t.status.value}]" for t in tasks)

    if "recent_handoffs" in include:
        # Get latest handoffs for the project's active tasks
        active_tasks = await repo.tasks.list_tasks_by_project(
            db, project_id, status=TaskStatus.ACTIVE, limit=5
        )
        handoffs = []
        for t in active_tasks:
            h = await repo.handoffs.get_latest_handoff(db, task_id=t.task_id)
            if h:
                handoffs.append(f"[{t.title}] {h.summary} (agent: {h.source_agent})")
        sections["recent_handoffs"] = "\n".join(handoffs) if handoffs else "No recent handoffs"

    if "accepted_constraints" in include:
        accepted = await repo.knowledge.list_knowledge_by_project(
            db,
            project_id,
            status=KnowledgeStatus.ACCEPTED,
            limit=10,
        )
        sections["accepted_constraints"] = "\n".join(
            f"- {k.title}: {k.content[:100]}" for k in accepted
        )

    # Truncate by character count as a proxy for tokens
    budget_chars = max_output_tokens * 4  # rough chars-per-token estimate
    result_sections: dict[str, str] = {}
    total_chars = 0
    truncated = False
    for key, value in sections.items():
        if total_chars + len(value) > budget_chars:
            truncated = True
            result_sections[key] = value[: max(0, budget_chars - total_chars)]
            break
        result_sections[key] = value
        total_chars += len(value)

    return {
        "project_id": project_id,
        "sections": result_sections,
        "truncated": truncated,
        "references": [],
    }


# ---------------------------------------------------------------------------
# Task / Handoff
# ---------------------------------------------------------------------------


async def get_task_state(
    db: Database,
    task_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict:
    """Get task status, latest handoff, and recent events."""
    if task_id:
        task = await repo.tasks.get_task(db, task_id)
        if task is None:
            raise ProjectUnresolvedError(f"Task {task_id} not found")
    elif project_id:
        active = await repo.tasks.list_tasks_by_project(
            db, project_id, status=TaskStatus.ACTIVE, limit=1
        )
        if not active:
            return {"task": None, "latest_handoff": None, "recent_events": []}
        task = active[0]
    else:
        raise ProjectUnresolvedError("Either task_id or project_id required")

    handoff = await repo.handoffs.get_latest_handoff(db, task_id=task.task_id)
    events: list[dict] = []
    if handoff and handoff.source_run_id:
        events = await repo.events.get_events_by_run(db, handoff.source_run_id, limit=10)

    return {
        "task": task.model_dump(),
        "latest_handoff": handoff.model_dump() if handoff else None,
        "recent_events": events,
    }


async def create_handoff(db: Database, handoff: Handoff) -> Handoff:
    """Create a new handoff record for a task. Increments revision."""
    return await repo.handoffs.create_handoff(db, handoff)


async def get_latest_handoff(
    db: Database,
    task_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> Optional[Handoff]:
    """Get the most recent valid (non-stale) handoff."""
    return await repo.handoffs.get_latest_handoff(db, task_id=task_id, workspace_id=workspace_id)


async def update_task_state(
    db: Database,
    task_id: str,
    expected_revision: int,
    state: str,
    reason: Optional[str] = None,
) -> Task:
    """Update task status with optimistic locking."""
    try:
        status = TaskStatus(state)
    except ValueError:
        raise ValueError(f"Invalid task state: {state!r}")
    try:
        return await repo.tasks.update_task_status(
            db, task_id, expected_revision=expected_revision, status=status
        )
    except TaskConflictError as e:
        raise TaskConflictServiceError(str(e)) from e


# ---------------------------------------------------------------------------
# Knowledge
# ---------------------------------------------------------------------------


# Reference to the JobDispatcher, set by main.py when retrieval is enabled.
_job_dispatcher = None


def set_job_dispatcher(dispatcher) -> None:
    """Inject the JobDispatcher for enqueuing index jobs on knowledge changes."""
    global _job_dispatcher
    _job_dispatcher = dispatcher


async def submit_memory_candidate(
    db: Database,
    project_id: str,
    idempotency_key: str,
    memories: list[dict],
    run_id: Optional[str] = None,
) -> dict:
    """Submit memory candidates. Idempotent per key; one candidate per memory.
    """
    inserted: list[str] = []
    duplicates = 0
    for memory in memories:
        candidate_id = await repo.knowledge.insert_memory_candidate(
            db, project_id, run_id, idempotency_key=f"{idempotency_key}:{memory.get('title','')}",
            memory_json=memory,
        )
        if candidate_id:
            inserted.append(candidate_id)
        else:
            duplicates += 1
    return {
        "candidate_ids": inserted,
        "validation_status": ["ok" for _ in inserted] + ["duplicate" for _ in range(duplicates)],
        "duplicate_count": duplicates,
    }


async def get_memory(db: Database, memory_id: str, include_revisions: bool = True) -> Optional[dict]:
    """Fetch a knowledge item with optional revision history."""
    return await repo.knowledge.get_knowledge(db, memory_id, include_revisions=include_revisions)


# ---------------------------------------------------------------------------
# Knowledge governance (Phase 6)
# ---------------------------------------------------------------------------


async def governance_summary(
    db: Database,
    project_id: str,
    max_age_days: int = 30,
) -> dict:
    """Aggregate governance metrics for a project."""
    from agent_memory.services.governance import governance_summary as _gs
    return await _gs(db, project_id, max_age_days=max_age_days)


async def find_superseded(
    db: Database,
    project_id: str,
    content_threshold: float = 0.85,
    limit: int = 50,
) -> list[dict]:
    """Find accepted knowledge items that may have been superseded."""
    from agent_memory.services.governance import find_superseded as _fs
    return await _fs(db, project_id, content_threshold, limit)


async def find_duplicates(
    db: Database,
    project_id: str,
    title_threshold: float = 0.90,
    content_threshold: float = 0.80,
    limit: int = 50,
) -> list[dict]:
    """Find duplicated knowledge items."""
    from agent_memory.services.governance import find_duplicates as _fd
    return await _fd(db, project_id, title_threshold, content_threshold, limit)


async def list_stale_knowledge(
    db: Database,
    project_id: str,
    max_age_days: int = 30,
    limit: int = 50,
) -> list[dict]:
    """List accepted knowledge items not updated within max_age_days."""
    from agent_memory.services.governance import list_stale_knowledge as _ls
    return await _ls(db, project_id, max_age_days, limit)


async def approve_and_supersede(
    db: Database,
    new_memory_id: str,
    old_memory_id: str,
    decided_by: str = "agent",
    reason: str = "",
) -> dict:
    """Mark old_memory_id superseded by new_memory_id."""
    from agent_memory.services.governance import approve_and_supersede as _as
    return await _as(db, new_memory_id, old_memory_id, decided_by, reason)


async def archive_knowledge(
    db: Database,
    memory_id: str,
    decided_by: str = "agent",
    reason: str = "",
) -> dict:
    """Archive a knowledge item (terminal state)."""
    from agent_memory.services.governance import archive_knowledge as _ak
    return await _ak(db, memory_id, decided_by, reason)


async def reject_knowledge(
    db: Database,
    memory_id: str,
    decided_by: str = "agent",
    reason: str = "",
) -> dict:
    """Reject a knowledge item (terminal state)."""
    from agent_memory.services.governance import reject_knowledge as _rk
    return await _rk(db, memory_id, decided_by, reason)


# ---------------------------------------------------------------------------
# Events (HTTP channel)
# ---------------------------------------------------------------------------


async def _capture_extracted_memories(db: Database, event: EventEnvelope) -> None:
    """Store an explicit extraction result as reviewable candidates.

    Lifecycle plugins do not infer memories; this only consumes structured
    results supplied by an agent. Replaying an event safely retries candidate
    storage because candidate insertion is idempotent by event ID and title.
    """
    if event.event_type != "memory.extraction_completed" or not event.project_id:
        return
    memories = event.payload.get("memories")
    if not isinstance(memories, list):
        return
    structured_memories = [memory for memory in memories if isinstance(memory, dict)]
    if structured_memories:
        await submit_memory_candidate(
            db,
            event.project_id,
            event.event_id,
            structured_memories,
            run_id=event.run_id,
        )


async def submit_event(db: Database, event: EventEnvelope) -> dict:
    """Persist a lifecycle event idempotently.

    Returns status: 'created' or 'duplicate'.
    """
    created = await repo.events.insert_event(db, event)
    await _capture_extracted_memories(db, event)
    return {
        "event_id": event.event_id,
        "status": "created" if created else "duplicate",
    }


async def submit_events_batch(db: Database, events: list[EventEnvelope]) -> dict:
    """Persist a batch of events. Per-event idempotency."""
    created = 0
    duplicates = 0
    for evt in events:
        was_new = await repo.events.insert_event(db, evt)
        await _capture_extracted_memories(db, evt)
        if was_new:
            created += 1
        else:
            duplicates += 1
    return {"created": created, "duplicates": duplicates, "total": len(events)}


async def submit_checkpoint(db: Database, checkpoint: Checkpoint) -> Checkpoint:
    """Persist a checkpoint."""
    return await repo.checkpoints.create_checkpoint(db, checkpoint)


# ---------------------------------------------------------------------------
# Search (Phase 4: hybrid FTS5 + vector RRF)
# ---------------------------------------------------------------------------

# Module-level reference to the SearchService, set by main.py at startup.
_search_service = None


def set_search_service(service) -> None:
    """Inject the SearchService built in main.py (used by MCP + HTTP)."""
    global _search_service
    _search_service = service


def get_search_service():
    return _search_service


async def search_memory(
    db: Database,
    project_id: str,
    query: str,
    limit: int = 8,
    filters: Optional[dict] = None,
) -> dict:
    """Hybrid search over the chunk index (FTS5 + optional vector RRF).

    Uses the injected SearchService when available. Falls back to Phase 2
    knowledge LIKE search when no index has been built yet.
    """
    status_filter = None
    if filters and "status" in filters:
        try:
            status_filter = KnowledgeStatus(filters["status"])
        except ValueError:
            status_filter = None

    svc = _search_service
    if svc is not None and getattr(svc, "has_index", False):
        return await svc.search(
            project_id=project_id,
            query=query,
            limit=limit,
            status=status_filter.value if status_filter else None,
        )

    # Phase 2 fallback: LIKE search over knowledge rows
    results = await repo.knowledge.list_knowledge_by_project(
        db,
        project_id,
        status=status_filter,
        limit=limit,
    )
    lower_query = query.lower()
    matched = [
        k for k in results
        if lower_query in k.title.lower() or lower_query in k.content.lower()
    ]
    return {
        "results": [k.model_dump() for k in matched[:limit]],
        "retrieval_mode": "lexical_basic",
    }


# ---------------------------------------------------------------------------
# Admin / candidates
# ---------------------------------------------------------------------------


async def list_pending_candidates(
    db: Database, project_id: Optional[str] = None, limit: int = 50
) -> list[dict]:
    """List pending memory candidates (admin channel)."""
    return await repo.knowledge.list_pending_candidates(
        db, project_id=project_id, limit=limit
    )


async def approve_candidate(
    db: Database,
    candidate_id: str,
    decided_by: str = "admin",
    auto_accept: bool = False,
) -> Optional[str]:
    """Approve a candidate; optionally auto-promote to accepted knowledge.

    Returns the new knowledge memory_id if auto_accept=True and promotion
    succeeded, otherwise None.
    """
    memory_id = await repo.knowledge.approve_candidate(
        db, candidate_id, decided_by=decided_by, auto_accept=auto_accept
    )
    if memory_id and _job_dispatcher is not None:
        record = await repo.knowledge.get_knowledge(db, memory_id)
        if record:
            _job_dispatcher.enqueue_index(memory_id, record["knowledge"]["project_id"])
    return memory_id


async def reject_candidate(
    db: Database,
    candidate_id: str,
    decided_by: str = "admin",
    reason: Optional[str] = None,
) -> bool:
    """Reject a candidate."""
    return await repo.knowledge.reject_candidate(
        db, candidate_id, decided_by=decided_by, reason=reason
    )


# ---------------------------------------------------------------------------
# Events read helpers
# ---------------------------------------------------------------------------


async def get_events_by_run(db: Database, run_id: str, limit: int = 100) -> list[dict]:
    """Read recent events for a run."""
    return await repo.events.get_events_by_run(db, run_id, limit=limit)
