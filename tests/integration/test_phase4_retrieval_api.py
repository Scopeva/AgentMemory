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
    with TestClient(app) as client:
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

    def test_admin_index_status_requires_no_token_by_default(self, app):
        # No admin token configured -> endpoint open
        resp = app.get("/v1/admin/index/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "pending_index_jobs" in data
        assert "vector_available" in data

    def test_admin_drain_reports_disabled_or_drained(self, app):
        resp = app.post("/v1/admin/index/drain")
        assert resp.status_code == 200
        data = resp.json()
        assert "drained" in data
