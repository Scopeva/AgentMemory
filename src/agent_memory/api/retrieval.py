"""HTTP + admin endpoints: expose Phase 4 retrieval ops.

Additive module mounted by ``create_app``; does not disturb Phase 2 routers.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from agent_memory.api.admin import require_admin
from agent_memory.schemas import Knowledge, KnowledgeStatus
from agent_memory.services import core

router = APIRouter(prefix="/v1")
admin_router = APIRouter(prefix="/v1/admin")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@router.get("/search")
async def search(
    request: Request,
    project_id: str,
    query: str,
    limit: int = 8,
    status: Optional[str] = None,
) -> dict:
    """Hybrid search over the project knowledge index."""
    if not query.strip():
        raise HTTPException(422, "query must not be blank")
    db = request.app.state.db
    filters = {"status": status} if status else None
    return await core.search_memory(db, project_id, query, limit=limit, filters=filters)


# ---------------------------------------------------------------------------
# Knowledge write (indexes on submit)
# ---------------------------------------------------------------------------


@router.post("/knowledge")
async def create_knowledge(
    request: Request,
    payload: dict,
) -> dict:
    """Create or update a knowledge row and enqueue its index job.

    Accepts: project_id, type, title, content, scope?, status?,
    current_source_revision?, supersedes_memory_id?, memory_id? (for update).
    """
    db = request.app.state.db
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")

    memory_id = payload.get("memory_id")
    if memory_id:
        # Update path: use optimistic revision
        expected_rev = payload.get("revision")
        if expected_rev is None:
            raise HTTPException(400, "revision required for update")
        from agent_memory.storage import repositories as repo

        try:
            k = await repo.knowledge.update_knowledge(
                db,
                memory_id,
                expected_rev,
                title=payload.get("title"),
                content=payload.get("content"),
                status=KnowledgeStatus(payload["status"]) if payload.get("status") else None,
            )
        except Exception as exc:
            raise HTTPException(409, f"knowledge update failed: {exc}")

        dispatcher = getattr(request.app.state, "job_dispatcher", None)
        if dispatcher:
            dispatcher.enqueue_index(memory_id, project_id)
        return {"memory_id": memory_id, "revision": k.revision, "action": "updated"}

    # Create path
    k = Knowledge(
        project_id=project_id,
        type=payload.get("type", "note"),
        title=payload.get("title", ""),
        content=payload.get("content", ""),
        scope=payload.get("scope", "project"),
        status=KnowledgeStatus(payload.get("status", "accepted")),
        current_source_revision=payload.get("current_source_revision"),
        supersedes_memory_id=payload.get("supersedes_memory_id"),
    )
    from agent_memory.storage import repositories as repo

    k = await repo.knowledge.create_knowledge(db, k)
    dispatcher = getattr(request.app.state, "job_dispatcher", None)
    if dispatcher:
        dispatcher.enqueue_index(k.memory_id, project_id)
    return {"memory_id": k.memory_id, "revision": k.revision, "action": "created"}


@router.delete("/knowledge/{memory_id}")
async def delete_knowledge(
    request: Request,
    memory_id: str,
    _: None = Depends(require_admin),
) -> dict:
    """Mark a knowledge row archived and enqueue its index delete job."""
    db = request.app.state.db
    from agent_memory.storage import repositories as repo

    revision = int(request.query_params.get("revision", 1))
    updated = await repo.knowledge.update_knowledge(
        db,
        memory_id,
        expected_revision=revision,
        status=KnowledgeStatus.ARCHIVED,
        changed_by="admin",
    )
    if updated is None:
        raise HTTPException(404, f"knowledge {memory_id} not found")

    dispatcher = getattr(request.app.state, "job_dispatcher", None)
    if dispatcher:
        dispatcher.enqueue_delete(memory_id, updated.project_id)
    return {"memory_id": memory_id, "status": "archived"}


# ---------------------------------------------------------------------------
# Admin: drain index jobs
# ---------------------------------------------------------------------------


@admin_router.post("/index/drain")
async def drain_index(
    request: Request,
    batch_size: int = 100,
    _: None = Depends(require_admin),
) -> dict:
    """Drain pending index jobs. Requires admin token."""
    dispatcher = getattr(request.app.state, "job_dispatcher", None)
    if dispatcher is None:
        return {"drained": 0, "reason": "indexing disabled"}
    result = await dispatcher.drain(batch_size=batch_size)
    return {"drained": result["completed"], **result}


@admin_router.get("/index/status")
async def index_status(
    request: Request,
    _: None = Depends(require_admin),
) -> dict:
    """Report pending index jobs + vector availability."""
    dispatcher = getattr(request.app.state, "job_dispatcher", None)
    pending = dispatcher.pending_count() if dispatcher else 0
    worker = getattr(request.app.state, "indexing_worker", None)
    vector = worker.vector if worker is not None else None

    return {
        "pending_index_jobs": pending,
        "vector_available": bool(vector and vector.available),
    }
