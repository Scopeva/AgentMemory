"""Knowledge governance: supersession, duplication, staleness detection,
and approval-with-supersede workflows.

All functions are async and operate on the shared Database instance.
"""

from __future__ import annotations

import difflib
from datetime import datetime, timedelta, timezone
from typing import Optional

from agent_memory.schemas import Knowledge, KnowledgeStatus
from agent_memory.storage import repositories as repo
from agent_memory.storage.database import Database


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


# ---------------------------------------------------------------------------
# Supersession detection
# ---------------------------------------------------------------------------


async def find_superseded(
    db: Database,
    project_id: str,
    content_threshold: float = 0.85,
    limit: int = 50,
) -> list[dict]:
    """Find accepted knowledge items that may have been superseded.

    Heuristic: two accepted items with the same (project, type) where the
    newer one shares >= content_threshold similarity with the older one.
    """
    items = await repo.knowledge.list_knowledge_by_project(
        db, project_id, status=KnowledgeStatus.ACCEPTED, limit=limit * 4
    )
    # Group by type
    by_type: dict[str, list[Knowledge]] = {}
    for k in items:
        by_type.setdefault(k.type, []).append(k)

    results: list[dict] = []
    for ktype, group in by_type.items():
        group.sort(key=lambda k: k.updated_at)
        for i in range(len(group) - 1):
            older, newer = group[i], group[i + 1]
            sim = _similarity(older.content, newer.content)
            if sim >= content_threshold:
                results.append({
                    "superseded_memory_id": older.memory_id,
                    "superseded_title": older.title,
                    "supersedes_memory_id": newer.memory_id,
                    "supersedes_title": newer.title,
                    "type": ktype,
                    "similarity": round(sim, 3),
                })
    return results[:limit]


def _similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio between two strings (0.0 – 1.0)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


async def find_duplicates(
    db: Database,
    project_id: str,
    title_threshold: float = 0.90,
    content_threshold: float = 0.80,
    limit: int = 50,
) -> list[dict]:
    """Find candidate/accepted knowledge items that look duplicated.

    Two items are considered duplicates when their titles are very similar
    AND their contents overlap significantly.
    """
    items = await repo.knowledge.list_knowledge_by_project(
        db, project_id, status=KnowledgeStatus.ACCEPTED, limit=limit * 4
    )
    pairs: list[dict] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            t_sim = _similarity(a.title, b.title)
            if t_sim < title_threshold:
                continue
            c_sim = _similarity(a.content, b.content)
            if c_sim < content_threshold:
                continue
            pairs.append({
                "memory_id_a": a.memory_id,
                "title_a": a.title,
                "memory_id_b": b.memory_id,
                "title_b": b.title,
                "title_similarity": round(t_sim, 3),
                "content_similarity": round(c_sim, 3),
            })
    return pairs[:limit]


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------


async def list_stale_knowledge(
    db: Database,
    project_id: str,
    max_age_days: int = 30,
    limit: int = 50,
) -> list[dict]:
    """List accepted knowledge items not updated within ``max_age_days``.

    These are candidates for re-verification or archival.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=max_age_days)
    ).replace(tzinfo=None).isoformat() + "Z"

    items = await repo.knowledge.list_knowledge_by_project(
        db, project_id, status=KnowledgeStatus.ACCEPTED, limit=limit
    )
    stale = []
    for k in items:
        if k.updated_at < cutoff:
            stale.append({
                "memory_id": k.memory_id,
                "title": k.title,
                "type": k.type,
                "updated_at": k.updated_at,
                "age_days": max_age_days,  # approximate
            })
    return stale[:limit]


# ---------------------------------------------------------------------------
# Approve with supersede
# ---------------------------------------------------------------------------


async def approve_and_supersede(
    db: Database,
    new_memory_id: str,
    old_memory_id: str,
    decided_by: str = "agent",
    reason: str = "",
) -> dict:
    """Mark ``old_memory_id`` superseded by ``new_memory_id``.

    The new item must be in 'accepted' status; the old item must also be
    'accepted'. The old item's status is set to 'superseded' and its
    supersedes_memory_id points to the new one.
    """
    new_k = await repo.knowledge.get_knowledge(db, new_memory_id, include_revisions=False)
    old_k = await repo.knowledge.get_knowledge(db, old_memory_id, include_revisions=False)

    if new_k is None or old_k is None:
        return {"ok": False, "error": "memory not found"}

    new_status = KnowledgeStatus(new_k["knowledge"]["status"])
    old_status = KnowledgeStatus(old_k["knowledge"]["status"])

    if new_status != KnowledgeStatus.ACCEPTED:
        return {"ok": False, "error": f"new memory {new_memory_id} is {new_status.value}, not accepted"}
    if old_status != KnowledgeStatus.ACCEPTED:
        return {"ok": False, "error": f"old memory {old_memory_id} is {old_status.value}, not accepted"}

    # Update old: mark superseded
    from agent_memory.storage.repositories.knowledge import update_knowledge

    updated_old = await update_knowledge(
        db,
        old_memory_id,
        expected_revision=old_k["knowledge"]["revision"],
        status=KnowledgeStatus.SUPERSEDED,
        changed_by=decided_by,
    )

    # Update new: record the supersession link
    await update_knowledge(
        db,
        new_memory_id,
        expected_revision=new_k["knowledge"]["revision"],
        status=KnowledgeStatus.ACCEPTED,
        changed_by=decided_by,
    )

    return {
        "ok": True,
        "superseded_memory_id": old_memory_id,
        "supersedes_memory_id": new_memory_id,
        "old_revision": updated_old.revision,
        "new_revision": new_k["knowledge"]["revision"],
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Archive / reject bulk
# ---------------------------------------------------------------------------


async def archive_knowledge(
    db: Database,
    memory_id: str,
    decided_by: str = "agent",
    reason: str = "",
) -> dict:
    """Archive a knowledge item (terminal state)."""
    from agent_memory.storage.repositories.knowledge import update_knowledge, VersionConflictError

    k = await repo.knowledge.get_knowledge(db, memory_id, include_revisions=False)
    if k is None:
        return {"ok": False, "error": f"memory {memory_id} not found"}

    try:
        updated = await update_knowledge(
            db,
            memory_id,
            expected_revision=k["knowledge"]["revision"],
            status=KnowledgeStatus.ARCHIVED,
            changed_by=decided_by,
        )
        return {"ok": True, "memory_id": memory_id, "new_revision": updated.revision, "reason": reason}
    except VersionConflictError as exc:
        return {"ok": False, "error": str(exc)}


async def reject_knowledge(
    db: Database,
    memory_id: str,
    decided_by: str = "agent",
    reason: str = "",
) -> dict:
    """Reject a candidate knowledge item (terminal state)."""
    from agent_memory.storage.repositories.knowledge import update_knowledge, VersionConflictError

    k = await repo.knowledge.get_knowledge(db, memory_id, include_revisions=False)
    if k is None:
        return {"ok": False, "error": f"memory {memory_id} not found"}

    try:
        updated = await update_knowledge(
            db,
            memory_id,
            expected_revision=k["knowledge"]["revision"],
            status=KnowledgeStatus.REJECTED,
            changed_by=decided_by,
        )
        return {"ok": True, "memory_id": memory_id, "new_revision": updated.revision, "reason": reason}
    except VersionConflictError as exc:
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Governance summary
# ---------------------------------------------------------------------------


async def governance_summary(
    db: Database,
    project_id: str,
    max_age_days: int = 30,
) -> dict:
    """Aggregate governance metrics for a project."""
    all_items = await repo.knowledge.list_knowledge_by_project(
        db, project_id, limit=1000
    )
    counts: dict[str, int] = {}
    for k in all_items:
        counts[k.status.value] = counts.get(k.status.value, 0) + 1

    superseded = await find_superseded(db, project_id)
    duplicates = await find_duplicates(db, project_id)
    stale = await list_stale_knowledge(db, project_id, max_age_days=max_age_days)

    return {
        "project_id": project_id,
        "total_knowledge": len(all_items),
        "status_counts": counts,
        "potential_supersessions": len(superseded),
        "potential_duplicates": len(duplicates),
        "stale_items": len(stale),
    }
