#!/usr/bin/env python3
"""Python helper invoked by the Pi extension (pi_extension.py).

Usage:
    python _pi_helper.py <action> '<json_payload>'

Actions:
    session_start, run_started, turn_end, session_before_compact,
    run_settled, run_interrupted, extraction_result, session_shutdown

Prints a JSON result to stdout (e.g. {"extract": true}) when relevant.
"""

from __future__ import annotations

import json
import os
from agent_memory.adapters.pi.pi_adapter import (
    ExtractionResult,
    PiAdapter,
    PiAdapterConfig,
)


def _make_adapter() -> PiAdapter:
    project_id = os.environ.get("AGENT_MEMORY_PROJECT_ID")
    # Fallback: auto-detect from CWD when env var is not set
    if not project_id:
        from agent_memory.adapters.shared.event_client import detect_project_id
        project_id = detect_project_id()
    workspace_id = os.environ.get("AGENT_MEMORY_WORKSPACE_ID")
    task_id = os.environ.get("AGENT_MEMORY_TASK_ID")
    spool_root = os.environ.get("AGENT_MEMORY_SPOOL_ROOT")
    server_url = os.environ.get("AGENT_MEMORY_SERVER_URL", "http://127.0.0.1:8765")
    cfg = PiAdapterConfig(
        project_id=project_id,
        workspace_id=workspace_id,
        task_id=task_id,
        spool_root=spool_root,
        server_url=server_url,
    )
    return PiAdapter(cfg)


def main() -> int:
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage: _pi_helper.py <action> <json>"}))
        return 1

    action = sys.argv[1]
    try:
        payload = json.loads(sys.argv[2])
    except json.JSONDecodeError:
        print(json.dumps({"error": "invalid JSON payload"}))
        return 1

    adapter = _make_adapter()
    session_id = payload.get("session_id", "")
    run_id = payload.get("run_id", session_id)

    try:
        if action == "session_start":
            adapter.on_session_start(session_id, payload.get("native_session_id", ""))
            print(json.dumps({"ok": True}))
        elif action == "run_started":
            adapter.on_run_started(run_id, session_id, payload.get("head_sha", ""))
            print(json.dumps({"ok": True}))
        elif action == "turn_end":
            adapter.on_turn_end(run_id, session_id, payload.get("turn_index", 0))
            print(json.dumps({"ok": True}))
        elif action == "session_before_compact":
            adapter.on_session_before_compact(run_id, session_id, payload.get("summary", ""))
            print(json.dumps({"ok": True}))
        elif action == "run_settled":
            outcome = payload.get("outcome", "completed")
            # Save the pre-settle decision via the adapter.
            # We re-derive "should extract" by calling on_run_settled which
            # records the extraction_requested event if warranted.
            adapter.on_run_settled(
                run_id,
                session_id,
                outcome,
                head_sha_end=payload.get("head_sha_end", ""),
                had_code_changes=payload.get("had_code_changes", False),
                task_significant=payload.get("task_significant", False),
            )
            # Determine whether extraction was requested for this run.
            extract = adapter.guard.get(run_id).extraction_requested or (
                adapter.guard.get(run_id).origin == "memory_extraction"
            )
            print(json.dumps({"ok": True, "extract": extract}))
        elif action == "extraction_result":
            result = ExtractionResult(
                run_id=run_id,
                capture_result=payload.get("capture_result", "captured"),
                handoff=payload.get("handoff") or None,
                memories=payload.get("memories") or [],
            )
            adapter.submit_extraction_result(run_id, session_id, result)
            print(json.dumps({"ok": True}))
        elif action == "run_interrupted":
            adapter.on_run_interrupted(run_id, session_id, payload.get("reason", ""))
            print(json.dumps({"ok": True}))
        elif action == "session_shutdown":
            adapter.on_session_shutdown(session_id)
            adapter.close()
            print(json.dumps({"ok": True}))
        else:
            print(json.dumps({"error": f"unknown action: {action}"}))
            return 1
    finally:
        # Ensure spool is flushed even on unexpected errors
        try:
            adapter.flush()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
