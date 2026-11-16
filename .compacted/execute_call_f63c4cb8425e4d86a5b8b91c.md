338:async def search_memory(
339-    db: Database,
340-    project_id: str,
341-    query: str,
342-    limit: int = 8,
343-    filters: Optional[dict] = None,
344-) -> dict:
345-    """Phase 2: lexical search over knowledge titles/content.
346-
347-    Phase 4 replaces this with FTS5 + sqlite-vec hybrid RRF.
348-    """
349-    status_filter = None
350-    if filters and "status" in filters:
351-        try:
352-            status_filter = KnowledgeStatus(filters["status"])
353-        except ValueError:
354-            status_filter = None
355-
356-    results = await repo.knowledge.list_knowledge_by_project(
357-        db,
358-        project_id,
359-        status=status_filter,
360-        limit=limit,
361-    )
362-    # Simple keyword filter on title/content
363-    lower_query = query.lower()
364-    matched = [
365-        k for k in results
366-        if lower_query in k.title.lower() or lower_query in k.content.lower()
367-    ]
368-    return {
369-        "results": [k.model_dump() for k in matched[:limit]],
370-        "retrieval_mode": "lexical_basic",
371-    }
372-
373-
374-# ---------------------------------------------------------------------------
375-# Admin / candidates
376-# ---------------------------------------------------------------------------
377-
378-
---REPO-KNOW---
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
                now,
                now,
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

... [truncated, showing 200/463 lines, 6518/16064 chars]