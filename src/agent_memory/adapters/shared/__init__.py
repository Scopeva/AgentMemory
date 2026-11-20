"""Shared event schema, HTTP client, and spool used by all adapters."""

from agent_memory.adapters.shared.event_client import (
    DurableSpool,
    EventClient,
    SpooledEvent,
    build_event,
)

__all__ = [
    "DurableSpool",
    "EventClient",
    "SpooledEvent",
    "build_event",
]
