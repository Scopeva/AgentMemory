"""Unit tests for Phase 6 knowledge governance.

Covers:
- find_superseded: similarity-based supersession detection
- find_duplicates: title + content duplicate detection
- list_stale_knowledge: age-based staleness
- approve_and_supersede / archive / reject: terminal state transitions
- governance_summary: aggregate metrics
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_memory.config import DatabaseConfig
from agent_memory.core import knowledge_governance as gov
from agent_memory.schemas import Knowledge, KnowledgeStatus
from agent_memory.services import governance as gov_service
from agent_memory.storage.database import Database
from agent_memory.storage.repositories import projects as projects_repo
from agent_memory.storage.repositories import knowledge as knowledge_repo


@pytest.fixture
async def gov_db(tmp_path: Path):
    db = Database(DatabaseConfig(path=str(tmp_path / "gov.db")))
    await db.migrate()
    yield db


async def _seed_project(db: Database, project_id: str = "p1") -> None:
    from agent_memory.schemas import Project

    await projects_repo.register_project(
        db,
        Project(
            project_id=project_id,
            name="Gov Test",
            created_at="2026-01-01",
            updated_at="2026-01-01",
        ),
    )


def _old_timestamp(days_ago: int = 45) -> str:
    dt = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_ago)
    return dt.isoformat() + "Z"


async def _create_knowledge(
    db: Database,
    project_id: str,
    *,
    title: str,
    content: str,
    status: str = "accepted",
    ktype: str = "adr",
    memory_id: str | None = None,
    updated_at: str | None = None,
) -> Knowledge:
    import uuid

    k = Knowledge(
        memory_id=memory_id or str(uuid.uuid4()),
        project_id=project_id,
        type=ktype,
        status=KnowledgeStatus(status),
        title=title,
        content=content,
        updated_at=updated_at or _old_timestamp(0),
    )
    await knowledge_repo.create_knowledge(db, k)
    return k


@pytest.mark.asyncio
class TestSupersededDetection:
    async def test_detects_similar_newer_item(self, gov_db):
        db = gov_db
        await _seed_project(db)
        old = await _create_knowledge(
            db, "p1", title="Use WAL mode",
            content="Set PRAGMA journal_mode=WAL for concurrency.",
            updated_at=_old_timestamp(60),
        )
        # Newer item: a trivially near-identical single word addition → ratio ≈ 1.0
        new = await _create_knowledge(
            db, "p1", title="Use WAL mode",
            content="Set PRAGMA journal_mode=WAL for concurrency. ok.",
        )
        results = await gov.find_superseded(db, "p1", content_threshold=0.85)
        # The two items are near-identical; should flag one supersession
        assert len(results) >= 1
        assert any(r["superseded_memory_id"] == old.memory_id for r in results)

    async def test_no_supersession_for_distinct_content(self, gov_db):
        db = gov_db
        await _seed_project(db)
        await _create_knowledge(db, "p1", title="Auth flow", content="OAuth2 with PKCE")
        await _create_knowledge(db, "p1", title="DB layer", content="Use asyncpg pool")
        results = await gov.find_superseded(db, "p1")
        assert results == []


@pytest.mark.asyncio
class TestDuplicateDetection:
    async def test_finds_duplicates(self, gov_db):
        db = gov_db
        await _seed_project(db)
        await _create_knowledge(db, "p1", title="WAL mode", content="journal_mode WAL")
        await _create_knowledge(db, "p1", title="WAL mode", content="journal_mode WAL")
        results = await gov.find_duplicates(db, "p1")
        assert len(results) >= 1
        assert results[0]["title_similarity"] >= 0.9

    async def test_no_duplicates_for_distinct_items(self, gov_db):
        db = gov_db
        await _seed_project(db)
        await _create_knowledge(db, "p1", title="Auth", content="OAuth2")
        await _create_knowledge(db, "p1", title="DB", content="postgres")
        results = await gov.find_duplicates(db, "p1")
        assert results == []


@pytest.mark.asyncio
class TestStaleKnowledge:
    async def test_lists_old_items(self, gov_db):
        db = gov_db
        await _seed_project(db)
        old = await _create_knowledge(
            db, "p1", title="Old note", content="ancient", updated_at=_old_timestamp(45)
        )
        recent = await _create_knowledge(db, "p1", title="New note", content="fresh")
        stale = await gov.list_stale_knowledge(db, "p1", max_age_days=30)
        ids = [s["memory_id"] for s in stale]
        assert old.memory_id in ids
        assert recent.memory_id not in ids

    async def test_no_stale_when_recent(self, gov_db):
        db = gov_db
        await _seed_project(db)
        await _create_knowledge(db, "p1", title="Fresh", content="new")
        stale = await gov.list_stale_knowledge(db, "p1", max_age_days=30)
        assert stale == []


@pytest.mark.asyncio
class TestApproveAndSupersede:
    async def test_supersede_success(self, gov_db):
        db = gov_db
        await _seed_project(db)
        old = await _create_knowledge(db, "p1", title="v1", content="old content")
        new = await _create_knowledge(db, "p1", title="v2", content="new content")
        result = await gov.approve_and_supersede(db, new.memory_id, old.memory_id)
        assert result["ok"]
        # Verify old is now superseded
        k = await knowledge_repo.get_knowledge(db, old.memory_id)
        assert k["knowledge"]["status"] == KnowledgeStatus.SUPERSEDED

    async def test_supersede_fails_when_new_not_accepted(self, gov_db):
        db = gov_db
        await _seed_project(db)
        old = await _create_knowledge(db, "p1", title="old", content="x")
        cand = await _create_knowledge(
            db, "p1", title="cand", content="y", status="candidate"
        )
        result = await gov.approve_and_supersede(db, cand.memory_id, old.memory_id)
        assert not result["ok"]
        assert "not accepted" in result["error"]

    async def test_supersede_missing_memory(self, gov_db):
        db = gov_db
        await _seed_project(db)
        import uuid
        result = await gov.approve_and_supersede(db, str(uuid.uuid4()), str(uuid.uuid4()))
        assert not result["ok"]


@pytest.mark.asyncio
class TestArchiveReject:
    async def test_archive_success(self, gov_db):
        db = gov_db
        await _seed_project(db)
        k = await _create_knowledge(db, "p1", title="arch", content="c")
        result = await gov.archive_knowledge(db, k.memory_id)
        assert result["ok"]
        row = await knowledge_repo.get_knowledge(db, k.memory_id)
        assert row["knowledge"]["status"] == KnowledgeStatus.ARCHIVED

    async def test_reject_success(self, gov_db):
        db = gov_db
        await _seed_project(db)
        k = await _create_knowledge(db, "p1", title="rej", content="c")
        result = await gov.reject_knowledge(db, k.memory_id)
        assert result["ok"]
        row = await knowledge_repo.get_knowledge(db, k.memory_id)
        assert row["knowledge"]["status"] == KnowledgeStatus.REJECTED

    async def test_archive_missing(self, gov_db):
        db = gov_db
        await _seed_project(db)
        import uuid
        result = await gov.archive_knowledge(db, str(uuid.uuid4()))
        assert not result["ok"]


@pytest.mark.asyncio
class TestGovernanceSummary:
    async def test_summary_counts(self, gov_db):
        db = gov_db
        await _seed_project(db)
        await _create_knowledge(db, "p1", title="a", content="x")
        await _create_knowledge(db, "p1", title="b", content="y", status="candidate")
        summary = await gov.governance_summary(db, "p1")
        assert summary["total_knowledge"] == 2
        assert summary["status_counts"].get("accepted", 0) == 1
        assert summary["status_counts"].get("candidate", 0) == 1


@pytest.mark.asyncio
class TestGovernanceServiceWrappers:
    async def test_service_wrappers_delegated(self, gov_db):
        db = gov_db
        await _seed_project(db)
        s1 = await gov_service.governance_summary(db, "p1")
        assert s1["project_id"] == "p1"
        sup = await gov_service.find_superseded(db, "p1")
        assert sup == []
        dup = await gov_service.find_duplicates(db, "p1")
        assert dup == []
        stale = await gov_service.list_stale_knowledge(db, "p1")
        assert stale == []
