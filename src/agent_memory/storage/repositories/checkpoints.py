"""Checkpoint repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from agent_memory.schemas import Checkpoint
from agent_memory.storage.database import Database


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


async def create_checkpoint(db: Database, cp: Checkpoint) -> Checkpoint:
    now = _utcnow()
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO checkpoints (checkpoint_id, run_id, source_revision, summary, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                cp.checkpoint_id,
                cp.run_id,
                cp.source_revision,
                cp.summary,
                now,
            ),
        )
        await conn.commit()
    return cp


async def get_checkpoint(db: Database, checkpoint_id: str) -> Optional[Checkpoint]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT checkpoint_id, run_id, source_revision, summary, created_at "
            "FROM checkpoints WHERE checkpoint_id = ?",
            (checkpoint_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return Checkpoint(
            checkpoint_id=row["checkpoint_id"],
            run_id=row["run_id"],
            source_revision=row["source_revision"],
            summary=row["summary"],
            created_at=row["created_at"],
        )


async def get_latest_checkpoint_by_run(
    db: Database, run_id: str
) -> Optional[Checkpoint]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT checkpoint_id, run_id, source_revision, summary, created_at "
            "FROM checkpoints WHERE run_id = ? ORDER BY created_at DESC LIMIT 1",
            (run_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return Checkpoint(
            checkpoint_id=row["checkpoint_id"],
            run_id=row["run_id"],
            source_revision=row["source_revision"],
            summary=row["summary"],
            created_at=row["created_at"],
        )


async def list_checkpoints_by_run(
    db: Database, run_id: str, limit: int = 20
) -> list[Checkpoint]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT checkpoint_id, run_id, source_revision, summary, created_at "
            "FROM checkpoints WHERE run_id = ? ORDER BY created_at DESC LIMIT ?",
            (run_id, limit),
        )
        rows = await cursor.fetchall()
        return [
            Checkpoint(
                checkpoint_id=r["checkpoint_id"],
                run_id=r["run_id"],
                source_revision=r["source_revision"],
                summary=r["summary"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
