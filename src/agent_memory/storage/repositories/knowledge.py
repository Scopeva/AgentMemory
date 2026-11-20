"""Knowledge repository with revision history and candidate approval."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from agent_memory.schemas import (
    EvidenceRef,
    Knowledge,
    KnowledgeStatus,
    KnowledgeScope,
)
from agent_memory.storage.database import Database


class VersionConflictError(Exception):
    """Raised when a knowledge update conflicts with a newer revision."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _evidence_to_json(evidence: list[EvidenceRef]) -> str:
    return json.dumps(
        [{"kind": e.kind.value, "value": e.value} for e in evidence],
        ensure_ascii=False,
    )


def _json_to_evidence(raw: str) -> list[EvidenceRef]:
    try:
        data = json.loads(raw)
        return [EvidenceRef(kind=e["kind"], value=e["value"]) for e in data]
    except (TypeError, json.JSONDecodeError, KeyError):
        return []


async def create_knowledge(db: Database, k: Knowledge) -> Knowledge:
    now = _utcnow()
    # Honour the Knowledge model's created_at/updated_at if explicitly set
    # (used by governance tests and backfills); otherwise use now.
    created_at = k.created_at or now
    updated_at = k.updated_at or now
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO knowledge ("
            "memory_id, project_id, scope, type, status, title, content, revision, "
            "current_source_revision, supersedes_memory_id, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                k.memory_id,
                k.project_id,
                k.scope.value,
                k.type,
                k.status.value,
                k.title,
                k.content,
                k.revision,
                k.current_source_revision,
                k.supersedes_memory_id,
                created_at,
                updated_at,
            ),
        )
        # Initial revision record
        await conn.execute(
            "INSERT INTO knowledge_revisions "
            "(memory_id, revision, title, content, status, changed_by, changed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                k.memory_id,
                k.revision,
                k.title,
                k.content,
                k.status.value,
                "system",
                now,
            ),
        )
        # Evidence sources
        import uuid

        for ev in k.evidence:
            source_id = str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO knowledge_sources "
                "(source_id, memory_id, kind, value, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (source_id, k.memory_id, ev.kind.value, ev.value, now),
            )
        await conn.commit()
    return k


async def get_knowledge(
    db: Database, memory_id: str, include_revisions: bool = False
) -> Optional[dict]:
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT memory_id, project_id, scope, type, status, title, content, "
            "revision, current_source_revision, supersedes_memory_id, created_at, updated_at "
            "FROM knowledge WHERE memory_id = ?",
            (memory_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        k = Knowledge(
            memory_id=row["memory_id"],
            project_id=row["project_id"],
            scope=KnowledgeScope(row["scope"]),
            type=row["type"],
            status=KnowledgeStatus(row["status"]),
            title=row["title"],
            content=row["content"],
            revision=row["revision"],
            current_source_revision=row["current_source_revision"],
            supersedes_memory_id=row["supersedes_memory_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        result: dict = {"knowledge": k.model_dump()}
        if include_revisions:
            rev_cursor = await conn.execute(
                "SELECT revision, title, content, status, changed_by, changed_at "
                "FROM knowledge_revisions WHERE memory_id = ? ORDER BY revision DESC",
                (memory_id,),
            )
            rev_rows = await rev_cursor.fetchall()
            result["revisions"] = [dict(r) for r in rev_rows]
        # Evidence
        ev_cursor = await conn.execute(
            "SELECT kind, value, verified_at FROM knowledge_sources WHERE memory_id = ?",
            (memory_id,),
        )
        ev_rows = await ev_cursor.fetchall()
        result["evidence"] = [dict(r) for r in ev_rows]
        return result


async def update_knowledge(
    db: Database,
    memory_id: str,
    expected_revision: int,
    *,
    title: Optional[str] = None,
    content: Optional[str] = None,
    status: Optional[KnowledgeStatus] = None,
    changed_by: str = "agent",
) -> Knowledge:
    """Optimistic update of knowledge with revision history."""
    now = _utcnow()
    async with db.connection() as conn:
        # Fetch current
        cursor = await conn.execute(
            "SELECT revision, title, content, status FROM knowledge WHERE memory_id = ?",
            (memory_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"Knowledge {memory_id} not found")
        if row["revision"] != expected_revision:
            raise VersionConflictError(
                f"Expected revision {expected_revision}, actual {row['revision']}"
            )
        new_revision = expected_revision + 1
        new_title = title if title is not None else row["title"]
        new_content = content if content is not None else row["content"]
        new_status = status.value if status else row["status"]

        await conn.execute(
            "UPDATE knowledge SET title = ?, content = ?, status = ?, "
            "revision = revision + 1, updated_at = ? WHERE memory_id = ?",
            (new_title, new_content, new_status, now, memory_id),
        )
        await conn.execute(
            "INSERT INTO knowledge_revisions "
            "(memory_id, revision, title, content, status, changed_by, changed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (memory_id, new_revision, new_title, new_content, new_status, changed_by, now),
        )
        await conn.commit()

    # Return updated knowledge
    fetched = await get_knowledge(db, memory_id)
    return Knowledge(**fetched["knowledge"])  # type: ignore[arg-type]


async def list_knowledge_by_project(
    db: Database,
    project_id: str,
    status: Optional[KnowledgeStatus] = None,
    scope: Optional[KnowledgeScope] = None,
    limit: int = 50,
) -> list[Knowledge]:
    sql = (
        "SELECT memory_id, project_id, scope, type, status, title, content, "
        "revision, current_source_revision, supersedes_memory_id, created_at, updated_at "
        "FROM knowledge WHERE project_id = ?"
    )
    params: list = [project_id]
    if status:
        sql += " AND status = ?"
        params.append(status.value)
    if scope:
        sql += " AND scope = ?"
        params.append(scope.value)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    async with db.connection() as conn:
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [
            Knowledge(
                memory_id=r["memory_id"],
                project_id=r["project_id"],
                scope=KnowledgeScope(r["scope"]),
                type=r["type"],
                status=KnowledgeStatus(r["status"]),
                title=r["title"],
                content=r["content"],
                revision=r["revision"],
                current_source_revision=r["current_source_revision"],
                supersedes_memory_id=r["supersedes_memory_id"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Memory candidates
# ---------------------------------------------------------------------------


async def insert_memory_candidate(
    db: Database,
    project_id: str,
    run_id: Optional[str],
    idempotency_key: str,
    memory_json: dict,
) -> Optional[str]:
    """Insert a candidate memory and return its ID, or ``None`` if duplicate."""
    now = _utcnow()
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT 1 FROM memory_candidates WHERE project_id = ? AND idempotency_key = ?",
            (project_id, idempotency_key),
        )
        if await cursor.fetchone():
            return None
        import uuid

        candidate_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO memory_candidates "
            "(candidate_id, project_id, run_id, idempotency_key, memory_json, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (
                candidate_id,
                project_id,
                run_id,
                idempotency_key,
                json.dumps(memory_json, ensure_ascii=False),
                now,
                now,
            ),
        )
        await conn.commit()
        return candidate_id


async def list_pending_candidates(
    db: Database, project_id: Optional[str] = None, limit: int = 50
) -> list[dict]:
    sql = (
        "SELECT candidate_id, project_id, run_id, idempotency_key, memory_json, "
        "status, created_at, updated_at FROM memory_candidates WHERE status = 'pending'"
    )
    params: list = []
    if project_id:
        sql += " AND project_id = ?"
        params.append(project_id)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    async with db.connection() as conn:
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            try:
                memory = json.loads(r["memory_json"])
            except (TypeError, json.JSONDecodeError):
                memory = {}
            results.append({**dict(r), "memory": memory})
        return results


async def approve_candidate(
    db: Database,
    candidate_id: str,
    decided_by: str,
    auto_accept: bool = False,
) -> Optional[str]:
    """Approve a candidate; optionally promote to accepted knowledge.

    Returns the new knowledge memory_id if auto_accept is True and promotion succeeded,
    otherwise None.
    """
    now = _utcnow()
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT candidate_id, project_id, run_id, memory_json, status "
            "FROM memory_candidates WHERE candidate_id = ?",
            (candidate_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        if row["status"] != "pending":
            return None

        try:
            memory = json.loads(row["memory_json"])
        except (TypeError, json.JSONDecodeError):
            memory = {}

        target_status = "approved"
        memory_id: Optional[str] = None

        if auto_accept:
            # Promote to knowledge table
            import uuid

            memory_id = str(uuid.uuid4())
            evidence_raw = memory.get("evidence_refs", [])
            evidence = [
                EvidenceRef(
                    kind=e.get("kind", "agent_statement"),
                    value=e.get("value", ""),
                )
                for e in evidence_raw
            ]
            k = Knowledge(
                memory_id=memory_id,
                project_id=row["project_id"],
                scope=KnowledgeScope(memory.get("scope", "project")),
                type=memory.get("type", "unknown"),
                status=KnowledgeStatus.ACCEPTED,
                title=memory.get("title", "Untitled"),
                content=memory.get("content", ""),
                evidence=evidence,
            )
            await conn.execute(
                "INSERT INTO knowledge ("
                "memory_id, project_id, scope, type, status, title, content, revision, "
                "current_source_revision, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
                (
                    memory_id,
                    row["project_id"],
                    k.scope.value,
                    k.type,
                    k.status.value,
                    k.title,
                    k.content,
                    row["run_id"],
                    now,
                    now,
                ),
            )
            await conn.execute(
                "INSERT INTO knowledge_revisions "
                "(memory_id, revision, title, content, status, changed_by, changed_at) "
                "VALUES (?, 1, ?, ?, ?, ?, ?)",
                (memory_id, k.title, k.content, k.status.value, "auto-promote", now),
            )
            for ev in evidence:
                source_id = str(uuid.uuid4())
                await conn.execute(
                    "INSERT INTO knowledge_sources (source_id, memory_id, kind, value, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (source_id, memory_id, ev.kind.value, ev.value, now),
                )
            target_status = "approved"

        await conn.execute(
            "UPDATE memory_candidates SET status = ?, updated_at = ? WHERE candidate_id = ?",
            (target_status, now, candidate_id),
        )
        approval_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO approvals (approval_id, candidate_id, decision, decided_by, decided_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (approval_id, candidate_id, "approved" if auto_accept else "reviewed", decided_by, now),
        )
        await conn.commit()
        return memory_id


async def reject_candidate(
    db: Database, candidate_id: str, decided_by: str, reason: Optional[str] = None
) -> bool:
    now = _utcnow()
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT candidate_id, status FROM memory_candidates WHERE candidate_id = ?",
            (candidate_id,),
        )
        row = await cursor.fetchone()
        if not row or row["status"] != "pending":
            return False
        await conn.execute(
            "UPDATE memory_candidates SET status = 'rejected', updated_at = ? WHERE candidate_id = ?",
            (now, candidate_id),
        )
        approval_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO approvals (approval_id, candidate_id, decision, decided_by, decided_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (approval_id, candidate_id, "rejected", decided_by, now),
        )
        await conn.commit()
        return True
