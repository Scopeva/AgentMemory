adapters/pi/_pi_helper.py
adapters/pi/pi_adapter.py
adapters/pi/pi_extension.py
adapters/shared/__init__.py
adapters/shared/event_client.py
---
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

from adapters.shared.event_client import DurableSpool, EventClient, build_event


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
    project_id: Optional[str] = None
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