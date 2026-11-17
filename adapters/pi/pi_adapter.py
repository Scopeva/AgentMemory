"""Pi agent adapter: session lifecycle observer and controlled memory capture.

Pi is a CLI agent. This adapter plugs into Pi's extension mechanism to:
- Register sessions and runs
- Observe turn boundaries and compaction events
- Request one controlled continuation for memory extraction at settle
- Persist events via the shared EventClient with a durable spool

Architecture:
- SessionObserver: records lifecycle events (passive)
- MemoryCaptureController: decides when a controlled LLM extraction is allowed
  (at most once per run, with recursion guard)
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
class PiAdapterConfig:
    agent: str = "pi"
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
# Recursion guard
# ---------------------------------------------------------------------------


@dataclass
class _RunGuard:
    """Per-run state to prevent recursive extraction loops."""

    extraction_requested: bool = False
    extraction_attempted: bool = False
    origin: str = "user"  # "user" | "memory_extraction"


class RunGuard:
    """Thread-local-ish guard keyed by run_id (process-local for Pi CLI)."""

    def __init__(self):
        self._guards: dict[str, _RunGuard] = {}

    def get(self, run_id: str) -> _RunGuard:
        if run_id not in self._guards:
            self._guards[run_id] = _RunGuard()
        return self._guards[run_id]

    def allow_extraction(self, run_id: str) -> bool:
        g = self.get(run_id)
        # Refuse if we are already inside a memory-extraction continuation
        if g.origin == "memory_extraction":
            return False
        # Refuse if extraction was already attempted for this run
        if g.extraction_attempted:
            return False
        return True

    def mark_extraction_attempted(self, run_id: str) -> None:
        g = self.get(run_id)
        g.extraction_attempted = True

    def mark_extraction_origin(self, run_id: str) -> None:
        g = self.get(run_id)
        g.origin = "memory_extraction"

    def reset(self, run_id: str) -> None:
        self._guards.pop(run_id, None)


# ---------------------------------------------------------------------------
# Memory capture controller
# ---------------------------------------------------------------------------


@dataclass
class ExtractionResult:
    """Structured result the Pi agent must return after a controlled extraction."""

    run_id: str
    capture_result: str  # "captured" | "no_durable_memory" | "incomplete" | "failed"
    handoff: Optional[dict] = None
    memories: list[dict] = field(default_factory=list)


class MemoryCaptureController:
    """Decides when Pi may be asked to produce one structured extraction."""

    def __init__(self, guard: RunGuard):
        self._guard = guard

    def should_request_extraction(
        self,
        run_id: str,
        outcome: str,
        *,
        had_code_changes: bool = False,
        task_significant: bool = False,
    ) -> bool:
        """Return True only if:
        - the guard allows it (no recursion, not already attempted)
        - the outcome warrants it (completed/failed with code changes or task significance)
        """
        if not self._guard.allow_extraction(run_id):
            return False
        if outcome not in ("completed", "failed", "interrupted"):
            return False
        # Skip trivial runs with no code changes and no task significance
        if outcome == "completed" and not had_code_changes and not task_significant:
            return False
        return True

    def mark_attempted(self, run_id: str) -> None:
        self._guard.mark_extraction_attempted(run_id)
        self._guard.mark_extraction_origin(run_id)

    def on_run_end(self, run_id: str) -> None:
        self._guard.reset(run_id)


# ---------------------------------------------------------------------------
# Session observer (passive event recorder)
# ---------------------------------------------------------------------------


class SessionObserver:
    """Records Pi lifecycle events to the EventClient + spool.

    All methods are synchronous for easy integration with Pi's CLI hooks.
    """

    def __init__(self, client: EventClient, config: PiAdapterConfig):
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

    # -- lifecycle hooks ----------------------------------------------------

    def on_session_start(self, session_id: str, native_session_id: str = "") -> None:
        evt = build_event(
            "session.start",
            agent=self._config.agent,
            session_id=session_id,
            run_id=session_id,  # session.start has no run yet
            sequence_no=self._next_seq(),
            payload={"native_session_id": native_session_id},
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    def on_run_started(self, run_id: str, session_id: str, head_sha: str = "") -> None:
        evt = build_event(
            "run.started",
            agent=self._config.agent,
            session_id=session_id,
            run_id=run_id,
            sequence_no=self._next_seq(),
            payload={"head_sha_start": head_sha},
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    def on_turn_end(self, run_id: str, session_id: str, turn_index: int) -> None:
        evt = build_event(
            "turn.end",
            agent=self._config.agent,
            session_id=session_id,
            run_id=run_id,
            sequence_no=self._next_seq(),
            payload={"turn_index": turn_index},
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    def on_session_before_compact(self, run_id: str, session_id: str, summary: str = "") -> None:
        evt = build_event(
            "session.compacted",
            agent=self._config.agent,
            session_id=session_id,
            run_id=run_id,
            sequence_no=self._next_seq(),
            payload={"pre_compact_summary": summary},
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    def on_run_settled(
        self,
        run_id: str,
        session_id: str,
        outcome: str,
        *,
        head_sha_end: str = "",
        payload_extra: Optional[dict] = None,
    ) -> None:
        payload = {"outcome": outcome, "head_sha_end": head_sha_end}
        if payload_extra:
            payload.update(payload_extra)
        evt = build_event(
            "run.settled",
            agent=self._config.agent,
            session_id=session_id,
            run_id=run_id,
            sequence_no=self._next_seq(),
            payload=payload,
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    def on_run_interrupted(self, run_id: str, session_id: str, reason: str = "") -> None:
        evt = build_event(
            "run.interrupted",
            agent=self._config.agent,
            session_id=session_id,
            run_id=run_id,
            sequence_no=self._next_seq(),
            payload={"reason": reason},
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    def on_session_shutdown(self, session_id: str) -> None:
        # Flush spool before process exit; tolerate already-closed client.
        try:
            self._client.flush_spool()
        except RuntimeError:
            pass

    # -- memory extraction --------------------------------------------------

    def request_extraction(
        self,
        run_id: str,
        session_id: str,
        result: ExtractionResult,
    ) -> None:
        """Persist the extraction result as an event.

        If result.capture_result == "captured", also create a handoff and
        submit memory candidates.
        """
        payload = {
            "capture_result": result.capture_result,
        }
        if result.handoff:
            payload["handoff"] = result.handoff
        if result.memories:
            payload["memories"] = result.memories
        if result.capture_result == "no_durable_memory":
            payload["result"] = "no_durable_memory"

        evt = build_event(
            "memory.extraction_completed",
            agent=self._config.agent,
            session_id=session_id,
            run_id=run_id,
            sequence_no=self._next_seq(),
            payload=payload,
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    def on_extraction_requested(self, run_id: str, session_id: str) -> None:
        evt = build_event(
            "memory.extraction_requested",
            agent=self._config.agent,
            session_id=session_id,
            run_id=run_id,
            sequence_no=self._next_seq(),
            payload={},
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)


# ---------------------------------------------------------------------------
# Top-level adapter entry point
# ---------------------------------------------------------------------------


class PiAdapter:
    """Façade that wires together observer, controller, and client.

    Usage (inside a Pi extension):
        adapter = PiAdapter(PiAdapterConfig(project_id="..."))
        adapter.on_session_start(session_id, native_id)
        adapter.on_run_started(run_id, session_id, head_sha)
        ...
        adapter.on_run_settled(run_id, session_id, "completed")
        adapter.flush()
    """

    def __init__(self, config: Optional[PiAdapterConfig] = None):
        self.config = config or PiAdapterConfig()
        spool = DurableSpool(self.config.agent, root=self.config.spool_root)
        self.client = EventClient(self.config.server_url, self.config.agent, spool=spool)
        self.guard = RunGuard()
        self.controller = MemoryCaptureController(self.guard)
        self.observer = SessionObserver(self.client, self.config)

    # Convenience re-exports
    def on_session_start(self, session_id: str, native_session_id: str = "") -> None:
        self.observer.on_session_start(session_id, native_session_id)

    def on_run_started(self, run_id: str, session_id: str, head_sha: str = "") -> None:
        self.observer.on_run_started(run_id, session_id, head_sha)

    def on_turn_end(self, run_id: str, session_id: str, turn_index: int) -> None:
        self.observer.on_turn_end(run_id, session_id, turn_index)

    def on_session_before_compact(self, run_id: str, session_id: str, summary: str = "") -> None:
        self.observer.on_session_before_compact(run_id, session_id, summary)

    def on_run_settled(
        self,
        run_id: str,
        session_id: str,
        outcome: str,
        *,
        head_sha_end: str = "",
        had_code_changes: bool = False,
        task_significant: bool = False,
    ) -> None:
        self.observer.on_run_settled(
            run_id, session_id, outcome, head_sha_end=head_sha_end
        )
        # Decide if extraction should be requested before settling
        if self.controller.should_request_extraction(
            run_id,
            outcome,
            had_code_changes=had_code_changes,
            task_significant=task_significant,
        ):
            self.observer.on_extraction_requested(run_id, session_id)
            self.controller.mark_attempted(run_id)
            # The caller (Pi extension) is now expected to ask the model for
            # one structured extraction and call submit_extraction_result().

    def submit_extraction_result(self, run_id: str, session_id: str, result: ExtractionResult) -> None:
        self.observer.request_extraction(run_id, session_id, result)
        self.controller.on_run_end(run_id)

    def on_run_interrupted(self, run_id: str, session_id: str, reason: str = "") -> None:
        self.observer.on_run_interrupted(run_id, session_id, reason)

    def on_session_shutdown(self, session_id: str) -> None:
        self.observer.on_session_shutdown(session_id)

    def flush(self) -> dict:
        return self.client.flush_spool()

    def close(self) -> None:
        self.client.close()
