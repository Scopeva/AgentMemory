"""Source-independent Codex lifecycle hook dispatcher."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable

from agent_memory.adapters.codex import CodexAdapter, CodexAdapterConfig


def _config() -> CodexAdapterConfig:
    return CodexAdapterConfig(
        server_url=os.environ.get("AGENT_MEMORY_SERVER_URL", "http://127.0.0.1:8765"),
        project_id=os.environ.get("AGENT_MEMORY_PROJECT_ID"),
        workspace_id=os.environ.get("AGENT_MEMORY_WORKSPACE_ID"),
        task_id=os.environ.get("AGENT_MEMORY_TASK_ID"),
    )


def _payload() -> dict:
    try:
        raw = sys.stdin.read() or "{}"
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _session_start(adapter: CodexAdapter, payload: dict) -> None:
    adapter.on_session_start(
        payload.get("session_id", ""),
        native_session_id=payload.get("transcript_path", ""),
    )
    adapter.flush()


def _pre_compact(adapter: CodexAdapter, payload: dict) -> None:
    adapter.on_pre_compact(payload.get("session_id", ""), payload.get("summary", ""))
    adapter.flush()


def _stop(adapter: CodexAdapter, payload: dict) -> None:
    adapter.on_stop(
        payload.get("session_id", ""),
        payload.get("outcome", "completed"),
        head_sha_end=payload.get("head_sha_end", ""),
    )
    adapter.flush()


def _session_end(adapter: CodexAdapter, payload: dict) -> None:
    adapter.on_session_end(payload.get("session_id", ""))


_HANDLERS: dict[str, Callable[[CodexAdapter, dict], None]] = {
    "session-start": _session_start,
    "pre-compact": _pre_compact,
    "stop": _stop,
    "session-end": _session_end,
}
_PROGRAM = "agent-memory-codex-hook"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1 or args[0] not in _HANDLERS:
        print(f"usage: {_PROGRAM} <{'|'.join(_HANDLERS)}>", file=sys.stderr)
        return 2

    adapter = CodexAdapter(_config())
    try:
        _HANDLERS[args[0]](adapter, _payload())
    except Exception as exc:
        print(f"[am-codex] lifecycle delivery failed: {exc}", file=sys.stderr)
    finally:
        adapter.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
