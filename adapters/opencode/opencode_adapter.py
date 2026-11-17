"""OpenCode adapter: project-level plugin session lifecycle observer.

OpenCode supports project-level plugins. The plugin hooks into:
- onSessionStart: session begins
- onTurnStart / onTurnEnd: turn boundaries
- onSessionEnd: session teardown

The adapter reuses the shared EventClient + DurableSpool for at-least-once
delivery and builds EventEnvelope payloads matching the Phase 0 contract.
OpenCode has no pre_compaction or controlled_continuation capability (per
agent_capabilities), so the adapter is observe-only: it persists events
but does not trigger extraction.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from adapters.shared.event_client import DurableSpool, EventClient, build_event, detect_project_id


# ---------------------------------------------------------------------------
# Adapter config
# ---------------------------------------------------------------------------


@dataclass
class OpenCodeAdapterConfig:
    agent: str = "opencode"
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
# Plugin observer (passive, synchronous)
# ---------------------------------------------------------------------------


class OpenCodePluginObserver:
    """Records OpenCode plugin hook events to the EventClient + spool.

    All methods are synchronous for easy integration with OpenCode's
    project-level plugin callbacks.
    """

    def __init__(self, client: EventClient, config: OpenCodeAdapterConfig):
        self._client = client
        self._config = config
        self._seq = 0
        self._turn_counters: dict[str, int] = {}

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _cfg_kwargs(self) -> dict:
        return {
            "project_id": self._config.project_id,
            "workspace_id": self._config.workspace_id,
            "task_id": self._config.task_id,
        }

    def _turn_index(self, run_id: str) -> int:
        idx = self._turn_counters.get(run_id, 0)
        self._turn_counters[run_id] = idx + 1
        return idx

    # -- onSessionStart -----------------------------------------------------

    def on_session_start(
        self, session_id: str, native_session_id: str = "", head_sha: str = ""
    ) -> None:
        """OpenCode onSessionStart: emit session.start + run.started."""
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

    # -- onTurnStart / onTurnEnd --------------------------------------------

    def on_turn_start(self, run_id: str, session_id: str) -> None:
        """OpenCode onTurnStart: emit turn.start."""
        evt = build_event(
            "turn.start",
            agent=self._config.agent,
            session_id=session_id,
            run_id=run_id,
            sequence_no=self._next_seq(),
            payload={"turn_index": self._turn_index(run_id)},
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    def on_turn_end(self, run_id: str, session_id: str) -> None:
        """OpenCode onTurnEnd: emit turn.end."""
        evt = build_event(
            "turn.end",
            agent=self._config.agent,
            session_id=session_id,
            run_id=run_id,
            sequence_no=self._next_seq(),
            payload={"turn_index": self._turn_index(run_id) - 1},
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    # -- onSessionEnd ---------------------------------------------------------

    def on_session_end(
        self,
        session_id: str,
        outcome: str = "completed",
        head_sha_end: str = "",
    ) -> None:
        """OpenCode onSessionEnd: emit run.settled + flush spool."""
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
        try:
            self._client.flush_spool()
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Top-level adapter
# ---------------------------------------------------------------------------


class OpenCodeAdapter:
    """Façade for OpenCode plugin integration.

    Usage (inside an OpenCode project plugin):
        adapter = OpenCodeAdapter(OpenCodeAdapterConfig(project_id="..."))
        adapter.on_session_start(session_id, native_id, head_sha)
        adapter.on_turn_start(run_id, session_id)
        adapter.on_turn_end(run_id, session_id)
        adapter.on_session_end(session_id, "completed", head_sha_end)
    """

    def __init__(self, config: Optional[OpenCodeAdapterConfig] = None):
        self.config = config or OpenCodeAdapterConfig()
        spool = DurableSpool(self.config.agent, root=self.config.spool_root)
        self.client = EventClient(self.config.server_url, self.config.agent, spool=spool)
        self.observer = OpenCodePluginObserver(self.client, self.config)

    # Convenience re-exports
    def on_session_start(self, session_id: str, native_session_id: str = "", head_sha: str = "") -> None:
        self.observer.on_session_start(session_id, native_session_id, head_sha)

    def on_turn_start(self, run_id: str, session_id: str) -> None:
        self.observer.on_turn_start(run_id, session_id)

    def on_turn_end(self, run_id: str, session_id: str) -> None:
        self.observer.on_turn_end(run_id, session_id)

    def on_session_end(self, session_id: str, outcome: str = "completed", head_sha_end: str = "") -> None:
        self.observer.on_session_end(session_id, outcome, head_sha_end)

    def flush(self) -> dict:
        return self.client.flush_spool()

    def close(self) -> None:
        self.client.close()
