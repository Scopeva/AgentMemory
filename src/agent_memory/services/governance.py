"""Service-layer wrappers for knowledge governance operations.

Both MCP tools and HTTP admin endpoints call these functions.
"""

from __future__ import annotations

from typing import Optional

from agent_memory.schemas import KnowledgeStatus
from agent_memory.storage import repositories as repo
from agent_memory.storage.database import Database
from agent_memory.core.knowledge_governance import (
    approve_and_supersede as _gov_approve_and_supersede,
    archive_knowledge as _gov_archive,
    reject_knowledge as _gov_reject,
    find_superseded as _gov_find_superseded,
    find_duplicates as _gov_find_duplicates,
    list_stale_knowledge as _gov_list_stale,
    governance_summary as _gov_summary,
)


async def governance_summary(
    db: Database,
    project_id: str,
    max_age_days: int = 30,
) -> dict:
    """Aggregate governance metrics for a project."""
    return await _gov_summary(db, project_id, max_age_days=max_age_days)


async def find_superseded(
    db: Database,
    project_id: str,
    content_threshold: float = 0.85,
    limit: int = 50,
) -> list[dict]:
    """Find accepted knowledge items that may have been superseded."""
    return await _gov_find_superseded(db, project_id, content_threshold, limit)


async def find_duplicates(
    db: Database,
    project_id: str,
    title_threshold: float = 0.90,
    content_threshold: float = 0.80,
    limit: int = 50,
) -> list[dict]:
    """Find duplicated knowledge items."""
    return await _gov_find_duplicates(
        db, project_id, title_threshold, content_threshold, limit
    )


async def list_stale_knowledge(
    db: Database,
    project_id: str,
    max_age_days: int = 30,
    limit: int = 50,
) -> list[dict]:
    """List accepted knowledge items not updated within max_age_days."""
    return await _gov_list_stale(db, project_id, max_age_days, limit)


async def approve_and_supersede(
    db: Database,
    new_memory_id: str,
    old_memory_id: str,
    decided_by: str = "agent",
    reason: str = "",
) -> dict:
    """Mark old_memory_id superseded by new_memory_id."""
    return await _gov_approve_and_supersede(db, new_memory_id, old_memory_id, decided_by, reason)


async def archive_knowledge(
    db: Database,
    memory_id: str,
    decided_by: str = "agent",
    reason: str = "",
) -> dict:
    """Archive a knowledge item."""
    return await _gov_archive(db, memory_id, decided_by, reason)


async def reject_knowledge(
    db: Database,
    memory_id: str,
    decided_by: str = "agent",
    reason: str = "",
) -> dict:
    """Reject a knowledge item."""
    return await _gov_reject(db, memory_id, decided_by, reason)
