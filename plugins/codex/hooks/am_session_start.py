#!/usr/bin/env python3
"""Codex SessionStart hook -> agent-memory adapter.

Invoked by Codex's hooks.json. Codex pipes a JSON object on stdin with
fields such as ``session_id``, ``cwd``, and ``transcript_path``. This
script registers the session and flushes the durable spool so the next
session can pick up any un-sent events.

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
        return 0  # Never block Codex on adapter failure.

    raw = sys.stdin.read() or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}

    a = CodexAdapter(make_config())
    sid = data.get("session_id", "")
    transcript = data.get("transcript_path", "")
    a.on_session_start(sid, native_session_id=transcript)
    a.flush()
    a.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
