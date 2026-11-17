#!/usr/bin/env python3
"""Codex SessionStart hook -> agent-memory adapter.

Invoked by Codex's hooks.json. Codex pipes a JSON object on stdin with
fields such as ``session_id``, ``cwd``, and ``transcript_path``. This
script registers the session and flushes the durable spool so the next
session can pick up any un-sent events.

The adapter is imported from the repo's ``adapters`` package. Set the
``AGENT_MEMORY_REPO_ROOT`` env var (or clone the repo and let this script
auto-detect) so ``sys.path`` can find it. All AGENT_MEMORY_* env vars are
read by the adapter (see adapters/shared/event_client.py).
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
    # Auto-detect: walk up from this file's repo location.
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
        return 0  # Never block Codex on adapter failure.

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
    transcript = data.get("transcript_path", "")
    a.on_session_start(sid, native_session_id=transcript)
    a.flush()
    a.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
