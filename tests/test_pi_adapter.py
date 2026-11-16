"""Integration tests for the Pi adapter (Phase 3).

Verifies:
- Durable spool persists events when the server is unreachable
- EventClient falls back to spool on failure
- Recursion guard blocks a second extraction in the same run
- PiAdapter captures a full session lifecycle
- flush_spool replays buffered events
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Make adapters importable
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters.shared.event_client import DurableSpool, EventClient, build_event
from adapters.pi.pi_adapter import (
    ExtractionResult,
    PiAdapter,
    PiAdapterConfig,
    RunGuard,
)


# ---------------------------------------------------------------------------
# DurableSpool
# ---------------------------------------------------------------------------


class TestDurableSpool:
    def test_append_and_pending(self, tmp_path: Path):
        spool = DurableSpool("pi", root=tmp_path)
        evt = build_event(
            "run.settled", agent="pi", session_id="s1", run_id="r1",
            payload={"outcome": "completed"},
        )
        spool.append(evt)
        pending = spool.pending()
        assert len(pending) == 1
        assert pending[0]["event"]["event_id"] == evt["event_id"]
        assert pending[0]["status"] == "locally_persisted"

    def test_mark_acknowledged_removes_from_pending(self, tmp_path: Path):
        spool = DurableSpool("pi", root=tmp_path)
        evt = build_event("run.settled", agent="pi", session_id="s1", run_id="r1")
        spool.append(evt)
        spool.mark_acknowledged(evt["event_id"])
        assert spool.pending() == []

    def test_clear_acked(self, tmp_path: Path):
        spool = DurableSpool("pi", root=tmp_path)
        e1 = build_event("run.started", agent="pi", session_id="s1", run_id="r1")
        e2 = build_event("run.settled", agent="pi", session_id="s1", run_id="r1")
        spool.append(e1)
        spool.append(e2)
        spool.mark_acknowledged(e1["event_id"])
        removed = spool.clear_acked()
        assert removed == 1
        remaining = spool.pending()
        assert len(remaining) == 1
        assert remaining[0]["event_id"] == e2["event_id"]

    def test_persistence_across_instances(self, tmp_path: Path):
        spool1 = DurableSpool("pi", root=tmp_path)
        evt = build_event("turn.end", agent="pi", session_id="s1", run_id="r1")
        spool1.append(evt)

        spool2 = DurableSpool("pi", root=tmp_path)
        pending = spool2.pending()
        assert len(pending) == 1
        assert pending[0]["event"]["event_id"] == evt["event_id"]


# ---------------------------------------------------------------------------
# EventClient spool fallback
# ---------------------------------------------------------------------------


class TestEventClientSpoolFallback:
    def test_submit_falls_back_to_spool_when_server_unreachable(self, tmp_path: Path):
        spool = DurableSpool("pi", root=tmp_path)
        client = EventClient("http://127.0.0.1:1", agent="pi", spool=spool)
        evt = build_event("run.started", agent="pi", session_id="s1", run_id="r1")
        result = client.submit(evt)
        assert result["status"] == "spooled"
        assert len(spool.pending()) == 1
        client.close()

    def test_flush_spool_replays_events(self, tmp_path: Path):
        spool = DurableSpool("pi", root=tmp_path)
        client = EventClient("http://127.0.0.1:1", agent="pi", spool=spool)
        e1 = build_event("run.started", agent="pi", session_id="s1", run_id="r1")
        e2 = build_event("run.settled", agent="pi", session_id="s1", run_id="r1")
        client.submit(e1)
        client.submit(e2)
        assert len(spool.pending()) == 2

        # Now simulate the server being reachable: mock the HTTP POST
        with patch("httpx.Client.post") as mock_post:
            from unittest.mock import MagicMock
            resp = MagicMock()
            resp.status_code = 202
            resp.json.return_value = {"status": "created"}
            resp.raise_for_status.return_value = None
            mock_post.return_value = resp

            result = client.flush_spool()
            assert result["flushed"] == 2
            assert spool.pending() == []
        client.close()


# ---------------------------------------------------------------------------
# RunGuard (recursion prevention)
# ---------------------------------------------------------------------------


class TestRunGuard:
    def test_allows_one_extraction_per_run(self):
        guard = RunGuard()
        assert guard.allow_extraction("r1") is True
        guard.mark_extraction_attempted("r1")
        assert guard.allow_extraction("r1") is False

    def test_blocks_when_origin_is_memory_extraction(self):
        guard = RunGuard()
        guard.mark_extraction_origin("r1")
        assert guard.allow_extraction("r1") is False

    def test_different_runs_independent(self):
        guard = RunGuard()
        guard.mark_extraction_attempted("r1")
        assert guard.allow_extraction("r1") is False
        assert guard.allow_extraction("r2") is True

    def test_reset_clears_guard(self):
        guard = RunGuard()
        guard.mark_extraction_attempted("r1")
        guard.reset("r1")
        assert guard.allow_extraction("r1") is True


# ---------------------------------------------------------------------------
# PiAdapter full lifecycle
# ---------------------------------------------------------------------------


class TestPiAdapterLifecycle:
    def _make_adapter(self, tmp_path: Path, server_url: str = "http://127.0.0.1:1") -> PiAdapter:
        cfg = PiAdapterConfig(
            project_id="proj-1",
            workspace_id="ws-1",
            task_id="task-1",
            spool_root=str(tmp_path),
            server_url=server_url,
        )
        return PiAdapter(cfg)

    def test_full_lifecycle_spools_all_events(self, tmp_path: Path):
        """When the server is unreachable, every event is spooled locally."""
        adapter = self._make_adapter(tmp_path)
        try:
            adapter.on_session_start("s1", "pi-native-1")
            adapter.on_run_started("r1", "s1", "sha-start")
            adapter.on_turn_end("r1", "s1", 1)
            adapter.on_session_before_compact("r1", "s1", "context compressed")
            adapter.on_run_settled(
                "r1", "s1", "completed",
                head_sha_end="sha-end",
                had_code_changes=True,
            )
            # Extraction requested → submit a result
            result = ExtractionResult(
                run_id="r1",
                capture_result="captured",
                handoff={
                    "summary": "Auth migration 50%",
                    "completed": ["token gen"],
                    "pending": ["integration tests"],
                },
                memories=[
                    {"type": "problem_solution", "title": "JWT refresh", "content": "Use /api/refresh", "scope": "project"},
                ],
            )
            adapter.submit_extraction_result("r1", "s1", result)
            adapter.on_session_shutdown("s1")
        finally:
            adapter.close()

        spool = DurableSpool("pi", root=tmp_path)
        pending = spool.pending()
        # Expected: session.start, run.started, turn.end, session.compacted,
        #          run.settled, memory.extraction_requested,
        #          memory.extraction_completed = 7 events
        # (session_shutdown flushes, so all should be spooled)
        types = [p["event"]["event_type"] for p in pending]
        assert "session.start" in types
        assert "run.started" in types
        assert "turn.end" in types
        assert "session.compacted" in types
        assert "run.settled" in types
        assert "memory.extraction_requested" in types
        assert "memory.extraction_completed" in types

    def test_no_extraction_for_trivial_completed_run(self, tmp_path: Path):
        """A completed run with no code changes and no task significance
        should NOT request extraction."""
        adapter = self._make_adapter(tmp_path)
        try:
            adapter.on_session_start("s1")
            adapter.on_run_started("r1", "s1")
            adapter.on_run_settled("r1", "s1", "completed")
        finally:
            adapter.close()

        spool = DurableSpool("pi", root=tmp_path)
        types = [p["event"]["event_type"] for p in spool.pending()]
        assert "memory.extraction_requested" not in types

    def test_recursion_guard_blocks_double_extraction(self, tmp_path: Path):
        """Even if the caller tries to trigger extraction twice for the
        same run, only the first is allowed."""
        adapter = self._make_adapter(tmp_path)
        try:
            adapter.on_session_start("s1")
            adapter.on_run_started("r1", "s1")

            # First settle → extraction requested
            adapter.on_run_settled(
                "r1", "s1", "failed", had_code_changes=True
            )

            # Simulate the extension asking again (e.g. on a retry path)
            # The guard should refuse because extraction was already attempted.
            assert adapter.guard.allow_extraction("r1") is False
        finally:
            adapter.close()

    def test_no_durable_memory_is_legal_empty_result(self, tmp_path: Path):
        """A 'no_durable_memory' result is valid and does not create handoff."""
        adapter = self._make_adapter(tmp_path)
        try:
            adapter.on_session_start("s1")
            adapter.on_run_started("r1", "s1")
            adapter.on_run_settled("r1", "s1", "completed", had_code_changes=True)
            result = ExtractionResult(
                run_id="r1",
                capture_result="no_durable_memory",
            )
            adapter.submit_extraction_result("r1", "s1", result)
        finally:
            adapter.close()

        spool = DurableSpool("pi", root=tmp_path)
        types = [p["event"]["event_type"] for p in spool.pending()]
        assert "memory.extraction_completed" in types
        # Find that event and verify payload
        for p in spool.pending():
            if p["event"]["event_type"] == "memory.extraction_completed":
                payload = p["event"]["payload"]
                assert payload["capture_result"] == "no_durable_memory"
                assert payload.get("result") == "no_durable_memory"
                assert "handoff" not in payload
                break
