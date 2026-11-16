     1	"""End-to-end test: Pi adapter spools events → flush to a live server.
     2	
     3	Simulates the full Phase 3 flow:
     4	1. PiAdapter (with unreachable server) spools all lifecycle events
     5	2. Server comes "online" (mocked) and spool is flushed
     6	3. Server receives and persists the events idempotently
     7	"""
     8	
     9	from __future__ import annotations
    10	
    11	import json
    12	import os
    13	import sys
    14	import tempfile
    15	from pathlib import Path
    16	from unittest.mock import MagicMock, patch
    17	
    18	import pytest
    19	import pytest_asyncio
    20	
    21	# Make adapters importable
    22	sys.path.insert(0, str(Path(__file__).parent.parent))
    23	
    24	from adapters.pi.pi_adapter import ExtractionResult, PiAdapter, PiAdapterConfig
    25	from adapters.shared.event_client import DurableSpool
    26	
    27	from agent_memory.config import DatabaseConfig
    28	from agent_memory.schemas import EventEnvelope, AgentType
    29	from agent_memory.services import core
    30	from agent_memory.storage.database import Database
    31	from agent_memory.storage.repositories import projects, sessions, tasks
    32	from agent_memory.schemas import Project, Session, Run, Task, TaskStatus
    33	
    34	
    35	@pytest.fixture
    36	async def server_db():
    37	    """A migrated database acting as the memory server."""
    38	    with tempfile.TemporaryDirectory() as tmp:
    39	        db = Database(DatabaseConfig(path=str(Path(tmp) / "server.db")))
    40	        await db.migrate()
    41	        yield db
    42	
    43	
    44	@pytest.fixture
    45	def pi_adapter_env(tmp_path: Path, server_db: Database):
    46	    """Set up a Pi adapter pointing at an unreachable server + temp spool."""
    47	    return {
    48	        "tmp_path": tmp_path,
    49	        "server_db": server_db,
    50	        "server_url": "http://127.0.0.1:1",  # unreachable
    51	    }
    52	
    53	
    54	class TestPiToServerFlow:
    55	    def test_spooled_events_flush_to_server(
    56	        self, pi_adapter_env: dict, server_db: Database
    57	    ):
    58	        tmp_path: Path = pi_adapter_env["tmp_path"]
    59	        server_url: str = pi_adapter_env["server_url"]
    60	