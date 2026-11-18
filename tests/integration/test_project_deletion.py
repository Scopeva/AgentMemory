"""Project deletion must remove every direct foreign-key dependent row."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent_memory.config import AppConfig, DatabaseConfig, EmbeddingConfig


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient

    from agent_memory.main import create_app

    monkeypatch.setenv("AGENT_MEMORY_ADMIN_TOKEN", "test-token")
    app = create_app(
        AppConfig(
            database=DatabaseConfig(path=str(tmp_path / "memory.db")),
            embedding=EmbeddingConfig(enabled=False),
        )
    )
    with TestClient(app) as test_client:
        yield test_client


def test_delete_project_removes_all_fk_dependents(client):
    db_path = client.app.state.db.path
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        INSERT INTO projects VALUES ('p1', 'Project', 'active', '2026-01-01', '2026-01-01');
        INSERT INTO repositories VALUES ('repo-1', 'p1', 'hash', 'fingerprint', '2026-01-01');
        INSERT INTO workspaces VALUES ('ws-1', 'repo-1', '/tmp/project', NULL, '2026-01-01');
        INSERT INTO sessions VALUES ('session-1', 'pi', NULL, 'ws-1', '2026-01-01');
        INSERT INTO tasks VALUES ('task-1', 'p1', 'Task', 'active', 1, NULL, '2026-01-01', '2026-01-01');
        INSERT INTO runs (run_id, task_id, session_id, status, started_at, project_id)
            VALUES ('run-1', 'task-1', 'session-1', 'completed', '2026-01-01', 'p1');
        INSERT INTO events (event_id, run_id, event_type, sequence_no, payload_json, created_at, project_id)
            VALUES ('event-1', 'run-1', 'stop', 1, '{}', '2026-01-01', 'p1');
        INSERT INTO checkpoints VALUES ('checkpoint-1', 'run-1', NULL, 'done', '2026-01-01');
        INSERT INTO handoffs (handoff_id, task_id, source_agent, summary, created_at, updated_at)
            VALUES ('handoff-1', 'task-1', 'pi', 'done', '2026-01-01', '2026-01-01');
        INSERT INTO knowledge VALUES ('memory-1', 'p1', 'project', 'note', 'accepted', 'Title', 'Content', 1, NULL, NULL, '2026-01-01', '2026-01-01');
        INSERT INTO knowledge_revisions VALUES ('memory-1', 1, 'Title', 'Content', 'accepted', 'system', '2026-01-01');
        INSERT INTO knowledge_sources VALUES ('source-1', 'memory-1', 'agent_statement', 'evidence', NULL, '2026-01-01');
        INSERT INTO chunks (chunk_id, project_id, memory_id, text, indexed_at)
            VALUES ('memory-1:0', 'p1', 'memory-1', 'Content', '2026-01-01');
        INSERT INTO chunks_fts VALUES ('memory-1:0', 'p1', 'memory-1', 'knowledge', 'Title', '', 'Content', 1);
        INSERT INTO index_jobs VALUES ('index-1', 'memory-1', 'p1', 'index', 'pending', 0, NULL, '2026-01-01', '2026-01-01');
        INSERT INTO memory_candidates VALUES ('candidate-1', 'p1', 'run-1', 'key', '{}', 'pending', '2026-01-01', '2026-01-01');
        INSERT INTO approvals VALUES ('approval-1', 'candidate-1', 'reviewed', 'admin', '2026-01-01');
        """
    )
    conn.commit()
    conn.close()

    response = client.delete("/v1/projects/p1", headers={"X-Admin-Token": "test-token"})
    assert response.status_code == 200
    assert response.json()["removed"] is True

    conn = sqlite3.connect(db_path)
    tables = [
        "projects",
        "repositories",
        "workspaces",
        "tasks",
        "runs",
        "events",
        "checkpoints",
        "handoffs",
        "knowledge",
        "knowledge_revisions",
        "knowledge_sources",
        "chunks",
        "chunks_fts",
        "index_jobs",
        "memory_candidates",
        "approvals",
    ]
    assert {
        table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in tables
    } == {table: 0 for table in tables}
    conn.close()
