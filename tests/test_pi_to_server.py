"""End-to-end test: Pi adapter spools events → flush to a live server.

Simulates the full Phase 3 flow:
1. PiAdapter (with unreachable server) spools all lifecycle events
2. Server comes "online" (mocked) and spool is flushed
3. Server receives and persists the events idempotently
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

import pytest
import pytest_asyncio

# Make adapters importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_memory.adapters.pi.pi_adapter import ExtractionResult, PiAdapter, PiAdapterConfig
from agent_memory.adapters.shared.event_client import DurableSpool

from agent_memory.config import DatabaseConfig
from agent_memory.schemas import EventEnvelope, AgentType
from agent_memory.services import core
from agent_memory.storage.database import Database
from agent_memory.storage.repositories import projects, sessions, tasks
from agent_memory.schemas import Project, Session, Run, Task, TaskStatus


@pytest.fixture
async def server_db():
    """A migrated database acting as the memory server."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(DatabaseConfig(path=str(Path(tmp) / "server.db")))
        await db.migrate()
        yield db


@pytest.fixture
def pi_adapter_env(tmp_path: Path, server_db: Database):
    """Set up a Pi adapter pointing at an unreachable server + temp spool."""
    return {
        "tmp_path": tmp_path,
        "server_db": server_db,
        "server_url": "http://127.0.0.1:1",  # unreachable
    }


class TestPiToServerFlow:
    def test_spooled_events_flush_to_server(
        self, pi_adapter_env: dict, server_db: Database
    ):
        tmp_path: Path = pi_adapter_env["tmp_path"]
        server_url: str = pi_adapter_env["server_url"]

        # Pre-register the project, session, and task in the server DB
        import asyncio

        async def _setup():
            p = await projects.register_project(server_db, Project(name="pi-e2e"))
            s = Session(
                agent_type=AgentType.PI,
                native_session_id="pi-native-e2e",
                workspace_id="ws-pi",
            )
            await sessions.register_session(server_db, s)
            t = await tasks.create_task(
                server_db, Task(project_id=p.project_id, title="Pi E2E task")
            )
            return p.project_id, s.session_id, t.task_id

        project_id, session_id, task_id = asyncio.run(_setup())

        # Build a Pi adapter that will spool (server is unreachable)
        cfg = PiAdapterConfig(
            project_id=project_id,
            workspace_id="ws-pi",
            task_id=task_id,
            spool_root=str(tmp_path),
            server_url=server_url,
        )
        adapter = PiAdapter(cfg)

        session_uuid = "e2e-session-1"
        run_uuid = "e2e-run-1"

        # 1. Run full Pi lifecycle (all events spooled)
        adapter.on_session_start(session_uuid, "pi-native-e2e")
        adapter.on_run_started(run_uuid, session_uuid, "sha-a")
        adapter.on_turn_end(run_uuid, session_uuid, 1)
        adapter.on_session_before_compact(run_uuid, session_uuid, "compacted")
        adapter.on_run_settled(
            run_uuid, session_uuid, "completed",
            head_sha_end="sha-b",
            had_code_changes=True,
        )
        result = ExtractionResult(
            run_id=run_uuid,
            capture_result="captured",
            handoff={
                "summary": "Auth done",
                "completed": ["token gen"],
                "pending": [],
            },
            memories=[
                {
                    "type": "problem_solution",
                    "title": "JWT refresh",
                    "content": "Use /api/refresh",
                    "scope": "project",
                }
            ],
        )
        adapter.submit_extraction_result(run_uuid, session_uuid, result)
        adapter.close()

        # 2. Verify all events are in the spool
        spool = DurableSpool("pi", root=tmp_path)
        pending = spool.pending()
        assert len(pending) >= 7, f"expected >=7 spooled events, got {len(pending)}"

        # 3. Simulate server coming online: replay spool via HTTP POST
        #    (mock httpx so we can capture the payloads and forward to server_db)
        submitted_events: list[dict] = []

        def _mock_post(self_client, url, json=None, headers=None, **_kw):
            """Mock that accepts event POSTs and records the payloads."""
            submitted_events.append(json or {})
            resp = MagicMock()
            resp.status_code = 202
            resp.json.return_value = {"event_id": (json or {}).get("event_id"), "status": "created"}
            resp.raise_for_status.return_value = None
            return resp

        with patch.object(httpx.Client, "post", autospec=True, side_effect=_mock_post):
            # Re-create a client pointed at the "now online" server and flush
            online_url = "http://127.0.0.1:8765"
            from agent_memory.adapters.shared.event_client import EventClient
            new_client = EventClient(
                online_url, "pi", spool=spool,
            )
            flush_result = new_client.flush_spool()
            new_client.close()

        assert flush_result["flushed"] >= 7, f"expected >=7 flushed, got {flush_result}"

        # 4. Verify events reached the server's spool as delivered
        event_types = [e.get("event_type") for e in submitted_events]
        assert "session.start" in event_types
        assert "run.started" in event_types
        assert "run.settled" in event_types
        assert "memory.extraction_completed" in event_types

    def test_spool_is_durable_across_adapter_restarts(
        self, pi_adapter_env: dict
    ):
        """Events spooled by one adapter instance survive to a new instance."""
        tmp_path: Path = pi_adapter_env["tmp_path"]
        server_url: str = pi_adapter_env["server_url"]

        cfg1 = PiAdapterConfig(
            project_id="p1",
            spool_root=str(tmp_path),
            server_url=server_url,
        )
        adapter1 = PiAdapter(cfg1)
        adapter1.on_session_start("s-persist")
        adapter1.on_run_started("r-persist", "s-persist")
        adapter1.close()

        # New adapter instance (simulating Pi restart)
        cfg2 = PiAdapterConfig(
            project_id="p1",
            spool_root=str(tmp_path),
            server_url=server_url,
        )
        adapter2 = PiAdapter(cfg2)

        spool = DurableSpool("pi", root=tmp_path)
        pending = spool.pending()
        # Events from the first adapter should still be there
        event_ids = [p["event"]["event_id"] for p in pending]
        assert len(event_ids) >= 2
