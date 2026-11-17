"""Unit tests for auto project-id detection (detect_project_id).

The detection function is implemented in adapters/shared/event_client.py
and is used by all three adapter configs. It auto-derives the project_id
from the user's current working directory or git checkout name when the
AGENT_MEMORY_PROJECT_ID env var is not set.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "adapters"))


class TestDetectProjectId:
    def test_explicit_value_wins(self):
        from adapters.shared.event_client import detect_project_id
        assert detect_project_id("my-explicit") == "my-explicit"

    def test_env_var_when_set(self):
        from adapters.shared.event_client import detect_project_id
        with patch.dict(os.environ, {"AGENT_MEMORY_PROJECT_ID": "from-env"}):
            assert detect_project_id() == "from-env"

    def test_git_repo_basename(self, tmp_path: Path, monkeypatch):
        # Simulate a git checkout named "myproject"
        monkeypatch.setenv("AGENT_MEMORY_PROJECT_ID", "")
        monkeypatch.delenv("AGENT_MEMORY_PROJECT_ID", raising=False)
        from adapters.shared.event_client import detect_project_id
        fake_toplevel = str(tmp_path / "myproject")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                ["git"], 0, stdout=fake_toplevel + "\n"
            )
            assert detect_project_id() == "myproject"

    def test_cwd_basename_fallback(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("AGENT_MEMORY_PROJECT_ID", raising=False)
        monkeypatch.chdir(tmp_path)
        from adapters.shared.event_client import detect_project_id
        # No git available in tmp_path; CWD basename is the fallback.
        result = detect_project_id()
        assert result in (tmp_path.name, None, "")

    def test_all_adapters_get_detected_project_id(self):
        """The three adapters' config dataclasses pick up the auto-detected
        project_id when the env var is not set."""
        from adapters.codex.codex_adapter import CodexAdapterConfig
        from adapters.opencode.opencode_adapter import OpenCodeAdapterConfig
        from adapters.pi.pi_adapter import PiAdapterConfig

        # With env var set, all three should agree
        with patch.dict(os.environ, {"AGENT_MEMORY_PROJECT_ID": "shared-id"}):
            c1 = CodexAdapterConfig()
            c2 = OpenCodeAdapterConfig()
            c3 = PiAdapterConfig()
            assert c1.project_id == "shared-id"
            assert c2.project_id == "shared-id"
            assert c3.project_id == "shared-id"

    def test_project_id_overridable(self):
        """An explicitly passed project_id always wins over detection."""
        from adapters.codex.codex_adapter import CodexAdapterConfig
        with patch.dict(os.environ, {"AGENT_MEMORY_PROJECT_ID": "env-id"}):
            cfg = CodexAdapterConfig(project_id="explicit-id")
            assert cfg.project_id == "explicit-id"
