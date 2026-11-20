"""Smoke tests for Phase 4 retrieval HTTP endpoints.

Verifies that /v1/search, /v1/knowledge, and /v1/admin/index/* routes
are mounted and respond correctly when the retrieval layer is wired in.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_memory.config import AppConfig, DatabaseConfig, EmbeddingConfig, RetrievalConfig


@pytest.fixture
def app(tmp_path):
    from fastapi.testclient import TestClient
    from agent_memory.main import create_app

    config = AppConfig(
        database=DatabaseConfig(path=str(tmp_path / "t.db")),
        embedding=EmbeddingConfig(enabled=False),
        retrieval=RetrievalConfig(),
    )
    app = create_app(config)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        yield client


class TestRetrievalRoutes:
    def test_search_endpoint_returns_200(self, app):
        # Seed the project directly (no /v1/projects/register route in Phase 2;
        # project identity is MCP/admin-side).
        self._seed_project(app, "p1")

        resp = app.get("/v1/search", params={"project_id": "p1", "query": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "retrieval_mode" in data

    def test_create_knowledge_enqueues_index(self, app):
        self._seed_project(app, "p1")

        resp = app.post(
            "/v1/knowledge",
            json={"project_id": "p1", "type": "note", "title": "T", "content": "C"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "created"
        assert data["memory_id"]

    @staticmethod
    def _seed_project(app, project_id: str) -> None:
        """Seed a project row via sync sqlite (TestClient owns the DB file)."""
        import sqlite3

        db = app.app.state.db
        conn = sqlite3.connect(db.path)
        conn.execute(
            "INSERT OR IGNORE INTO projects "
            "(project_id, name, status, created_at, updated_at) "
            "VALUES (?, ?, 'active', '2026-01-01', '2026-01-01')",
            (project_id, "P"),
        )
        conn.commit()
        conn.close()

    def test_admin_index_status_fails_closed_without_configuration(self, app):
        resp = app.get("/v1/admin/index/status")
        assert resp.status_code == 503

    def test_admin_routes_require_the_configured_token(self, app, monkeypatch):
        monkeypatch.setenv("AGENT_MEMORY_ADMIN_TOKEN", "test-token")
        assert app.get("/v1/admin/index/status").status_code == 403
        resp = app.get("/v1/admin/index/status", headers={"X-Admin-Token": "test-token"})
        assert resp.status_code == 200
        assert "pending_index_jobs" in resp.json()

        assert app.get("/v1/admin/pending").status_code == 403
        assert app.get("/v1/admin/pending", headers={"X-Admin-Token": "test-token"}).status_code == 200

    def test_admin_drain_reports_disabled_or_drained(self, app, monkeypatch):
        monkeypatch.setenv("AGENT_MEMORY_ADMIN_TOKEN", "test-token")
        resp = app.post("/v1/admin/index/drain", headers={"X-Admin-Token": "test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert "drained" in data

    def test_delete_knowledge_requires_the_configured_token(self, app, monkeypatch):
        self._seed_project(app, "p1")
        created = app.post(
            "/v1/knowledge",
            json={"project_id": "p1", "type": "note", "title": "T", "content": "C"},
        ).json()
        monkeypatch.setenv("AGENT_MEMORY_ADMIN_TOKEN", "test-token")

        path = f"/v1/knowledge/{created['memory_id']}?revision=1"
        assert app.delete(path).status_code == 403
        assert app.delete(path, headers={"X-Admin-Token": "test-token"}).status_code == 200

    def test_blank_search_is_rejected(self, app):
        resp = app.get("/v1/search", params={"project_id": "p1", "query": "   "})
        assert resp.status_code == 422

    def test_mcp_endpoint_initializes(self, app):
        response = app.post(
            "/mcp/",
            headers={"Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1"},
                },
            },
        )
        assert response.status_code == 200
        assert '"name":"agent-memory"' in response.text

    def test_completed_extraction_creates_one_candidate_and_indexes_on_accept(
        self, app, monkeypatch
    ):
        event = {
            "event_id": "extract-once",
            "event_type": "memory.extraction_completed",
            "agent": "pi",
            "session_id": "session-1",
            "run_id": "run-1",
            "project_id": "project-from-event",
            "sequence_no": 1,
            "payload": {
                "memories": [
                    {
                        "type": "decision",
                        "title": "Use WAL",
                        "content": "Keep SQLite in WAL mode.",
                        "scope": "project",
                    }
                ]
            },
        }
        assert app.post("/v1/events", json=event).status_code == 202
        assert app.post("/v1/events", json=event).json()["status"] == "duplicate"

        monkeypatch.setenv("AGENT_MEMORY_ADMIN_TOKEN", "test-token")
        headers = {"X-Admin-Token": "test-token"}
        candidates = app.get(
            "/v1/admin/pending", params={"project_id": "project-from-event"}, headers=headers
        ).json()["candidates"]
        assert len(candidates) == 1
        assert candidates[0]["memory"]["title"] == "Use WAL"

        accepted = app.post(
            f"/v1/admin/approvals/{candidates[0]['candidate_id']}/approve?auto_accept=true",
            headers=headers,
        ).json()
        assert accepted["memory_id"]

        import sqlite3

        conn = sqlite3.connect(app.app.state.db.path)
        project = conn.execute(
            "SELECT project_id FROM projects WHERE project_id = ?", ("project-from-event",)
        ).fetchone()
        run = conn.execute(
            "SELECT run_id, session_id FROM runs WHERE run_id = ?", ("run-1",)
        ).fetchone()
        job = conn.execute(
            "SELECT memory_id, project_id FROM index_jobs WHERE memory_id = ?",
            (accepted["memory_id"],),
        ).fetchone()
        conn.close()
        assert project == ("project-from-event",)
        assert run == ("run-1", "session-1")
        assert job == (accepted["memory_id"], "project-from-event")
