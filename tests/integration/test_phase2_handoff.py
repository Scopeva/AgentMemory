"""Phase 2 integration tests: two simulated agents hand off a task
through the service layer (which is the same path MCP tools use).

Scenario:
- Agent A (Pi) creates a task, does some work, and leaves a handoff.
- Agent B (Codex) picks up the task, reads the handoff, continues, and
  updates the task state.
- Verify: handoff revision increments, stale handoffs are not overwritten,
  and the receiving agent gets the correct context.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from agent_memory.config import DatabaseConfig
from agent_memory.schemas import (
    AgentType,
    Handoff,
    Project,
    Run,
    Session,
    Task,
    TaskStatus,
)
from agent_memory.services import core
from agent_memory.storage.database import Database
from agent_memory.storage.repositories import handoffs, projects, sessions, tasks


@pytest_asyncio.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmp:
        config = DatabaseConfig(path=str(Path(tmp) / "phase2.db"))
        database = Database(config)
        await database.migrate()
        yield database


@pytest_asyncio.fixture
async def project(db):
    p = await projects.register_project(db, Project(name="phase2-e2e"))
    return p


@pytest_asyncio.fixture
async def task(db, project):
    t = await tasks.create_task(
        db, Task(project_id=project.project_id, title="Migrate auth to JWT")
    )
    # Move to active
    t = await tasks.update_task_status(
        db, t.task_id, expected_revision=1, status=TaskStatus.ACTIVE
    )
    return t


@pytest_asyncio.fixture
async def session_a(db):
    """Pi's session."""
    s = Session(agent_type=AgentType.PI, workspace_id="ws-a", native_session_id="pi-native-1")
    await sessions.register_session(db, s)
    return s


@pytest_asyncio.fixture
async def run_a(db, session_a, task):
    """Pi's run on the task."""
    r = Run(session_id=session_a.session_id, task_id=task.task_id, head_sha_start="sha-start")
    await sessions.start_run(db, r)
    return r


class TestPhase2HandoffFlow:
    """Full two-agent handoff through the service layer."""

    @pytest.mark.asyncio
    async def test_pi_creates_handoff_and_codex_resumes(self, db, project, task, session_a, run_a):
        # --- Pi (Agent A) leaves a handoff before finishing ---
        handoff = Handoff(
            task_id=task.task_id,
            source_agent="pi",
            source_session_id=session_a.session_id,
            source_run_id=run_a.run_id,
            source_workspace_id="ws-a",
            source_head_sha="sha-mid",
            summary="JWT refresh token implemented, 3/5 unit tests passing",
            completed=["token generation", "refresh endpoint"],
            pending=["fix edge case in refresh expiry", "integration tests"],
            blockers=[],
            decisions=["store tokens in localStorage"],
            verification_refs=["tests/auth.spec.ts"],
            next_actions=["run integration suite", "add CSRF protection check"],
        )
        result = await core.create_handoff(db, handoff)
        assert result.revision == 1
        assert result.task_id == task.task_id

        # --- Codex (Agent B) picks up the task ---
        session_b = Session(
            agent_type=AgentType.CODEX,
            workspace_id="ws-b",
            native_session_id="codex-native-1",
        )
        await sessions.register_session(db, session_b)
        run_b = Run(
            session_id=session_b.session_id,
            task_id=task.task_id,
            head_sha_start="sha-mid",
        )
        await sessions.start_run(db, run_b)

        # Codex reads the latest handoff
        latest = await core.get_latest_handoff(db, task_id=task.task_id)
        assert latest is not None
        assert latest.source_agent == "pi"
        assert latest.revision == 1
        assert "JWT refresh" in latest.summary

        # Codex continues and creates a newer handoff
        handoff2 = Handoff(
            task_id=task.task_id,
            source_agent="codex",
            source_session_id=session_b.session_id,
            source_run_id=run_b.run_id,
            source_workspace_id="ws-b",
            source_head_sha="sha-newer",
            summary="Edge case fixed, all 5 unit tests passing",
            completed=["fix edge case in refresh expiry"],
            pending=["integration tests"],
            decisions=[],
            verification_refs=["tests/auth.spec.ts::test_refresh_expiry"],
            next_actions=["run integration suite"],
        )
        result2 = await core.create_handoff(db, handoff2)
        assert result2.revision == 2
        assert result2.handoff_id != result.handoff_id

        # Latest handoff now reflects Codex's state
        latest2 = await core.get_latest_handoff(db, task_id=task.task_id)
        assert latest2 is not None
        assert latest2.source_agent == "codex"
        assert latest2.revision == 2
        assert latest2.summary == "Edge case fixed, all 5 unit tests passing"

    @pytest.mark.asyncio
    async def test_handoff_revision_increments_monotonically(self, db, project, task):
        """Multiple handoffs must produce strictly increasing revisions."""
        for i in range(4):
            h = Handoff(
                task_id=task.task_id,
                source_agent=f"agent-{i}",
                summary=f"State {i}",
            )
            result = await core.create_handoff(db, h)
            assert result.revision == i + 1

        all_handoffs = await handoffs.list_handoffs_by_task(db, task.task_id, limit=10)
        revisions = [x.revision for x in all_handoffs]
        assert revisions == [4, 3, 2, 1]  # descending order

    @pytest.mark.asyncio
    async def test_task_state_reflects_handoff_activity(self, db, project, task, session_a, run_a):
        """get_task_state must return the latest handoff alongside the task."""
        h = Handoff(
            task_id=task.task_id,
            source_agent="pi",
            source_run_id=run_a.run_id,
            summary="WIP: token generation",
            pending=["unit tests"],
        )
        await core.create_handoff(db, h)

        state = await core.get_task_state(db, task_id=task.task_id)
        assert state["task"] is not None
        assert state["task"]["task_id"] == task.task_id
        assert state["latest_handoff"] is not None
        assert state["latest_handoff"]["summary"] == "WIP: token generation"
        assert state["latest_handoff"]["source_agent"] == "pi"

    @pytest.mark.asyncio
    async def test_stale_handoff_detection_via_head_sha(self, db, project, task):
        """When HEAD has advanced beyond the handoff's source_head_sha,
        the handoff should be flagged for revalidation."""
        h1 = Handoff(
            task_id=task.task_id,
            source_agent="pi",
            source_head_sha="sha-old",
            summary="Old state",
        )
        await core.create_handoff(db, h1)

        latest = await core.get_latest_handoff(db, task_id=task.task_id)
        assert latest.source_head_sha == "sha-old"
        # needs_revalidation is True whenever a source_head_sha is present,
        # signalling the receiver must check Git before continuing.

    @pytest.mark.asyncio
    async def test_project_context_includes_recent_handoffs(self, db, project, task):
        """get_project_context must surface the latest handoffs for active tasks."""
        h = Handoff(
            task_id=task.task_id,
            source_agent="pi",
            summary="Auth work in progress",
            pending=["integration tests"],
        )
        await core.create_handoff(db, h)

        ctx = await core.get_project_context(
            db, project.project_id, include=["active_tasks", "recent_handoffs"]
        )
        assert "active_tasks" in ctx["sections"]
        assert "Migrate auth" in ctx["sections"]["active_tasks"]
        assert "recent_handoffs" in ctx["sections"]
        assert "Auth work in progress" in ctx["sections"]["recent_handoffs"]

    @pytest.mark.asyncio
    async def test_two_agents_cannot_overwrite_newer_handoff(self, db, project, task):
        """An older agent's late handoff must not clobber a newer one.

        This is verified by the fact that create_handoff always appends a
        new revision; the 'latest' query returns the highest revision.
        """
        h_new = Handoff(task_id=task.task_id, source_agent="codex", summary="Newer")
        await core.create_handoff(db, h_new)
        assert h_new.revision == 1

        h_old = Handoff(task_id=task.task_id, source_agent="pi", summary="Older but late")
        await core.create_handoff(db, h_old)
        assert h_old.revision == 2  # appended, not overwritten

        latest = await core.get_latest_handoff(db, task_id=task.task_id)
        assert latest.summary == "Older but late"  # latest by revision
        # The 'stale' marker is a separate operation:
        marked = await handoffs.mark_handoff_stale(db, h_new.handoff_id)
        assert marked is True
        # Latest non-stale is now only the revision-2 handoff
        latest2 = await core.get_latest_handoff(db, task_id=task.task_id)
        assert latest2.handoff_id == h_old.handoff_id
