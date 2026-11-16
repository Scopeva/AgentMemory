"""Shared event schema, HTTP client, and spool used by all adapters."""

from adapters.shared.event_client import (
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
