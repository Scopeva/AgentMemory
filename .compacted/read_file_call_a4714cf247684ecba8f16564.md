     1	"""Integration tests for the Pi adapter (Phase 3).
     2	
     3	Verifies:
     4	- Durable spool persists events when the server is unreachable
     5	- EventClient falls back to spool on failure
     6	- Recursion guard blocks a second extraction in the same run
     7	- PiAdapter captures a full session lifecycle
     8	- flush_spool replays buffered events
     9	"""
    10	
    11	from __future__ import annotations
    12	
    13	import json
    14	import os
    15	import tempfile
    16	from pathlib import Path
    17	from unittest.mock import patch
    18	
    19	import pytest
    20	
    21	# Make adapters importable
    22	import sys
    23	sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    24	
    25	from adapters.shared.event_client import DurableSpool, EventClient, build_event
    26	from adapters.pi.pi_adapter import (
    27	    ExtractionResult,
    28	    PiAdapter,
    29	    PiAdapterConfig,
    30	    RunGuard,
    31	)
    32	
    33	
    34	# ---------------------------------------------------------------------------
    35	# DurableSpool
    36	# ---------------------------------------------------------------------------
    37	
    38	
    39	class TestDurableSpool:
    40	    def test_append_and_pending(self, tmp_path: Path):
    41	        spool = DurableSpool("pi", root=tmp_path)
    42	        evt = build_event(
    43	            "run.settled", agent="pi", session_id="s1", run_id="r1",
    44	            payload={"outcome": "completed"},
    45	        )
    46	        spool.append(evt)
    47	        pending = spool.pending()
    48	        assert len(pending) == 1
    49	        assert pending[0]["event"]["event_id"] == evt["event_id"]
    50	        assert pending[0]["status"] == "locally_persisted"
    51	
    52	    def test_mark_acknowledged_removes_from_pending(self, tmp_path: Path):
    53	        spool = DurableSpool("pi", root=tmp_path)
    54	        evt = build_event("run.settled", agent="pi", session_id="s1", run_id="r1")
    55	        spool.append(evt)
    56	        spool.mark_acknowledged(evt["event_id"])
    57	        assert spool.pending() == []
    58	
    59	    def test_clear_acked(self, tmp_path: Path):
    60	        spool = DurableSpool("pi", root=tmp_path)