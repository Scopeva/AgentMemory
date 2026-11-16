     1	"""Integration tests for the Codex and OpenCode adapters (Phase 5).
     2	
     3	Verifies:
     4	- Durable spool persists events when the server is unreachable
     5	- Codex hooks emit the correct event sequence (session.start, run.started,
     6	  session.compacted, run.settled)
     7	- OpenCode plugin hooks emit the correct event sequence (session.start,
     8	  run.started, turn.start, turn.end, run.settled)
     9	- EventEnvelope payloads match the Phase 0 contract (agent, session_id,
    10	  run_id, sequence_no, schema_version)
    11	- flush_spool replays buffered events to a live (mocked) server
    12	"""
    13	
    14	from __future__ import annotations
    15	
    16	import json
    17	import sys
    18	from pathlib import Path
    19	from unittest.mock import patch
    20	
    21	import pytest
    22	
    23	# Make adapters importable
    24	sys.path.insert(0, str(Path(__file__).parent.parent))
    25	
    26	from adapters.codex.codex_adapter import CodexAdapter, CodexAdapterConfig
    27	from adapters.opencode.opencode_adapter import OpenCodeAdapter, OpenCodeAdapterConfig
    28	from adapters.shared.event_client import build_event
    29	
    30	
    31	def _read_spool(agent: str, root: Path) -> list[dict]:
    32	    """Read all spool records for an agent."""
    33	    spool_path = root / agent / "spool.jsonl"
    34	    if not spool_path.exists():
    35	        return []
    36	    out = []
    37	    for line in spool_path.read_text(encoding="utf-8").splitlines():
    38	        if line.strip():
    39	            out.append(json.loads(line))
    40	    return out
    41	
    42	
    43	def _event_types(records: list[dict]) -> list[str]:
    44	    """Extract event_type from each spool record, deduped, in order of first appearance."""
    45	    seen: list[str] = []
    46	    for rec in records:
    47	        et = rec.get("event", {}).get("event_type", "")
    48	        if et and et not in seen:
    49	            seen.append(et)
    50	    return seen
    51	
    52	
    53	class TestCodexAdapter:
    54	    def test_full_lifecycle_spooled_when_unreachable(self, tmp_path: Path):
    55	        """All hook events are spooled when the server is unreachable."""
    56	        cfg = CodexAdapterConfig(server_url="http://127.0.0.1:1", spool_root=str(tmp_path))
    57	        adapter = CodexAdapter(cfg)
    58	
    59	        adapter.on_session_start("s1", "native1", "abc123")
    60	        adapter.on_pre_compact("s1", "context summary")
    61	        adapter.on_stop("s1", "completed", "def456")
    62	        adapter.on_session_end("s1")
    63	        adapter.close()
    64	
    65	        records = _read_spool("codex", tmp_path)
    66	        # session.start + run.started + session.compacted + run.settled
    67	        # (duplicated by earlier manual test runs in the same spool dir are
    68	        #  not possible here because tmp_path is fresh per-test)
    69	        types = _event_types(records)
    70	        assert "session.start" in types
    71	        assert "run.started" in types
    72	        assert "session.compacted" in types
    73	        assert "run.settled" in types
    74	
    75	    def test_event_envelope_contract(self, tmp_path: Path):
    76	        """Each spooled event matches the Phase 0 EventEnvelope fields."""
    77	        cfg = CodexAdapterConfig(server_url="http://127.0.0.1:1", spool_root=str(tmp_path))
    78	        adapter = CodexAdapter(cfg)
    79	        adapter.on_session_start("s1", "native1", "abc123")
    80	        adapter.on_stop("s1", "completed", "def456")
    81	        adapter.close()
    82	
    83	        records = _read_spool("codex", tmp_path)
    84	        assert records, "expected at least one spooled event"
    85	        for rec in records:
    86	            evt = rec["event"]
    87	            assert evt["schema_version"] == "1.0"
    88	            assert evt["agent"] == "codex"
    89	            assert evt["session_id"] == "s1"
    90	            assert "event_id" in evt
    91	            assert "sequence_no" in evt
    92	            assert "occurred_at" in evt
    93	
    94	    def test_session_start_without_head_sha_omits_run_started(self, tmp_path: Path):
    95	        """When no head_sha is provided, only session.start is emitted."""
    96	        cfg = CodexAdapterConfig(server_url="http://127.0.0.1:1", spool_root=str(tmp_path))
    97	        adapter = CodexAdapter(cfg)
    98	        adapter.on_session_start("s2", "native2")  # no head_sha
    99	        adapter.close()
   100	
   101	        records = _read_spool("codex", tmp_path)
   102	        types = _event_types(records)
   103	        assert "session.start" in types
   104	        assert "run.started" not in types
   105	
   106	    def test_flush_spool_replays_to_mocked_server(self, tmp_path: Path):
   107	        """Spooled events are replayed when the server becomes available."""
   108	        cfg = CodexAdapterConfig(server_url="http://127.0.0.1:8765", spool_root=str(tmp_path))
   109	        adapter = CodexAdapter(cfg)
   110	
   111	        # Simulate unreachable: manually spool an event
   112	        from adapters.shared.event_client import DurableSpool
   113	        spool = DurableSpool("codex", root=tmp_path)
   114	        evt = build_event(
   115	            "run.settled", agent="codex", session_id="s1", run_id="s1",
   116	            payload={"outcome": "completed"},
   117	        )
   118	        spool.append(evt)
   119	
   120	        # Mock a successful HTTP response
   121	        import httpx
   122	
   123	        def mock_post(self_client, url, json=None, headers=None, **_kw):
   124	            resp = httpx.Response(
   125	                202,
   126	                json={"event_id": json["event_id"], "status": "created"},
   127	                request=httpx.Request("POST", url),
   128	            )
   129	            return resp
   130	
   131	        with patch.object(httpx.Client, "post", autospec=True, side_effect=mock_post):
   132	            result = adapter.flush()
   133	
   134	        assert result["flushed"] >= 1
   135	        # After flush, the event should be acknowledged
   136	        remaining = spool.pending()
   137	        assert len(remaining) == 0
   138	        adapter.close()
   139	
   140	    def test_adapter_uses_codex_agent_tag(self, tmp_path: Path):
   141	        """Events are tagged with agent=codex, not pi or opencode."""
   142	        cfg = CodexAdapterConfig(server_url="http://127.0.0.1:1", spool_root=str(tmp_path))
   143	        adapter = CodexAdapter(cfg)
   144	        adapter.on_session_start("s3", "n3", "sha")
   145	        adapter.close()
   146	
   147	        records = _read_spool("codex", tmp_path)
   148	        assert all(r["event"]["agent"] == "codex" for r in records)
   149	
   150	
   151	class TestOpenCodeAdapter:
   152	    def test_full_lifecycle_spooled_when_unreachable(self, tmp_path: Path):
   153	        """All plugin hook events are spooled when the server is unreachable."""
   154	        cfg = OpenCodeAdapterConfig(server_url="http://127.0.0.1:1", spool_root=str(tmp_path))
   155	        adapter = OpenCodeAdapter(cfg)
   156	
   157	        adapter.on_session_start("s1", "native1", "abc123")
   158	        adapter.on_turn_start("r1", "s1")
   159	        adapter.on_turn_end("r1", "s1")
   160	        adapter.on_session_end("s1", "completed", "def456")
   161	        adapter.close()
   162	
   163	        records = _read_spool("opencode", tmp_path)
   164	        types = _event_types(records)
   165	        assert "session.start" in types
   166	        assert "run.started" in types
   167	        assert "turn.start" in types
   168	        assert "turn.end" in types
   169	        assert "run.settled" in types
   170	
   171	    def test_event_envelope_contract(self, tmp_path: Path):
   172	        """Each spooled event matches the

... [truncated, showing 200/269 lines, 8000/12843 chars]