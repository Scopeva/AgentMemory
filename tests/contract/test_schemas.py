"""Contract tests for Phase 0 schemas.

These tests verify:
- Pydantic models serialize/deserialize as expected
- Event envelope rejects unknown event types
- Knowledge state machine values are constrained
- MCP tool input models accept valid payloads
"""

from __future__ import annotations

import pytest

from agent_memory.mcp_schemas import (
    CreateHandoffInput,
    GetLatestHandoffInput,
    GetProjectContextInput,
    GetTaskStateInput,
    SearchMemoryInput,
    SubmitMemoryCandidateInput,
    UpdateTaskStateInput,
)
from agent_memory.schemas import (
    AgentType,
    EvidenceKind,
    EventEnvelope,
    Knowledge,
    KnowledgeScope,
    KnowledgeStatus,
    MemoryCandidate,
    Project,
    Run,
    RunStatus,
    Task,
    TaskStatus,
)


# ---------------------------------------------------------------------------
# EventEnvelope
# ---------------------------------------------------------------------------


class TestEventEnvelope:
    def test_valid_envelope(self):
        evt = EventEnvelope(
            event_type="run.settled",
            agent=AgentType.PI,
            session_id="s1",
            run_id="r1",
            project_id="p1",
            task_id="t1",
            sequence_no=1,
            payload={"outcome": "completed"},
        )
        assert evt.event_id
        assert evt.schema_version == "1.0"
        assert evt.agent == AgentType.PI

    def test_rejects_unknown_event_type(self):
        with pytest.raises(ValueError, match="Unknown event_type"):
            EventEnvelope(
                event_type="bogus.event",
                agent=AgentType.CODEX,
                session_id="s1",
                run_id="r1",
            )

    def test_all_allowed_event_types(self):
        allowed = {
            "run.started",
            "run.settled",
            "run.interrupted",
            "checkpoint.created",
            "session.start",
            "session.end",
            "session.compacted",
            "turn.end",
            "memory.extraction_requested",
            "memory.extraction_completed",
        }
        for t in allowed:
            evt = EventEnvelope(
                event_type=t,
                agent=AgentType.OPENCODE,
                session_id="s",
                run_id="r",
            )
            assert evt.event_type == t


# ---------------------------------------------------------------------------
# Knowledge
# ---------------------------------------------------------------------------


class TestKnowledge:
    def test_defaults(self):
        k = Knowledge(
            project_id="p1",
            type="adr",
            title="Use SQLite",
            content="We chose SQLite for simplicity.",
        )
        assert k.status == KnowledgeStatus.CANDIDATE
        assert k.scope == KnowledgeScope.PROJECT
        assert k.revision == 1
        assert k.evidence == []

    def test_with_evidence(self):
        k = Knowledge(
            project_id="p1",
            type="problem_solution",
            title="Fix race condition",
            content="Added lock.",
            evidence=[
                {"kind": EvidenceKind.GIT_COMMIT, "value": "abc123"},
                {"kind": EvidenceKind.TEST_RESULT, "value": "test_race.py::pass"},
            ],
        )
        assert len(k.evidence) == 2
        assert k.evidence[0].kind == EvidenceKind.GIT_COMMIT


# ---------------------------------------------------------------------------
# Task / Run / Project
# ---------------------------------------------------------------------------


class TestTaskRunProject:
    def test_task_defaults(self):
        t = Task(project_id="p1", title="Auth migration")
        assert t.status == TaskStatus.PENDING
        assert t.revision == 1

    def test_run_defaults(self):
        r = Run(session_id="s1")
        assert r.status == RunStatus.RUNNING
        assert r.task_id is None

    def test_project_defaults(self):
        p = Project(name="demo")
        assert p.status.value == "active"


# ---------------------------------------------------------------------------
# MCP input models
# ---------------------------------------------------------------------------


class TestMcpInputs:
    def test_get_project_context(self):
        m = GetProjectContextInput(project_id="p1")
        assert "project_summary" in m.include
        assert m.max_output_tokens == 2000

    def test_search_memory(self):
        m = SearchMemoryInput(project_id="p1", query="jwt refresh")
        assert m.limit == 8

    def test_create_handoff(self):
        m = CreateHandoffInput(task_id="t1", summary="WIP")
        assert m.pending == []
        assert m.completed == []
        assert not hasattr(m, "revision")  # revision is assigned server-side

    def test_submit_memory_candidate(self):
        m = SubmitMemoryCandidateInput(
            project_id="p1",
            idempotency_key="idem-1",
            memories=[
                {
                    "type": "constraint",
                    "title": "No secrets in memory",
                    "content": "Never store API keys.",
                    "scope": "project",
                }
            ],
        )
        assert len(m.memories) == 1

    def test_update_task_state(self):
        m = UpdateTaskStateInput(
            task_id="t1",
            expected_revision=3,
            state="active",
        )
        assert m.expected_revision == 3


# ---------------------------------------------------------------------------
# MemoryCandidate
# ---------------------------------------------------------------------------


class TestMemoryCandidate:
    def test_round_trip(self):
        mc = MemoryCandidate(
            project_id="p1",
            run_id="r1",
            idempotency_key="k1",
            memories=[
                {
                    "type": "adr",
                    "title": "X",
                    "content": "Y",
                    "scope": "project",
                }
            ],
        )
        data = mc.model_dump()
        mc2 = MemoryCandidate.model_validate(data)
        assert mc2.project_id == "p1"
        assert mc2.idempotency_key == "k1"
