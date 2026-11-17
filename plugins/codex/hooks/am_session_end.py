#!/usr/bin/env python3
"""Codex SessionEnd hook -> agent-memory adapter.

Fires when the main thread ends. Codex gives this hook at most 3 seconds,
so we only flush the local spool (no network) and let the next SessionStart
resend. This is the at-least-once delivery guarantee.

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
    a.on_session_end(sid)  # flushes spool locally (fast, no network)
    a.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
