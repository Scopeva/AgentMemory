#!/usr/bin/env python3
"""Batch bridge for the OpenCode plugin.

Instead of forking a Python process for every OpenCode event (which was
measured at ~0.23 s per call and blocked the OpenCode event loop via
execFileSync), the TS plugin keeps one long-lived bridge process in a
child process and pipes newline-delimited JSON to its stdin. This bridge
reads events, persists them through the shared EventClient, and batches
them so the durable spool + HTTP delivery happens once per flush cycle.

Usage (one invocation handles many events):
    python3 opencode_bridge_batch.py
    # stdin lines: {"action": "session_start", "payload": {...}}

The bridge stays alive until stdin closes (i.e. the OpenCode process
exits or the plugin explicitly closes the pipe).
"""

from __future__ import annotations

import json
import os
import sys


def _bootstrap() -> None:
    root = os.environ.get("AGENT_MEMORY_REPO_ROOT")
    if root:
        sys.path.insert(0, root)
        return
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.abspath(os.path.join(here, "..", ".."))
    if os.path.isdir(os.path.join(candidate, "adapters")):
        sys.path.insert(0, candidate)


def main() -> int:
    _bootstrap()
    try:
        from adapters.opencode.opencode_adapter import (
            OpenCodeAdapter,
            OpenCodeAdapterConfig,
        )
    except ImportError as exc:
        print(f"[am-opencode] adapter import failed: {exc}", file=sys.stderr)
        return 1

    cfg = OpenCodeAdapterConfig(
        server_url=os.environ.get("AGENT_MEMORY_SERVER_URL", "http://127.0.0.1:8765"),
        project_id=os.environ.get("AGENT_MEMORY_PROJECT_ID"),
        workspace_id=os.environ.get("AGENT_MEMORY_WORKSPACE_ID"),
        task_id=os.environ.get("AGENT_MEMORY_TASK_ID"),
    )
    a = OpenCodeAdapter(cfg)

    # Read stdin line-by-line; each line is a JSON envelope.
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            print(json.dumps({"error": "invalid JSON", "line": line[:80]}))
            continue

        action = rec.get("action", "")
        payload = rec.get("payload", {})
        sid = payload.get("session_id", "")
        run_id = payload.get("run_id", sid)

        try:
            if action == "session_start":
                a.on_session_start(sid, native_session_id=payload.get("native_session_id", ""))
            elif action == "turn_end":
                a.on_turn_end(run_id, sid)
            elif action == "turn_start":
                a.on_turn_start(run_id, sid)
            elif action == "session_end":
                a.on_session_end(sid, outcome=payload.get("outcome", "completed"))
            else:
                print(json.dumps({"error": f"unknown action: {action}"}))
                continue
        except Exception as exc:
            print(json.dumps({"error": str(exc)}))
            continue

        # After each event, flush so the durable spool stays lean.
        try:
            a.flush()
        except Exception:
            pass

    # Final flush on stdin close.
    try:
        a.flush()
    except Exception:
        pass
    a.close()
    print(json.dumps({"ok": True, "closed": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
