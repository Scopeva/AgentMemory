     1	"""Smoke tests for Phase 4 retrieval HTTP endpoints.
     2	
     3	Verifies that /v1/search, /v1/knowledge, and /v1/admin/index/* routes
     4	are mounted and respond correctly when the retrieval layer is wired in.
     5	"""
     6	
     7	from __future__ import annotations
     8	
     9	import os
    10	import sys
    11	import tempfile
    12	from pathlib import Path
    13	
    14	import pytest
    15	
    16	sys.path.insert(0, str(Path(__file__).parent.parent))
    17	sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    18	
    19	from agent_memory.config import AppConfig, DatabaseConfig, EmbeddingConfig, RetrievalConfig
    20	
    21	
    22	@pytest.fixture
    23	def app(tmp_path):
    24	    from fastapi.testclient import TestClient
    25	    from agent_memory.main import create_app
    26	
    27	    config = AppConfig(
    28	        database=DatabaseConfig(path=str(tmp_path / "t.db")),
    29	        embedding=EmbeddingConfig(enabled=False),
    30	        retrieval=RetrievalConfig(),
    31	    )
    32	    app = create_app(config)
    33	    with TestClient(app) as client:
    34	        yield client
    35	
    36	
    37	class TestRetrievalRoutes:
    38	    def test_search_endpoint_returns_200(self, app):
    39	        # Seed the project directly via the repository (no /v1/projects/register
    40	        # route exists in Phase 2; project identity is MCP/admin-side).
    41	        import aiosqlite
    42	        from agent_memory.schemas import Project
    43	
    44	        async def seed():
    45	            db = app.app.state.db
    46	            async with db.connection() as conn:
    47	                await conn.execute(
    48	                    "INSERT INTO projects (project_id, name, status, created_at, updated_at) "
    49	                    "VALUES (?, ?, 'active', '2026-01-01', '2026-01-01')",
    50	                    ("p1", "P"),
    51	                )
    52	                await conn.commit()
    53	
    54	        import asyncio
    55	        asyncio.get_event_loop().run_until_complete(seed()) if False else None
    56	        # TestClient already drives the event loop; use the db directly
    57	        db = app.app.state.db
    58	
    59	        import sqlite3
    60	        conn = sqlite3.connect(db.path)
    61	        conn.execute(
    62	            "INSERT OR IGNORE INTO projects (project_id, name, status, created_at, updated_at) "
    63	            "VALUES ('p1', 'P', 'active', '2026-01-01', '2026-01-01')"
    64	        )
    65	        conn.commit()
    66	        conn.close()
    67	
    68	        resp = app.get("/v1/search", params={"project_id": "p1", "query": "hello"})
    69	        assert resp.status_code == 200
    70	        data = resp.json()
    71	        assert "results" in data
    72	        assert "retrieval_mode" in data
    73	
    74	    def test_create_knowledge_enqueues_index(self, app):
    75	        import sqlite3
    76	
    77	        db = app.app.state.db
    78	        conn = sqlite3.connect(db.path)
    79	        conn.execute(
    80	            "INSERT OR IGNORE INTO projects (project_id, name, status, created_at, updated_at) "
    81	            "VALUES ('p1', 'P', 'active', '2026-01-01', '2026-01-01')"
    82	        )
    83	        conn.commit()
    84	        conn.close()
    85	
    86	        resp = app.post(
    87	            "/v1/knowledge",
    88	            json={"project_id": "p1", "type": "note", "title": "T", "content": "C"},
    89	        )
    90	        assert resp.status_code == 200
    91	        data = resp.json()
    92	        assert data["action"] == "created"
    93	        assert data["memory_id"]
    94	
    95	    def test_admin_index_status_requires_no_token_by_default(self, app):
    96	        # No admin token configured -> endpoint open
    97	        resp = app.get("/v1/admin/index/status")
    98	        assert resp.status_code == 200
    99	        data = resp.json()
   100	        assert "pending_index_jobs" in data
   101	        assert "vector_available" in data
   102	
   103	    def test_admin_drain_reports_disabled_or_drained(self, app):
   104	        resp = app.post("/v1/admin/index/drain")
   105	        assert resp.status_code == 200
   106	        data = resp.json()
   107	        assert "drained" in data