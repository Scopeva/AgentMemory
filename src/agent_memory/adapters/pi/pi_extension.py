"""Packaged legacy Pi extension entry point.

This module is loaded by Pi's extension mechanism (JS/TS). It bridges
Pi's lifecycle hooks to the Python adapter so that all events and
memory extraction results are persisted through the shared EventClient.

Since Pi extensions run in a JS/TS runtime, this file is a thin wrapper
that shells out to a small Python helper script for event persistence.
The Python helper is ``_pi_helper.py`` in the same directory.

Configuration (env vars):
  AGENT_MEMORY_SERVER_URL   Memory server base URL (default http://127.0.0.1:8765)
  AGENT_MEMORY_SPOOL_ROOT   Spool root directory
  AGENT_MEMORY_PROJECT_ID   Project this Pi session belongs to
  AGENT_MEMORY_WORKSPACE_ID Workspace / worktree identifier
  AGENT_MEMORY_TASK_ID      Logical task being worked on
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from typing import Any, Optional

# The Python helper script lives next to this extension.
_HELPER = os.path.join(os.path.dirname(__file__), "_pi_helper.py")


def _invoke_helper(action: str, payload: dict) -> Optional[dict]:
    """Call the Python helper for a given action.

    Returns the parsed JSON result, or None if the helper failed.
    """
    cmd = [sys.executable, _HELPER, action, json.dumps(payload)]
    env = os.environ.copy()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        if result.returncode == 0:
            out = result.stdout.strip()
            if out:
                return json.loads(out)
        else:
            # Log to stderr; never block Pi on helper failure
            print(f"[pi-memory-adapter] helper error: {result.stderr.strip()}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[pi-memory-adapter] helper call failed: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Pi extension API (called by Pi's lifecycle hooks)
# ---------------------------------------------------------------------------


def on_session_start(session_id: str, native_session_id: str = "") -> None:
    """Called when Pi starts a new session."""
    _invoke_helper("session_start", {
        "session_id": session_id,
        "native_session_id": native_session_id,
    })


def on_run_started(run_id: str, session_id: str, head_sha: str = "") -> None:
    """Called when a new run begins."""
    _invoke_helper("run_started", {
        "run_id": run_id,
        "session_id": session_id,
        "head_sha": head_sha,
    })


def on_turn_end(run_id: str, session_id: str, turn_index: int) -> None:
    """Called at the end of each model turn."""
    _invoke_helper("turn_end", {
        "run_id": run_id,
        "session_id": session_id,
        "turn_index": turn_index,
    })


def on_session_before_compact(run_id: str, session_id: str, summary: str = "") -> None:
    """Called before Pi compresses its context."""
    _invoke_helper("session_before_compact", {
        "run_id": run_id,
        "session_id": session_id,
        "summary": summary,
    })


def on_run_settled(
    run_id: str,
    session_id: str,
    outcome: str,
    *,
    head_sha_end: str = "",
    had_code_changes: bool = False,
    task_significant: bool = False,
) -> None:
    """Called when a run finishes (after retries/continuations).

    If the adapter decides extraction is warranted, this returns a dict
    with ``"extract": True`` so the caller knows to invoke the model for
    one structured extraction and then call ``submit_extraction_result``.
    """
    result = _invoke_helper("run_settled", {
        "run_id": run_id,
        "session_id": session_id,
        "outcome": outcome,
        "head_sha_end": head_sha_end,
        "had_code_changes": had_code_changes,
        "task_significant": task_significant,
    })
    if result and result.get("extract"):
        # The caller (Pi) should now ask the model for a structured extraction
        # and call submit_extraction_result below.
        pass


def submit_extraction_result(
    run_id: str,
    session_id: str,
    capture_result: str,
    handoff: Optional[dict] = None,
    memories: Optional[list[dict]] = None,
) -> None:
    """Submit the structured extraction result after the model produced it."""
    _invoke_helper("extraction_result", {
        "run_id": run_id,
        "session_id": session_id,
        "capture_result": capture_result,
        "handoff": handoff or {},
        "memories": memories or [],
    })


def on_run_interrupted(run_id: str, session_id: str, reason: str = "") -> None:
    """Called when a run is aborted."""
    _invoke_helper("run_interrupted", {
        "run_id": run_id,
        "session_id": session_id,
        "reason": reason,
    })


def on_session_shutdown(session_id: str) -> None:
    """Called when the Pi session closes; flushes the spool."""
    _invoke_helper("session_shutdown", {
        "session_id": session_id,
    })


# ---------------------------------------------------------------------------
# Capability negotiation (Phase 8.4 in the spec)
# ---------------------------------------------------------------------------


def get_capabilities() -> dict:
    """Return the capabilities this adapter actually supports.

    These values must come from the actual Pi extension API, not from
    hard-coded agent names. The Memory Server uses them to decide how
    to handle extraction and recovery.
    """
    return {
        "agent": "pi",
        "adapter_version": "1.0.0",
        "session_lifecycle": True,
        "turn_completion": True,
        "pre_compaction": True,
        "controlled_continuation": True,  # Pi can request one final continuation
        "session_resume": True,
        "durable_spool": True,
    }
