"""Task repository with optimistic locking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from agent_memory.schemas import Task, TaskStatus
from agent_memory.storage.database import Database


class TaskConflictError(Exception):
    """Raised when a task update conflicts with a newer revision."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


async def create_task(db: Database, task: Task) -> Task:
    now = _utcnow()
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO tasks (task_id, project_id, title, status, revision, owner_session_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task.task_id,
                task.project_id,
                task.title,
                task.status.value,
                task.revision,
                task.owner_session_id,
                now,
                now,
            ),
        )
        await conn.commit()
    return task


async def get_task(db: Database, task_id: str) -> Optional[Task]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT task_id, project_id, title, status, revision, owner_session_id, created_at, updated_at "
            "FROM tasks WHERE task_id = ?",
            (task_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return Task(
            task_id=row["task_id"],
            project_id=row["project_id"],
            title=row["title"],
            status=TaskStatus(row["status"]),
            revision=row["revision"],
            owner_session_id=row["owner_session_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


async def update_task_status(
    db: Database,
    task_id: str,
    expected_revision: int,
    status: TaskStatus,
    owner_session_id: Optional[str] = None,
) -> Task:
    """Optimistic update: fails with TaskConflictError on revision mismatch."""
    now = _utcnow()
    async with db.connection() as conn:
        cursor = await conn.execute(
            "UPDATE tasks SET status = ?, revision = revision + 1, "
            "owner_session_id = COALESCE(?, owner_session_id), updated_at = ? "
            "WHERE task_id = ? AND revision = ?",
            (status.value, owner_session_id, now, task_id, expected_revision),
        )
        if cursor.rowcount == 0:
            await conn.rollback()
            # Determine why: not found or version conflict
            cur2 = await conn.execute(
                "SELECT revision FROM tasks WHERE task_id = ?", (task_id,)
            )
            row = await cur2.fetchone()
            if row is None:
                raise TaskConflictError(f"Task {task_id} not found")
            raise TaskConflictError(
                f"Task {task_id} revision conflict: expected {expected_revision}, "
                f"actual {row[0]}"
            )
        await conn.commit()
    return await get_task(db, task_id)  # type: ignore[arg-type]


async def list_tasks_by_project(
    db: Database, project_id: str, status: Optional[TaskStatus] = None, limit: int = 50
) -> list[Task]:
    sql = (
        "SELECT task_id, project_id, title, status, revision, owner_session_id, created_at, updated_at "
        "FROM tasks WHERE project_id = ?"
    )
    params: list = [project_id]
    if status:
        sql += " AND status = ?"
        params.append(status.value)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    async with db.connection() as conn:
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [
            Task(
                task_id=r["task_id"],
                project_id=r["project_id"],
                title=r["title"],
                status=TaskStatus(r["status"]),
                revision=r["revision"],
                owner_session_id=r["owner_session_id"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]
