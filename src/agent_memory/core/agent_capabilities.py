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
