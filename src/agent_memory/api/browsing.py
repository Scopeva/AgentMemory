"""Browser-facing GET endpoints for the web dashboard.

Mounted at /v1 (same prefix as events/retrieval routers).
Read endpoints are open; DELETE /projects/{id} is admin-gated.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter(prefix="/v1")


def _repos():
    from agent_memory.storage import repositories
    return repositories


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@router.get("/projects")
async def list_projects(request: Request) -> dict:
    """List all registered projects."""
    from agent_memory.storage.repositories import projects as repo

    db = request.app.state.db
    items = await repo.list_projects(db)
    return {"items": [_project_to_dict(p) for p in items]}


@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: str) -> dict:
    """Return a single project by ID.

    Lenient: an unknown project_id still returns a 200 shell so dashboard
    sub-panels (events/runs/...) can render their own "no data" state
    instead of a 404. Register it via POST /v1/projects/register to make
    it a first-class project.
    """
    from agent_memory.storage.repositories import projects as repo

    db = request.app.state.db
    p = await repo.get_project(db, project_id)
    if p is None:
        return {
            "project_id": project_id,
            "name": project_id,
            "status": "unregistered",
            "created_at": None,
            "updated_at": None,
        }
    return _project_to_dict(p)


@router.post("/projects/register", status_code=201)
async def register_project(request: Request, payload: dict) -> dict:
    """Register a project so agent events / knowledge can reference it.

    Body: {"project_id": "demo", "name": "Demo project"}  (name optional).
    Idempotent: re-registering the same project_id updates nothing
    (already-exists → 409 with the existing record).
    """
    from agent_memory.schemas import Project
    from agent_memory.storage.repositories import projects as repo

    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")

    db = request.app.state.db
    existing = await repo.get_project(db, project_id)
    if existing is not None:
        return {"project_id": project_id, "action": "exists", **_project_to_dict(existing)}

    p = Project(project_id=project_id, name=payload.get("name") or project_id)
    p = await repo.register_project(db, p)
    return {"project_id": project_id, "action": "registered", **_project_to_dict(p)}


def _project_to_dict(p) -> dict:
    return {
        "project_id": p.project_id,
        "name": getattr(p, "name", None) or p.project_id,
        "status": getattr(p, "status", "active"),
        "created_at": getattr(p, "created_at", None),
        "updated_at": getattr(p, "updated_at", None),
    }


# ---------------------------------------------------------------------------
# Project deletion (admin)
# ---------------------------------------------------------------------------


def _check_admin(request: Request, token: Optional[str]) -> None:
    """Verify admin token against the configured env var (mirrors retrieval._check_admin)."""
    import os

    config = getattr(request.app.state, "config", None)
    env_name = config.security.admin_token_env if config else "AGENT_MEMORY_ADMIN_TOKEN"
    expected = os.environ.get(env_name)
    if expected and token != expected:
        raise HTTPException(403, "invalid admin token")


@router.delete("/projects/{project_id}")
async def delete_project(
    request: Request,
    project_id: str,
    x_admin_token: Optional[str] = Header(default=None),
) -> dict:
    """Cascade-delete a project and all of its data.

    Requires admin token (X-Admin-Token header). Deletes, in FK order:
      events, checkpoints, runs, handoffs, tasks,
      knowledge_revisions, knowledge, index_jobs, FTS/vector index
      entries, sessions referenced only by this project's runs,
      finally the project row itself.
    """
    from agent_memory.storage.repositories import projects as repo

    _check_admin(request, x_admin_token)
    db = request.app.state.db
    existing = await repo.get_project(db, project_id)
    if existing is None:
        raise HTTPException(404, f"project {project_id!r} not found")

    async with db.connection() as conn:
        deleted: dict[str, int] = {}

        # 1. events + checkpoints (via this project's runs)
        for table in ("events", "checkpoints"):
            cursor = await conn.execute(
                f"DELETE FROM {table} WHERE run_id IN "
                f"(SELECT run_id FROM runs WHERE project_id = ?)",
                (project_id,),
            )
            deleted[table] = cursor.rowcount or 0

        # 2. runs
        cursor = await conn.execute("DELETE FROM runs WHERE project_id = ?", (project_id,))
        deleted["runs"] = cursor.rowcount or 0

        # 3. handoffs + tasks
        for table in ("handoffs", "tasks"):
            cursor = await conn.execute("DELETE FROM " + table + " WHERE project_id = ?", (project_id,))
            deleted[table] = cursor.rowcount or 0

        # 4. knowledge + revisions
        cursor = await conn.execute("DELETE FROM knowledge_revisions WHERE project_id = ?", (project_id,))
        deleted["knowledge_revisions"] = cursor.rowcount or 0

        mem_ids = [
            r[0]
            for r in await (
                await conn.execute(
                    "SELECT memory_id FROM knowledge WHERE project_id = ?", (project_id,)
                )
            ).fetchall()
        ]
        cursor = await conn.execute("DELETE FROM knowledge WHERE project_id = ?", (project_id,))
        deleted["knowledge"] = cursor.rowcount or 0

        # 5. index jobs + FTS/vector index entries
        cursor = await conn.execute("DELETE FROM index_jobs WHERE project_id = ?", (project_id,))
        deleted["index_jobs"] = cursor.rowcount or 0

        # chunks_fts carries its own project_id column — scoped delete.
        cursor = await conn.execute("DELETE FROM chunks_fts WHERE project_id = ?", (project_id,))
        deleted["fts_chunks"] = cursor.rowcount or 0

        # memory_vectors is a vec0 virtual table — only present when the
        # sqlite-vec extension is loaded at runtime.
        try:
            cursor = await conn.execute(
                "SELECT 1 FROM memory_vectors LIMIT 1"
            )
            await cursor.fetchone()
            for mid in mem_ids:
                cursor = await conn.execute(
                    "DELETE FROM memory_vectors WHERE memory_id = ?", (mid,)
                )
            deleted["memory_vectors"] = len(mem_ids)
        except Exception:
            pass  # vec not loaded — nothing to clean

        # 6. sessions referenced ONLY by this project's runs are already
        #    deleted above; sessions are not project-scoped — keep them.
        #    (Runs are the project-scoped boundary; a session may span projects.)

        # 7. the project row itself
        cursor = await conn.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
        deleted["projects"] = cursor.rowcount or 0

        await conn.commit()

    return {"project_id": project_id, "deleted": deleted, "removed": any(v for v in deleted.values() if v)}


# ---------------------------------------------------------------------------
# Events (per project)
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/events")
async def list_events(
    request: Request,
    project_id: str,
    limit: int = 50,
    event_type: Optional[str] = None,
) -> dict:
    """List recent events for a project, newest first."""
    from agent_memory.storage.repositories import events as repo

    db = request.app.state.db
    if event_type:
        items = await repo.get_events_by_type(db, event_type, limit=limit)
        items = [e for e in items if e.get("project_id") == project_id]
    else:
        items = await repo.get_events_by_project(db, project_id, limit=limit)
    return {"items": items, "count": len(items)}


# ---------------------------------------------------------------------------
# Runs (per project)
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/runs")
async def list_runs(request: Request, project_id: str, limit: int = 50) -> dict:
    """List recent runs for a project, newest first.

    Migration 003 adds project_id to the runs table; we filter directly.
    """
    from agent_memory.storage.database import _query

    db = request.app.state.db
    items = await _query(
        db,
        "SELECT run_id, task_id, session_id, status, head_sha_start, "
        "head_sha_end, started_at, ended_at, project_id "
        "FROM runs WHERE project_id = ? ORDER BY started_at DESC LIMIT ?",
        (project_id, limit),
    )
    return {"items": items, "count": len(items)}


# ---------------------------------------------------------------------------
# Tasks (per project)
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/tasks")
async def list_tasks(
    request: Request,
    project_id: str,
    status: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """List tasks for a project, newest first."""
    from agent_memory.storage.repositories import tasks as repo
    from agent_memory.schemas import TaskStatus

    db = request.app.state.db
    status_enum = TaskStatus(status) if status else None
    items = await repo.list_tasks_by_project(db, project_id, status=status_enum, limit=limit)
    return {
        "items": [
            {
                "task_id": t.task_id,
                "project_id": t.project_id,
                "title": t.title,
                "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                "owner_session_id": getattr(t, "owner_session_id", None),
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in items
        ],
        "count": len(items),
    }


# ---------------------------------------------------------------------------
# Handoffs (per project, via tasks)
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/handoffs")
async def list_handoffs(request: Request, project_id: str, limit: int = 20) -> dict:
    """List handoffs for a project.

    Handoffs are keyed by task; we first fetch the project's tasks,
    then collect handoffs for each task.
    """
    from agent_memory.storage.repositories import tasks as tasks_repo
    from agent_memory.storage.repositories import handoffs as handoffs_repo

    db = request.app.state.db
    task_list = await tasks_repo.list_tasks_by_project(db, project_id, limit=100)
    all_handoffs = []
    for task in task_list:
        hs = await handoffs_repo.list_handoffs_by_task(db, task.task_id, limit=limit)
        all_handoffs.extend(hs)

    return {
        "items": [
            {
                "handoff_id": h.handoff_id,
                "task_id": h.task_id,
                "source_agent": h.source_agent,
                "state": h.state,
                "summary": h.summary,
                "completed": h.completed,
                "pending": h.pending,
                "blockers": h.blockers,
                "decisions": h.decisions,
                "created_at": getattr(h, "created_at", None),
            }
            for h in all_handoffs
        ],
        "count": len(all_handoffs),
    }


# ---------------------------------------------------------------------------
# Knowledge (per project)
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/knowledge")
async def list_knowledge(
    request: Request,
    project_id: str,
    status: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """List knowledge items for a project, newest first."""
    from agent_memory.storage.repositories import knowledge as repo
    from agent_memory.schemas import KnowledgeStatus

    db = request.app.state.db
    status_enum = KnowledgeStatus(status) if status else None
    items = await repo.list_knowledge_by_project(
        db, project_id, status=status_enum, limit=limit
    )
    return {
        "items": [
            {
                "memory_id": k.memory_id,
                "project_id": k.project_id,
                "type": k.type,
                "title": k.title,
                "content": k.content,
                "status": k.status.value if hasattr(k.status, "value") else str(k.status),
                "revision": k.revision,
                "created_at": k.created_at,
                "updated_at": k.updated_at,
            }
            for k in items
        ],
        "count": len(items),
    }


# ---------------------------------------------------------------------------
# Search alias (dashboard calls /v1/retrieval/search)
# ---------------------------------------------------------------------------


@router.get("/retrieval/search")
async def retrieval_search_alias(
    request: Request,
    project_id: str,
    query: str,
    limit: int = 8,
    status: Optional[str] = None,
) -> dict:
    """Alias for /v1/search so the dashboard's /v1/retrieval/search works."""
    db = request.app.state.db
    from agent_memory.services import core

    filters = {"status": status} if status else None
    return await core.search_memory(db, project_id, query, limit=limit, filters=filters)
