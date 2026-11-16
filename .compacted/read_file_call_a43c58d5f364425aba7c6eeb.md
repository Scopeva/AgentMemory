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
    39	        # Need a project first
    40	        resp = app.post(
    41	            "/v1/projects/register",
    42	            json={"project_id": "p1", "name": "P", "created_at": "2026-01-01", "updated_at": "2026-01-01"},
    43	        )
    44	        # register may be 200/201; either way search should still work
    45	        resp = app.get("/v1/search", params={"project_id": "p1", "query": "hello"})
    46	        assert resp.status_code == 200
    47	        data = resp.json()
    48	        assert "results" in data
    49	        assert "retrieval_mode" in data
    50	
    51	    def test_create_knowledge_enqueues_index(self, app):
    52	        resp = app.post(
    53	            "/v1/projects/register",
    54	            json={"project_id": "p1", "name": "P", "created_at": "2026-01-01", "updated_at": "2026-01-01"},
    55	        )
    56	        resp = app.post(
    57	            "/v1/knowledge",
    58	            json={"project_id": "p1", "type": "note", "title": "T", "content": "C"},
    59	        )
    60	        assert resp.status_code == 200
    61	        data = resp.json()
    62	        assert data["action"] == "created"
    63	        assert data["memory_id"]
    64	
    65	    def test_admin_index_status_requires_no_token_by_default(self, app):
    66	        # No admin token configured -> endpoint open
    67	        resp = app.get("/v1/admin/index/status")
    68	        assert resp.status_code == 200
    69	        data = resp.json()
    70	        assert "pending_index_jobs" in data
    71	        assert "vector_available" in data
    72	
    73	    def test_admin_drain_reports_disabled_or_drained(self, app):
    74	        resp = app.post("/v1/admin/index/drain")
    75	        assert resp.status_code == 200
    76	        data = resp.json()
    77	        assert "drained" in data