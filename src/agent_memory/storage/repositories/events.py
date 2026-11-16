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
            "INSERT INTO events (event_id, run_id, event_type, sequence_no, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.run_id,
                event.event_type,
                event.sequence_no,
                json.dumps(event.payload, ensure_ascii=False),
                now,
            ),
        )
        await conn.commit()
        return True


async def get_events_by_run(
    db: Database, run_id: str, limit: int = 100
) -> list[dict]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT event_id, run_id, event_type, sequence_no, payload_json, created_at "
            "FROM events WHERE run_id = ? ORDER BY sequence_no ASC, created_at ASC LIMIT ?",
            (run_id, limit),
        )
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            try:
                payload = json.loads(r["payload_json"])
            except (TypeError, json.JSONDecodeError):
                payload = {}
            results.append(
                {
                    "event_id": r["event_id"],
                    "run_id": r["run_id"],
                    "event_type": r["event_type"],
                    "sequence_no": r["sequence_no"],
                    "payload": payload,
                    "created_at": r["created_at"],
                }
            )
        return results


async def get_event(db: Database, event_id: str) -> Optional[dict]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT event_id, run_id, event_type, sequence_no, payload_json, created_at "
            "FROM events WHERE event_id = ?",
            (event_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        return {
            "event_id": row["event_id"],
            "run_id": row["run_id"],
            "event_type": row["event_type"],
            "sequence_no": row["sequence_no"],
            "payload": payload,
            "created_at": row["created_at"],
        }


async def get_events_by_type(
    db: Database, event_type: str, limit: int = 50
) -> list[dict]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT event_id, run_id, event_type, sequence_no, payload_json, created_at "
            "FROM events WHERE event_type = ? ORDER BY created_at DESC LIMIT ?",
            (event_type, limit),
        )
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            try:
                payload = json.loads(r["payload_json"])
            except (TypeError, json.JSONDecodeError):
                payload = {}
            results.append(
                {
                    "event_id": r["event_id"],
                    "run_id": r["run_id"],
                    "event_type": r["event_type"],
                    "sequence_no": r["sequence_no"],
                    "payload": payload,
                    "created_at": r["created_at"],
                }
            )
        return results
