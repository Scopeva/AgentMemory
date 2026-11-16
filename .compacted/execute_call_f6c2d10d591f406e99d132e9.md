CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    payload_json TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT
);

CREATE INDEX idx_jobs_status ON jobs(status, updated_at);

CREATE TABLE IF NOT EXISTS outbox (
    outbox_id TEXT PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT
);

CREATE INDEX idx_outbox_unpublished ON outbox(published_at) WHERE published_at IS NULL;

-- FTS5 virtual table for lexical search (materialized later from knowledge).
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    memory_id UNINDEXED,
    title,
    content,
    tokenize = "unicode61"
);

-- sqlite-vec virtual table; dimension must match embedding config (1024).
-- Create only if sqlite-vec extension is available; Phase 1 does not require it.
-- CREATE VIRTUAL TABLE IF NOT EXISTS memory_vectors USING vec0(
--     memory_id TEXT,
--     chunk_id TEXT,
--     embedding FLOAT[1024]
-- );
---CORE---
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


async def submit_memory_candidate(
    db: Database,
    project_id: str,
    idempotency_key: str,
    memories: list[dict],
    run_id: Optional[str] = None,
) -> dict:
    """Submit memory candidates. Idempotent per key; one candidate per memory."""
    inserted: list[str] = []
    duplicates = 0
    for memory in memories:
        new = await repo.knowledge.insert_memory_candidate(
            db, project_id, run_id, idempotency_key=f"{idempotency_key}:{memory.get('title','')}",
            memory_json=memory,
        )
        if new:
            inserted.append(str(memory.get("memory_id", "")))
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
# Events (HTTP channel)
# ---------------------------------------------------------------------------


async def submit_event(db: Database, event: EventEnvelope) -> dict:
    """Persist a lifecycle event idempotently.

    Returns status: 'created' or 'duplicate'.
    """
    created = await repo.events.insert_event(db, event)
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
        if was_new:
            created += 1
        else:
            duplicates += 1
    return {"created": created, "duplicates": duplicates, "total": len(events)}


async def submit_checkpoint(db: Database, checkpoint: Checkpoint) -> Checkpoint:
    """Persist a checkpoint."""
    return await repo.checkpoints.create_checkpoint(db, checkpoint)


# ---------------------------------------------------------------------------
# Search (Phase 4 will upgrade to hybrid)
# ---------------------------------------------------------------------------


async def search_memory(
    db: Database,
    project_id: str,

... [truncated, showing 200/283 lines, 6493/9009 chars]