"""Codex adapter: official Hooks-based session lifecycle observer.

Codex (OpenAI's CLI agent) supports session hooks:
- SessionStart: agent begins a conversation
- Stop: agent finishes a run (outcome: completed/failed/interrupted)
- PreCompact: context window compaction warning
- SessionEnd: session teardown / shutdown

The adapter reuses the shared EventClient + DurableSpool for at-least-once
delivery and builds EventEnvelope payloads matching the Phase 0 contract.
Codex has no controlled_continuation capability (per agent_capabilities),
so the adapter is observe-only: it persists events but does not trigger
extraction.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from adapters.shared.event_client import (
    DurableSpool,
    EventClient,
    build_event,
    detect_project_id,
)


# ---------------------------------------------------------------------------
# Adapter config
# ---------------------------------------------------------------------------


@dataclass
class CodexAdapterConfig:
    agent: str = "codex"
    server_url: str = field(
        default_factory=lambda: os.environ.get("AGENT_MEMORY_SERVER_URL", "http://127.0.0.1:8765")
    )
    spool_root: Optional[str] = None
    project_id: Optional[str] = field(
        default_factory=lambda: detect_project_id(
            os.environ.get("AGENT_MEMORY_PROJECT_ID")
        )
    )
    workspace_id: Optional[str] = None
    task_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Hook observer (passive, synchronous)
# ---------------------------------------------------------------------------


class CodexHookObserver:
    """Records Codex hook events to the EventClient + spool.

    All methods are synchronous for easy integration with Codex's hook
    callbacks (SessionStart / Stop / PreCompact / SessionEnd).
    """

    def __init__(self, client: EventClient, config: CodexAdapterConfig):
        self._client = client
        self._config = config
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _cfg_kwargs(self) -> dict:
        return {
            "project_id": self._config.project_id,
            "workspace_id": self._config.workspace_id,
            "task_id": self._config.task_id,
        }

    # -- SessionStart -------------------------------------------------------

    def on_session_start(
        self, session_id: str, native_session_id: str = "", head_sha: str = ""
    ) -> None:
        """Codex SessionStart hook: emit session.start + run.started."""
        start_evt = build_event(
            "session.start",
            agent=self._config.agent,
            session_id=session_id,
            run_id=session_id,
            sequence_no=self._next_seq(),
            payload={"native_session_id": native_session_id},
            **self._cfg_kwargs(),
        )
        self._client.submit(start_evt)

        if head_sha:
            run_evt = build_event(
                "run.started",
                agent=self._config.agent,
                session_id=session_id,
                run_id=session_id,
                sequence_no=self._next_seq(),
                payload={"head_sha_start": head_sha},
                **self._cfg_kwargs(),
            )
            self._client.submit(run_evt)

    # -- Stop ---------------------------------------------------------------

    def on_stop(self, session_id: str, outcome: str, head_sha_end: str = "") -> None:
        """Codex Stop hook: emit run.settled with the run outcome.

        outcome: "completed" | "failed" | "interrupted"
        """
        evt = build_event(
            "run.settled",
            agent=self._config.agent,
            session_id=session_id,
            run_id=session_id,
            sequence_no=self._next_seq(),
            payload={"outcome": outcome, "head_sha_end": head_sha_end},
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    # -- PreCompact ---------------------------------------------------------

    def on_pre_compact(self, session_id: str, summary: str = "") -> None:
        """Codex PreCompact hook: emit session.compacted before context loss."""
        evt = build_event(
            "session.compacted",
            agent=self._config.agent,
            session_id=session_id,
            run_id=session_id,
            sequence_no=self._next_seq(),
            payload={"pre_compact_summary": summary},
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    # -- SessionEnd ---------------------------------------------------------

    def on_session_end(self, session_id: str) -> None:
        """Codex SessionEnd hook: flush spool before process exits."""
        try:
            self._client.flush_spool()
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Top-level adapter
# ---------------------------------------------------------------------------


class CodexAdapter:
    """Façade for Codex hook integration.

    Usage (inside a Codex hook script):
        adapter = CodexAdapter(CodexAdapterConfig(project_id="..."))
        adapter.on_session_start(session_id, native_id, head_sha)
        adapter.on_pre_compact(session_id, summary)
        adapter.on_stop(session_id, "completed", head_sha_end)
        adapter.on_session_end(session_id)
    """

    def __init__(self, config: Optional[CodexAdapterConfig] = None):
        self.config = config or CodexAdapterConfig()
        spool = DurableSpool(self.config.agent, root=self.config.spool_root)
        self.client = EventClient(self.config.server_url, self.config.agent, spool=spool)
        self.observer = CodexHookObserver(self.client, self.config)

    # Convenience re-exports
    def on_session_start(self, session_id: str, native_session_id: str = "", head_sha: str = "") -> None:
        self.observer.on_session_start(session_id, native_session_id, head_sha)

    def on_stop(self, session_id: str, outcome: str, head_sha_end: str = "") -> None:
        self.observer.on_stop(session_id, outcome, head_sha_end)

    def on_pre_compact(self, session_id: str, summary: str = "") -> None:
        self.observer.on_pre_compact(session_id, summary)

    def on_session_end(self, session_id: str) -> None:
        self.observer.on_session_end(session_id)

    def flush(self) -> dict:
        return self.client.flush_spool()

    def close(self) -> None:
        self.client.close()
