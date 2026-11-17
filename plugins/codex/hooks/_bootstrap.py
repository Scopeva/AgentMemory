"""Shared bootstrap + config for Codex hook scripts.

All four am_*.py hook scripts in this directory import ``_bootstrap``
and ``make_config`` from this module, so the common sys.path / env-var
plumbing is implemented in one place instead of being copy-pasted into
every hook.

Usage in each hook script::

    from plugins.codex.hooks import _bootstrap, make_config
    _bootstrap()
    a = CodexAdapter(make_config())
"""

from __future__ import annotations

import os
import sys
from typing import Optional


def _bootstrap() -> None:
    """Add the repo root to ``sys.path`` so adapters can be imported.

    Resolution order:
      1. ``AGENT_MEMORY_REPO_ROOT`` env var
      2. Walk up three levels from this file's directory
         (plugins/codex/hooks/ -> repo root)
    """
    root = os.environ.get("AGENT_MEMORY_REPO_ROOT")
    if root:
        sys.path.insert(0, root)
        return
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.abspath(os.path.join(here, "..", "..", ".."))
    if os.path.isdir(os.path.join(candidate, "adapters")):
        sys.path.insert(0, candidate)


def make_config():
    """Build a ``CodexAdapterConfig`` from the standard env vars."""
    from adapters.codex.codex_adapter import CodexAdapterConfig

    return CodexAdapterConfig(
        server_url=os.environ.get("AGENT_MEMORY_SERVER_URL", "http://127.0.0.1:8765"),
        project_id=os.environ.get("AGENT_MEMORY_PROJECT_ID"),
        workspace_id=os.environ.get("AGENT_MEMORY_WORKSPACE_ID"),
        task_id=os.environ.get("AGENT_MEMORY_TASK_ID"),
    )
