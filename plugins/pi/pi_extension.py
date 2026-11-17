#!/usr/bin/env python3
"""Pi extension entry point (installable).

This is the file Pi's extension mechanism loads. It bridges Pi's JS/TS
lifecycle hooks to the Python adapter by shelling out to the helper in
``adapters/pi/_pi_helper.py``.

Configuration is entirely via environment variables (read by the adapter):
  AGENT_MEMORY_REPO_ROOT    path to the repo (so adapters can be imported)
  AGENT_MEMORY_SERVER_URL   default http://127.0.0.1:8765
  AGENT_MEMORY_PROJECT_ID
  AGENT_MEMORY_WORKSPACE_ID
  AGENT_MEMORY_TASK_ID

Install: drop this file into Pi's extensions directory and point Pi's
lifecycle hooks at the functions below. See plugins/pi/install_pi.sh.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

# Resolve the repo root so we can find the shared adapter helper.
_REPO_ROOT = os.environ.get("AGENT_MEMORY_REPO_ROOT")
if not _REPO_ROOT:
    _here = os.path.dirname(os.path.abspath(__file__))
    _candidate = os.path.abspath(os.path.join(_here, "..", ".."))
    _REPO_ROOT = _candidate if os.path.isdir(os.path.join(_candidate, "adapters")) else _here

_HELPER = os.path.join(_REPO_ROOT, "adapters", "pi", "_pi_helper.py")


def _invoke(action: str, payload: dict) -> dict | None:
    cmd = [sys.executable, _HELPER, action, json.dumps(payload)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout.strip())
        if r.stderr.strip():
            print(f"[am-pi] helper: {r.stderr.strip()}", file=sys.stderr)
    except Exception as exc:  # never block Pi
        print(f"[am-pi] helper call failed: {exc}", file=sys.stderr)
    return None


# --- Pi lifecycle hook surface ---------------------------------------------

def on_session_start(session_id: str, native_session_id: str = "") -> None:
    _invoke("session_start", {"session_id": session_id, "native_session_id": native_session_id})


def on_run_started(run_id: str, session_id: str, head_sha: str = "") -> None:
    _invoke("run_started", {"run_id": run_id, "session_id": session_id, "head_sha": head_sha})


def on_turn_end(run_id: str, session_id: str, turn_index: int) -> None:
    _invoke("turn_end", {"run_id": run_id, "session_id": session_id, "turn_index": turn_index})


def on_session_before_compact(run_id: str, session_id: str, summary: str = "") -> None:
    _invoke("session_before_compact", {"run_id": run_id, "session_id": session_id, "summary": summary})


def on_run_settled(run_id: str, session_id: str, outcome: str,
                   head_sha_end: str = "", had_code_changes: bool = False,
                   task_significant: bool = False) -> dict | None:
    return _invoke("run_settled", {
        "run_id": run_id, "session_id": session_id, "outcome": outcome,
        "head_sha_end": head_sha_end, "had_code_changes": had_code_changes,
        "task_significant": task_significant,
    })


def submit_extraction_result(run_id: str, session_id: str, capture_result: str,
                             handoff: dict | None = None,
                             memories: list[dict] | None = None) -> None:
    _invoke("extraction_result", {
        "run_id": run_id, "session_id": session_id, "capture_result": capture_result,
        "handoff": handoff or {}, "memories": memories or [],
    })


def on_run_interrupted(run_id: str, session_id: str, reason: str = "") -> None:
    _invoke("run_interrupted", {"run_id": run_id, "session_id": session_id, "reason": reason})


def on_session_shutdown(session_id: str) -> None:
    _invoke("session_shutdown", {"session_id": session_id})
