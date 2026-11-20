#!/usr/bin/env python3
"""Bridge script invoked by the OpenCode TypeScript plugin.

Usage:
    python3 opencode_bridge.py <action> '<json_payload>'

Actions:
    session_start, turn_end, session_end

Each action instantiates the OpenCodeAdapter and persists the corresponding
event through the shared EventClient + DurableSpool. The bridge is
designed to be fast (< 50 ms) so it never blocks OpenCode's event loop
beyond the plugin's 5 s execFileSync timeout.

Env vars read: AGENT_MEMORY_SERVER_URL, AGENT_MEMORY_PROJECT_ID,
AGENT_MEMORY_WORKSPACE_ID, AGENT_MEMORY_TASK_ID.
"""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    try:
        from agent_memory.adapters.opencode.opencode_adapter import (
            OpenCodeAdapter,
            OpenCodeAdapterConfig,
        )
    except ImportError as exc:
        print(f"[am-opencode] adapter import failed: {exc}", file=sys.stderr)
        return 0

    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage: opencode_bridge.py <action> <json>"}))
        return 1

    action = sys.argv[1]
    try:
        payload = json.loads(sys.argv[2])
    except json.JSONDecodeError:
        print(json.dumps({"error": "invalid JSON payload"}))
        return 1

    cfg = OpenCodeAdapterConfig(
        server_url=os.environ.get("AGENT_MEMORY_SERVER_URL", "http://127.0.0.1:8765"),
        project_id=os.environ.get("AGENT_MEMORY_PROJECT_ID"),
        workspace_id=os.environ.get("AGENT_MEMORY_WORKSPACE_ID"),
        task_id=os.environ.get("AGENT_MEMORY_TASK_ID"),
    )
    a = OpenCodeAdapter(cfg)
    sid = payload.get("session_id", "")

    try:
        if action == "session_start":
            a.on_session_start(sid, native_session_id=payload.get("native_session_id", ""))
        elif action == "turn_end":
            a.on_turn_end(payload.get("run_id", sid), sid)
        elif action == "session_end":
            a.on_session_end(sid, outcome=payload.get("outcome", "completed"))
        else:
            print(json.dumps({"error": f"unknown action: {action}"}))
            return 1
    finally:
        try:
            a.flush()
        except Exception:
            pass
        a.close()

    print(json.dumps({"ok": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
