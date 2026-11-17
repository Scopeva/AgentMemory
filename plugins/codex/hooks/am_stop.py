#!/usr/bin/env python3
"""Codex Stop hook -> agent-memory adapter.

Fires at the end of a turn / run. Codex pipes JSON on stdin with
``session_id`` and an outcome. We persist ``run.settled`` and flush the
spool so events are delivered to the memory server.
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
    candidate = os.path.abspath(os.path.join(here, "..", "..", ".."))
    if os.path.isdir(os.path.join(candidate, "adapters")):
        sys.path.insert(0, candidate)


def main() -> int:
    _bootstrap()
    try:
        from adapters.codex.codex_adapter import CodexAdapter, CodexAdapterConfig
    except ImportError as exc:
        print(f"[am-codex] adapter import failed: {exc}", file=sys.stderr)
        return 0

    raw = sys.stdin.read() or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}

    cfg = CodexAdapterConfig(
        server_url=os.environ.get("AGENT_MEMORY_SERVER_URL", "http://127.0.0.1:8765"),
        project_id=os.environ.get("AGENT_MEMORY_PROJECT_ID"),
        workspace_id=os.environ.get("AGENT_MEMORY_WORKSPACE_ID"),
        task_id=os.environ.get("AGENT_MEMORY_TASK_ID"),
    )
    a = CodexAdapter(cfg)
    sid = data.get("session_id", "")
    outcome = data.get("outcome", "completed")
    head_sha_end = data.get("head_sha_end", "")
    a.on_stop(sid, outcome, head_sha_end=head_sha_end)
    a.flush()
    a.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
