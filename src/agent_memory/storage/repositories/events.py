"""Event repository with idempotent deduplication."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import json

from agent_memory.schemas import EventEnvelope
from agent_memory.storage.database import Database


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


async def insert_event(db: Database, event: EventEnvelope) -> bool:
    """Insert event idempotently. Returns True if newly inserted, False if duplicate."""
    now = _utcnow()
    async with db.connection() as conn:
        # Lifecycle clients only know their own IDs. Materialize the required
        # relational parents here so a first event can be accepted directly.
        if event.project_id:
            cursor = await conn.execute(
                "SELECT 1 FROM projects WHERE project_id = ?", (event.project_id,)
            )
            if not await cursor.fetchone():
                await conn.execute(
                    "INSERT OR IGNORE INTO projects "
                    "(project_id, name, status, created_at, updated_at) "
                    "VALUES (?, ?, 'active', ?, ?)",
                    (event.project_id, event.project_id, now, now),
                )
        task_id = event.task_id
        if task_id and event.project_id:
            await conn.execute(
                "INSERT OR IGNORE INTO tasks "
                "(task_id, project_id, title, status, revision, created_at, updated_at) "
                "VALUES (?, ?, ?, 'pending', 1, ?, ?)",
                (task_id, event.project_id, task_id, now, now),
            )
        elif task_id:
            task_id = None
        await conn.execute(
            "INSERT OR IGNORE INTO sessions "
            "(session_id, agent_type, native_session_id, workspace_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                event.session_id,
                event.agent.value,
                event.payload.get("native_session_id", event.session_id),
                event.workspace_id,
                now,
            ),
        )
        await conn.execute(
            "INSERT OR IGNORE INTO runs "
            "(run_id, task_id, session_id, status, started_at, project_id) "
            "VALUES (?, ?, ?, 'running', ?, ?)",
            (event.run_id, task_id, event.session_id, now, event.project_id),
        )
        if event.event_type in {"run.settled", "run.interrupted"}:
            outcome = event.payload.get("outcome", "interrupted")
            status = outcome if outcome in {"completed", "failed", "cancelled", "interrupted"} else "interrupted"
            await conn.execute(
                "UPDATE runs SET status = ?, ended_at = ? WHERE run_id = ?",
                (status, now, event.run_id),
            )
        # Check by event_id (idempotency key)
        cursor = await conn.execute(
            "SELECT 1 FROM events WHERE event_id = ?", (event.event_id,)
        )
        if await cursor.fetchone():
            return False
        # Check by (run_id, sequence_no) natural key
        if event.sequence_no is not None:
            cursor = await conn.execute(
                "SELECT 1 FROM events WHERE run_id = ? AND sequence_no = ?",
                (event.run_id, event.sequence_no),
            )
            if await cursor.fetchone():
                return False
        await conn.execute(
            "INSERT INTO events "
            "(event_id, run_id, event_type, sequence_no, payload_json, created_at, project_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.run_id,
                event.event_type,
                event.sequence_no,
                json.dumps(event.payload, ensure_ascii=False),
                now,
                event.project_id,
            ),
        )
        await conn.commit()
        return True


def _row_to_dict(r) -> dict:
    try:
        payload = json.loads(r["payload_json"])
    except (TypeError, json.JSONDecodeError):
        payload = {}
    return {
        "event_id": r["event_id"],
        "run_id": r["run_id"],
        "event_type": r["event_type"],
        "sequence_no": r["sequence_no"],
        "project_id": r["project_id"] if "project_id" in r.keys() else None,
        "payload": payload,
        "created_at": r["created_at"],
    }


async def get_events_by_run(
    db: Database, run_id: str, limit: int = 100
) -> list[dict]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT event_id, run_id, event_type, sequence_no, payload_json, created_at, project_id "
            "FROM events WHERE run_id = ? ORDER BY sequence_no ASC, created_at ASC LIMIT ?",
            (run_id, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


async def get_events_by_project(
    db: Database, project_id: str, limit: int = 100
) -> list[dict]:
    """Return events belonging to a specific project, newest first."""
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT event_id, run_id, event_type, sequence_no, payload_json, created_at, project_id "
            "FROM events WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
            (project_id, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


async def get_event(db: Database, event_id: str) -> Optional[dict]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT event_id, run_id, event_type, sequence_no, payload_json, created_at, project_id "
            "FROM events WHERE event_id = ?",
            (event_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return _row_to_dict(row)


async def get_events_by_type(
    db: Database, event_type: str, limit: int = 50
) -> list[dict]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT event_id, run_id, event_type, sequence_no, payload_json, created_at, project_id "
            "FROM events WHERE event_type = ? ORDER BY created_at DESC LIMIT ?",
            (event_type, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]
