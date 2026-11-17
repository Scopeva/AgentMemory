#!/usr/bin/env python3
"""Codex PreCompact hook -> agent-memory adapter.

Called just before Codex compacts its context window. Pipes a JSON object
on stdin with ``session_id`` and an optional compaction summary. We persist
the pre-compact summary so the memory server can capture context before
it is lost.

All shared plumbing (sys.path bootstrap, env-var config) lives in
``_bootstrap.py`` in the same directory.
"""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _here)
    from _bootstrap import _bootstrap, make_config  # type: ignore

    _bootstrap()
    try:
        from adapters.codex.codex_adapter import CodexAdapter
    except ImportError as exc:
        print(f"[am-codex] adapter import failed: {exc}", file=sys.stderr)
        return 0

    raw = sys.stdin.read() or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}

    a = CodexAdapter(make_config())
    sid = data.get("session_id", "")
    summary = data.get("summary", "")
    a.on_pre_compact(sid, summary)
    a.flush()
    a.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
