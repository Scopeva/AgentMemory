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
---agent_capabilities---
"""Agent adapter lifecycle and capability contract.

Adapters for Pi, Codex, and OpenCode must register their actual tested
capabilities at startup. The memory server uses these capabilities to
decide how to handle extraction and recovery, without hard-coding agent names.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentCapabilities(BaseModel):
    """Declarative capabilities an adapter actually supports."""

    agent: str
    adapter_version: str = "1.0.0"
    session_lifecycle: bool = False
    turn_completion: bool = False
    pre_compaction: bool = False
    controlled_continuation: bool = False
    session_resume: bool = False
    durable_spool: bool = False


def can_controlled_extract(caps: AgentCapabilities) -> bool:
    """Whether the adapter can request one controlled continuation for extraction."""
    return caps.controlled_continuation and caps.session_lifecycle


def can_observe_only(caps: AgentCapabilities) -> bool:
    """Fallback: the adapter can persist events but cannot trigger extraction."""
    return caps.session_lifecycle or caps.turn_completion


def recovery_strategy(caps: AgentCapabilities) -> str:
    """Return the recovery strategy for this adapter."""
    if can_controlled_extract(caps):
        return "controlled_extraction"
    if can_observe_only(caps):
        return "pending_observation"
    return "manual_recovery"


def example_capabilities() -> list[AgentCapabilities]:
    """Reference capabilities for the three target agents."""
    return [
        AgentCapabilities(
            agent="pi",
            adapter_version="1.0.0",
            session_lifecycle=True,
            turn_completion=True,
            pre_compaction=True,
            controlled_continuation=True,
            session_resume=True,
            durable_spool=True,
        ),
        AgentCapabilities(
            agent="codex",
            adapter_version="1.0.0",
            session_lifecycle=True,
            turn_completion=True,
            pre_compaction=True,
            controlled_continuation=False,
            session_resume=True,
            durable_spool=True,
        ),
        AgentCapabilities(
            agent="opencode",
            adapter_version="1.0.0",
            session_lifecycle=True,
            turn_completion=True,
            pre_compaction=False,
            controlled_continuation=False,
            session_resume=True,
            durable_spool=True,
        ),
    ]