"""Project, repository, and workspace repositories."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from agent_memory.schemas import Project, Repository, Workspace
from agent_memory.storage.database import Database


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


async def register_project(db: Database, project: Project) -> Project:
    now = _utcnow()
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO projects (project_id, name, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (project.project_id, project.name, project.status.value, now, now),
        )
        await conn.commit()
    return project


async def get_project(db: Database, project_id: str) -> Optional[Project]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT project_id, name, status, created_at, updated_at "
            "FROM projects WHERE project_id = ?",
            (project_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return Project(
            project_id=row["project_id"],
            name=row["name"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


async def list_projects(db: Database, status: Optional[str] = None) -> list[Project]:
    sql = "SELECT project_id, name, status, created_at, updated_at FROM projects"
    params: tuple = ()
    if status:
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY created_at DESC"
    async with db.connection() as conn:
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [
            Project(
                project_id=r["project_id"],
                name=r["name"],
                status=r["status"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]


async def register_repository(db: Database, repo: Repository) -> Repository:
    now = _utcnow()
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO repositories (repository_id, project_id, remote_url_hash, root_fingerprint, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                repo.repository_id,
                repo.project_id,
                repo.remote_url_hash,
                repo.root_fingerprint,
                now,
            ),
        )
        await conn.commit()
    return repo


async def get_repository_by_fingerprint(
    db: Database, project_id: str, root_fingerprint: str
) -> Optional[Repository]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT repository_id, project_id, remote_url_hash, root_fingerprint, created_at "
            "FROM repositories WHERE project_id = ? AND root_fingerprint = ?",
            (project_id, root_fingerprint),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return Repository(
            repository_id=row["repository_id"],
            project_id=row["project_id"],
            remote_url_hash=row["remote_url_hash"],
            root_fingerprint=row["root_fingerprint"],
            created_at=row["created_at"],
        )


async def register_workspace(db: Database, ws: Workspace) -> Workspace:
    now = _utcnow()
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO workspaces (workspace_id, repository_id, canonical_path, worktree_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                ws.workspace_id,
                ws.repository_id,
                ws.canonical_path,
                ws.worktree_id,
                now,
            ),
        )
        await conn.commit()
    return ws


async def get_workspace_by_path(
    db: Database, canonical_path: str
) -> Optional[Workspace]:
    """Find workspace by canonical path (used for project resolution)."""
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT w.workspace_id, w.repository_id, w.canonical_path, w.worktree_id, w.created_at "
            "FROM workspaces w WHERE w.canonical_path = ?",
            (canonical_path,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return Workspace(
            workspace_id=row["workspace_id"],
            repository_id=row["repository_id"],
            canonical_path=row["canonical_path"],
            worktree_id=row["worktree_id"],
            created_at=row["created_at"],
        )
