"""FastAPI HTTP API for hook events, checkpoints, and admin operations.

This is the event channel: agent adapters call these endpoints to
persist lifecycle events. MCP tools are the agent-facing query channel.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from agent_memory.schemas import Checkpoint, EventEnvelope
from agent_memory.services import core
from agent_memory.storage.database import Database


class EventBatchRequest(BaseModel):
    events: list[EventEnvelope]


class EventResponse(BaseModel):
    event_id: str
    status: str  # "created" | "duplicate"


class BatchEventResponse(BaseModel):
    created: int
    duplicates: int
    total: int


class CheckpointRequest(BaseModel):
    checkpoint: Checkpoint


class CheckpointResponse(BaseModel):
    checkpoint: Checkpoint


def get_db(request: Request) -> Database:
    """FastAPI dependency that returns the bound Database."""
    return request.app.state.db


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

router = APIRouter()


@router.get("/health/live")
async def health_live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(db: Database = Depends(get_db)) -> dict:
    # A basic readiness check: can we read the schema?
    async with db.connection() as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM schema_migrations")
        row = await cursor.fetchone()
        migrations = row[0] if row else 0
    return {"status": "ok", "migrations_applied": migrations}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


@router.post("/v1/events", response_model=EventResponse, status_code=status.HTTP_202_ACCEPTED)
async def post_event(
    event: EventEnvelope,
    db: Database = Depends(get_db),
) -> dict:
    """Persist a single lifecycle event idempotently."""
    return await core.submit_event(db, event)


@router.post(
    "/v1/events/batch",
    response_model=BatchEventResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_events_batch(
    batch: EventBatchRequest,
    db: Database = Depends(get_db),
) -> dict:
    """Persist a batch of lifecycle events."""
    return await core.submit_events_batch(db, batch.events)


@router.post("/v1/checkpoints", response_model=CheckpointResponse, status_code=status.HTTP_202_ACCEPTED)
async def post_checkpoint(
    body: CheckpointRequest,
    db: Database = Depends(get_db),
) -> dict:
    """Persist a checkpoint for a run."""
    cp = await core.submit_checkpoint(db, body.checkpoint)
    return {"checkpoint": cp}


@router.get("/v1/runs/{run_id}")
async def get_run_state(
    run_id: str,
    db: Database = Depends(get_db),
) -> dict:
    """Query run state and recent events."""
    events = await core.get_events_by_run(db, run_id, limit=20)
    return {"run_id": run_id, "events": events}


@router.get("/v1/jobs/{job_id}")
async def get_job_state(
    job_id: str,
    db: Database = Depends(get_db),
) -> dict:
    """Placeholder: query background job status (implemented in Phase 4+)."""
    raise HTTPException(status_code=404, detail="Jobs API not yet implemented")


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

admin_router = APIRouter(prefix="/v1/admin")


@admin_router.get("/pending")
async def list_pending(
    project_id: Optional[str] = None,
    limit: int = 50,
    db: Database = Depends(get_db),
) -> dict:
    """List pending memory candidates."""
    results = await core.list_pending_candidates(db, project_id=project_id, limit=limit)
    return {"candidates": results}


@admin_router.post("/approvals/{candidate_id}/approve")
async def approve_candidate(
    candidate_id: str,
    decided_by: str = "admin",
    auto_accept: bool = False,
    db: Database = Depends(get_db),
) -> dict:
    """Approve a memory candidate; optionally auto-promote to accepted knowledge."""
    memory_id = await core.approve_candidate(
        db, candidate_id, decided_by=decided_by, auto_accept=auto_accept
    )
    return {"candidate_id": candidate_id, "memory_id": memory_id}


@admin_router.post("/approvals/{candidate_id}/reject")
async def reject_candidate(
    candidate_id: str,
    decided_by: str = "admin",
    reason: Optional[str] = None,
    db: Database = Depends(get_db),
) -> dict:
    """Reject a memory candidate."""
    rejected = await core.reject_candidate(
        db, candidate_id, decided_by=decided_by, reason=reason
    )
    return {"candidate_id": candidate_id, "rejected": rejected}


@admin_router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: str,
    db: Database = Depends(get_db),
) -> dict:
    raise HTTPException(status_code=404, detail="Jobs retry not yet implemented")
