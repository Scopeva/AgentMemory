"""Test SQLite storage layer: migrations, idempotency, version conflicts."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

from agent_memory.config import DatabaseConfig
from agent_memory.services import core
from agent_memory.storage.database import Database
from agent_memory.storage import repositories as repo
from agent_memory.storage.repositories.knowledge import (
    VersionConflictError,
    create_knowledge,
    get_knowledge,
    insert_memory_candidate,
    update_knowledge,
)
from agent_memory.storage.repositories.projects import register_project
from agent_memory.storage.repositories.sessions import register_session, start_run
from agent_memory.storage.repositories.tasks import (
    TaskConflictError,
    create_task,
    update_task_status,
)
from agent_memory.schemas import (
    AgentType,
    EventEnvelope,
    Knowledge,
    KnowledgeStatus,
    Project,
    Run,
    Session,
    Task,
    TaskStatus,
)
from agent_memory.storage.repositories.events import insert_event


@pytest_asyncio.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmp:
        config = DatabaseConfig(path=str(Path(tmp) / "test.db"))
        database = Database(config)
        await database.migrate()
        yield database


# ---------------------------------------------------------------------------
# Project / Task
# ---------------------------------------------------------------------------


class TestProjects:
    @pytest.mark.asyncio
    async def test_register_and_get_project(self, db):
        p = await register_project(db, Project(name="demo-project"))
        fetched = await repo.projects.get_project(db, p.project_id)
        assert fetched is not None
        assert fetched.name == "demo-project"
        assert fetched.status == "active"

    @pytest.mark.asyncio
    async def test_get_missing_project(self, db):
        assert await repo.projects.get_project(db, "nonexistent") is None


class TestTasks:
    @pytest.mark.asyncio
    async def test_create_and_optimistic_update(self, db):
        p = await register_project(db, Project(name="t-project"))
        t = await create_task(db, Task(project_id=p.project_id, title="My task"))
        assert t.status == TaskStatus.PENDING
        assert t.revision == 1

        updated = await update_task_status(
            db, t.task_id, expected_revision=1, status=TaskStatus.ACTIVE
        )
        assert updated.status == TaskStatus.ACTIVE
        assert updated.revision == 2

        # Stale expected_revision must fail
        with pytest.raises(TaskConflictError):
            await update_task_status(
                db, t.task_id, expected_revision=1, status=TaskStatus.BLOCKED
            )

    @pytest.mark.asyncio
    async def test_update_missing_task(self, db):
        with pytest.raises(TaskConflictError, match="not found"):
            await update_task_status(
                db, "missing-task", expected_revision=1, status=TaskStatus.ACTIVE
            )


# ---------------------------------------------------------------------------
# Events idempotency
# ---------------------------------------------------------------------------


class TestEvents:
    @pytest.mark.asyncio
    async def test_event_idempotent_by_event_id(self, db):
        p = await register_project(db, Project(name="evt-project"))
        # Need a session and run first
        ws_id = "ws-1"
        s = Session(agent_type=AgentType.PI, workspace_id=ws_id)
        await register_session(db, s)
        r = Run(session_id=s.session_id)
        await start_run(db, r)

        evt = EventEnvelope(
            event_type="run.settled",
            agent=AgentType.PI,
            session_id=s.session_id,
            run_id=r.run_id,
            project_id=p.project_id,
            sequence_no=1,
            payload={"outcome": "completed"},
        )
        assert await insert_event(db, evt) is True
        # Duplicate by event_id
        assert await insert_event(db, evt) is False

    @pytest.mark.asyncio
    async def test_event_idempotent_by_sequence(self, db):
        p = await register_project(db, Project(name="seq-project"))
        s = Session(agent_type=AgentType.CODEX, workspace_id="ws-x")
        await register_session(db, s)
        r = Run(session_id=s.session_id)
        await start_run(db, r)

        evt1 = EventEnvelope(
            event_type="run.started",
            agent=AgentType.CODEX,
            session_id=s.session_id,
            run_id=r.run_id,
            sequence_no=1,
        )
        assert await insert_event(db, evt1) is True

        # Same run + sequence, different event_id
        evt2 = EventEnvelope(
            event_id="different-id",
            event_type="run.started",
            agent=AgentType.CODEX,
            session_id=s.session_id,
            run_id=r.run_id,
            sequence_no=1,
        )
        assert await insert_event(db, evt2) is False


# ---------------------------------------------------------------------------
# Knowledge
# ---------------------------------------------------------------------------


class TestKnowledge:
    @pytest.mark.asyncio
    async def test_create_and_read(self, db):
        p = await register_project(db, Project(name="k-project"))
        k = Knowledge(
            project_id=p.project_id,
            type="adr",
            title="Use SQLite",
            content="We use SQLite for local data.",
            status=KnowledgeStatus.ACCEPTED,
        )
        await create_knowledge(db, k)
        result = await get_knowledge(db, k.memory_id, include_revisions=True)
        assert result is not None
        assert result["knowledge"]["title"] == "Use SQLite"
        assert len(result["revisions"]) == 1

    @pytest.mark.asyncio
    async def test_optimistic_update(self, db):
        p = await register_project(db, Project(name="ku-project"))
        k = Knowledge(
            project_id=p.project_id,
            type="constraint",
            title="No secrets",
            content="Never store secrets.",
        )
        await create_knowledge(db, k)

        updated = await update_knowledge(
            db,
            k.memory_id,
            expected_revision=1,
            content="Never store secrets in memory.",
            changed_by="pi",
        )
        assert updated.revision == 2
        assert "in memory" in updated.content

        with pytest.raises(VersionConflictError):
            await update_knowledge(
                db, k.memory_id, expected_revision=1, content="stale update"
            )

    @pytest.mark.asyncio
    async def test_memory_candidate_idempotency(self, db):
        p = await register_project(db, Project(name="mc-project"))
        memory = {"type": "adr", "title": "X", "content": "Y", "scope": "project"}
        candidate_id = await insert_memory_candidate(db, p.project_id, None, "key-1", memory)
        assert uuid.UUID(candidate_id)
        assert await insert_memory_candidate(db, p.project_id, None, "key-1", memory) is None

    @pytest.mark.asyncio
    async def test_submit_memory_candidate_returns_persisted_candidate_id(self, db):
        p = await register_project(db, Project(name="mc-service-project"))
        memory = {"type": "adr", "title": "X", "content": "Y", "scope": "project"}

        created = await core.submit_memory_candidate(db, p.project_id, "key-1", [memory])
        assert len(created["candidate_ids"]) == 1
        assert uuid.UUID(created["candidate_ids"][0])
        assert created["duplicate_count"] == 0

        duplicate = await core.submit_memory_candidate(db, p.project_id, "key-1", [memory])
        assert duplicate == {
            "candidate_ids": [],
            "validation_status": ["duplicate"],
            "duplicate_count": 1,
        }


# ---------------------------------------------------------------------------
# Backup / restore
# ---------------------------------------------------------------------------


class TestBackup:
    @pytest.mark.asyncio
    async def test_backup_creates_file(self, db, tmp_path):
        p = await register_project(db, Project(name="backup-project"))
        target = tmp_path / "backup.db"
        await db.backup_to(target)
        assert target.exists()
        assert target.stat().st_size > 0
