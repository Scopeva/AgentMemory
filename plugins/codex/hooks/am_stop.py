#!/usr/bin/env python3
"""Codex Stop hook -> agent-memory adapter.

Fires at the end of a turn / run. Codex pipes JSON on stdin with
``session_id`` and an outcome. We persist ``run.settled`` and flush the
spool so events are delivered to the memory server.

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
    outcome = data.get("outcome", "completed")
    head_sha_end = data.get("head_sha_end", "")
    a.on_stop(sid, outcome, head_sha_end=head_sha_end)
    a.flush()
    a.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
