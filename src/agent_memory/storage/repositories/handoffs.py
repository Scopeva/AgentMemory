"""Handoff repository with versioned records per task."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from agent_memory.schemas import Handoff
from agent_memory.storage.database import Database


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _to_json_list(lst: list[str]) -> str:
    return json.dumps(lst, ensure_ascii=False)


def _from_json_list(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


async def create_handoff(db: Database, h: Handoff) -> Handoff:
    now = _utcnow()
    handoff_id = h.handoff_id or str(uuid.uuid4())
    h.handoff_id = handoff_id
    async with db.connection() as conn:
        # Determine next revision for this task
        cursor = await conn.execute(
            "SELECT COALESCE(MAX(revision), 0) FROM handoffs WHERE task_id = ?",
            (h.task_id,),
        )
        row = await cursor.fetchone()
        next_revision = (row[0] or 0) + 1
        h.revision = next_revision

        await conn.execute(
            "INSERT INTO handoffs ("
            "handoff_id, task_id, source_agent, source_session_id, source_run_id, "
            "source_workspace_id, source_head_sha, state, summary, "
            "completed_json, pending_json, blockers_json, decisions_json, "
            "verification_refs_json, next_actions_json, revision, is_stale, "
            "created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                handoff_id,
                h.task_id,
                h.source_agent,
                h.source_session_id,
                h.source_run_id,
                h.source_workspace_id,
                h.source_head_sha,
                h.state,
                h.summary,
                _to_json_list(h.completed),
                _to_json_list(h.pending),
                _to_json_list(h.blockers),
                _to_json_list(h.decisions),
                _to_json_list(h.verification_refs),
                _to_json_list(h.next_actions),
                next_revision,
                0,
                now,
                now,
            ),
        )
        await conn.commit()
    return h


async def get_latest_handoff(
    db: Database,
    task_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> Optional[Handoff]:
    async with db.connection() as conn:
        if task_id:
            cursor = await conn.execute(
                "SELECT * FROM handoffs WHERE task_id = ? AND is_stale = 0 "
                "ORDER BY revision DESC LIMIT 1",
                (task_id,),
            )
        elif workspace_id:
            cursor = await conn.execute(
                "SELECT * FROM handoffs WHERE source_workspace_id = ? AND is_stale = 0 "
                "ORDER BY created_at DESC LIMIT 1",
                (workspace_id,),
            )
        else:
            return None
        row = await cursor.fetchone()
        if not row:
            return None
        return Handoff(
            handoff_id=row["handoff_id"],
            task_id=row["task_id"],
            source_agent=row["source_agent"],
            source_session_id=row["source_session_id"],
            source_run_id=row["source_run_id"],
            source_workspace_id=row["source_workspace_id"],
            source_head_sha=row["source_head_sha"],
            state=row["state"],
            summary=row["summary"],
            completed=_from_json_list(row["completed_json"]),
            pending=_from_json_list(row["pending_json"]),
            blockers=_from_json_list(row["blockers_json"]),
            decisions=_from_json_list(row["decisions_json"]),
            verification_refs=_from_json_list(row["verification_refs_json"]),
            next_actions=_from_json_list(row["next_actions_json"]),
            revision=row["revision"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


async def mark_handoff_stale(
    db: Database, handoff_id: str, reason: Optional[str] = None
) -> bool:
    now = _utcnow()
    async with db.connection() as conn:
        cursor = await conn.execute(
            "UPDATE handoffs SET is_stale = 1, updated_at = ? WHERE handoff_id = ? AND is_stale = 0",
            (now, handoff_id),
        )
        affected = cursor.rowcount
        await conn.commit()
        return affected > 0


async def list_handoffs_by_task(
    db: Database, task_id: str, limit: int = 20
) -> list[Handoff]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT * FROM handoffs WHERE task_id = ? ORDER BY revision DESC LIMIT ?",
            (task_id, limit),
        )
        rows = await cursor.fetchall()
        return [
            Handoff(
                handoff_id=r["handoff_id"],
                task_id=r["task_id"],
                source_agent=r["source_agent"],
                source_session_id=r["source_session_id"],
                source_run_id=r["source_run_id"],
                source_workspace_id=r["source_workspace_id"],
                source_head_sha=r["source_head_sha"],
                state=r["state"],
                summary=r["summary"],
                completed=_from_json_list(r["completed_json"]),
                pending=_from_json_list(r["pending_json"]),
                blockers=_from_json_list(r["blockers_json"]),
                decisions=_from_json_list(r["decisions_json"]),
                verification_refs=_from_json_list(r["verification_refs_json"]),
                next_actions=_from_json_list(r["next_actions_json"]),
                revision=r["revision"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]
