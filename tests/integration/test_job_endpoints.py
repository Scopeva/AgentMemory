"""HTTP job status / retry endpoint tests (GET /v1/jobs/{id}, POST /v1/admin/jobs/{id}/retry)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def app_env(tmp_path: Path):
    """Set env vars for a fresh DB and build the FastAPI app with TestClient."""
    from agent_memory.config import DatabaseConfig, load_config
    from agent_memory.main import create_app

    db_path = tmp_path / "memory.db"
    os.environ["AGENT_MEMORY_DATABASE_PATH"] = str(db_path)
    os.environ["AGENT_MEMORY_CONFIG_PATH"] = ""
    os.environ["AGENT_MEMORY_EMBEDDING_ENABLED"] = "false"
    yield str(db_path)


def _make_app(db_path: str):
    from agent_memory.config import DatabaseConfig, load_config
    from agent_memory.main import create_app

    import asyncio

    from agent_memory.storage.database import Database

    db = Database(DatabaseConfig(path=db_path))
    asyncio.run(db.migrate())
    return create_app(load_config())


def _client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


class TestJobEndpoints:
    def test_get_job_404(self, app_env: str):
        app = _make_app(app_env)
        client = _client(app)
        with client:
            resp = client.get("/v1/jobs/nonexistent-job-id")
        assert resp.status_code == 404

    def test_get_job_status(self, app_env: str):
        import uuid

        app = _make_app(app_env)
        client = _client(app)
        job_id = str(uuid.uuid4())
        with client:
            client.post(
                "/v1/events",
                json={
                    "event_id": str(uuid.uuid4()),
                    "kind": "session_start",
                    "agent": "pi",
                    "run_id": "run-1",
                    "sequence_no": 1,
                    "project_id": "proj-1",
                    "workspace_id": "ws-1",
                    "occurred_at": "2026-01-01T00:00:00Z",
                    "payload": {},
                },
            )
            # Directly seed a pending index job
            import aiosqlite

            async def _seed():
                conn = await aiosqlite.connect(app_env)
                await conn.execute(
                    "INSERT INTO index_jobs (job_id, memory_id, project_id, job_type, status, attempts, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'index', 'pending', 0, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
                    (job_id, "mem-1", "proj-1"),
                )
                await conn.commit()
                await conn.close()

            import asyncio

            asyncio.run(_seed())

            resp = client.get(f"/v1/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] == "pending"

    def test_retry_failed_job(self, app_env: str):
        import uuid
        import asyncio
        import aiosqlite

        app = _make_app(app_env)
        client = _client(app)
        job_id = str(uuid.uuid4())

        async def _seed_failed():
            conn = await aiosqlite.connect(app_env)
            await conn.execute(
                "INSERT INTO index_jobs (job_id, memory_id, project_id, job_type, status, attempts, error, created_at, updated_at) "
                "VALUES (?, ?, ?, 'index', 'failed', 1, 'boom', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
                (job_id, "mem-1", "proj-1"),
            )
            await conn.commit()
            await conn.close()

        asyncio.run(_seed_failed())

        with client:
            resp = client.post(f"/v1/admin/jobs/{job_id}/retry")
        assert resp.status_code == 200
        assert resp.json()["action"] == "reset_to_pending"

        # Verify status flipped to pending
        async def _check():
            conn = await aiosqlite.connect(app_env)
            row = await (await conn.execute("SELECT status FROM index_jobs WHERE job_id=?", (job_id,))).fetchone()
            await conn.close()
            return row[0]

        assert asyncio.run(_check()) == "pending"

    def test_retry_non_failed_job_409(self, app_env: str):
        import uuid
        import asyncio
        import aiosqlite

        app = _make_app(app_env)
        client = _client(app)
        job_id = str(uuid.uuid4())

        async def _seed_pending():
            conn = await aiosqlite.connect(app_env)
            await conn.execute(
                "INSERT INTO index_jobs (job_id, memory_id, project_id, job_type, status, attempts, created_at, updated_at) "
                "VALUES (?, ?, ?, 'index', 'pending', 0, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
                (job_id, "mem-1", "proj-1"),
            )
            await conn.commit()
            await conn.close()

        asyncio.run(_seed_pending())

        with client:
            resp = client.post(f"/v1/admin/jobs/{job_id}/retry")
        assert resp.status_code == 409
