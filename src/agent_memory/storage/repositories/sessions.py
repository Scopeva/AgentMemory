"""Session and run repositories."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from agent_memory.schemas import AgentType, Run, RunStatus, Session
from agent_memory.storage.database import Database


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


async def register_session(db: Database, session: Session) -> Session:
    now = _utcnow()
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO sessions (session_id, agent_type, native_session_id, workspace_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                session.session_id,
                session.agent_type.value,
                session.native_session_id,
                session.workspace_id,
                now,
            ),
        )
        await conn.commit()
    return session


async def get_session(db: Database, session_id: str) -> Optional[Session]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT session_id, agent_type, native_session_id, workspace_id, created_at "
            "FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return Session(
            session_id=row["session_id"],
            agent_type=AgentType(row["agent_type"]),
            native_session_id=row["native_session_id"],
            workspace_id=row["workspace_id"],
            created_at=row["created_at"],
        )


async def list_sessions_by_workspace(
    db: Database, workspace_id: str, limit: int = 50
) -> list[Session]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT session_id, agent_type, native_session_id, workspace_id, created_at "
            "FROM sessions WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?",
            (workspace_id, limit),
        )
        rows = await cursor.fetchall()
        return [
            Session(
                session_id=r["session_id"],
                agent_type=AgentType(r["agent_type"]),
                native_session_id=r["native_session_id"],
                workspace_id=r["workspace_id"],
                created_at=r["created_at"],
            )
            for r in rows
        ]


async def start_run(db: Database, run: Run) -> Run:
    now = _utcnow()
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO runs (run_id, task_id, session_id, status, head_sha_start, head_sha_end, started_at, ended_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run.run_id,
                run.task_id,
                run.session_id,
                run.status.value,
                run.head_sha_start,
                run.head_sha_end,
                now,
                None,
            ),
        )
        await conn.commit()
    return run


async def end_run(
    db: Database,
    run_id: str,
    status: RunStatus,
    head_sha_end: Optional[str] = None,
) -> Optional[Run]:
    now = _utcnow()
    async with db.connection() as conn:
        await conn.execute(
            "UPDATE runs SET status = ?, head_sha_end = ?, ended_at = ? WHERE run_id = ?",
            (status.value, head_sha_end, now, run_id),
        )
        await conn.commit()
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT run_id, task_id, session_id, status, head_sha_start, head_sha_end, started_at, ended_at "
            "FROM runs WHERE run_id = ?",
            (run_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return Run(
            run_id=row["run_id"],
            task_id=row["task_id"],
            session_id=row["session_id"],
            status=RunStatus(row["status"]),
            head_sha_start=row["head_sha_start"],
            head_sha_end=row["head_sha_end"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )


async def get_run(db: Database, run_id: str) -> Optional[Run]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT run_id, task_id, session_id, status, head_sha_start, head_sha_end, started_at, ended_at "
            "FROM runs WHERE run_id = ?",
            (run_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return Run(
            run_id=row["run_id"],
            task_id=row["task_id"],
            session_id=row["session_id"],
            status=RunStatus(row["status"]),
            head_sha_start=row["head_sha_start"],
            head_sha_end=row["head_sha_end"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )


async def list_runs_by_task(
    db: Database, task_id: str, limit: int = 20
) -> list[Run]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT run_id, task_id, session_id, status, head_sha_start, head_sha_end, started_at, ended_at "
            "FROM runs WHERE task_id = ? ORDER BY started_at DESC LIMIT ?",
            (task_id, limit),
        )
        rows = await cursor.fetchall()
        return [
            Run(
                run_id=r["run_id"],
                task_id=r["task_id"],
                session_id=r["session_id"],
                status=RunStatus(r["status"]),
                head_sha_start=r["head_sha_start"],
                head_sha_end=r["head_sha_end"],
                started_at=r["started_at"],
                ended_at=r["ended_at"],
            )
            for r in rows
        ]
