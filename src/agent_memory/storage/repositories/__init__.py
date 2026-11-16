"""Storage repositories subpackage.

Each submodule is a repository layer for a core aggregate. Import them
via their module path, e.g. ``from agent_memory.storage.repositories import projects``.
"""

from agent_memory.storage.repositories import (
    checkpoints,
    events,
    handoffs,
    knowledge,
    projects,
    sessions,
    tasks,
)

__all__ = [
    "checkpoints",
    "events",
    "handoffs",
    "knowledge",
    "projects",
    "sessions",
    "tasks",
]
