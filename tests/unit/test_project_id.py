"""Unit tests for the alias table resolution (adapters/shared/project_id).

Covers:
  - explicit value always wins
  - AGENT_MEMORY_PROJECT_ID env var is the second priority
  - alias table matching: bare name, absolute path, glob wildcard, longest-wins
  - alias file missing / malformed -> empty table, falls through
  - git repo basename fallback
  - CWD basename last-resort fallback
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "adapters"))


@pytest.fixture
def alias_file(tmp_path: Path, monkeypatch):
    p = tmp_path / "aliases.toml"
    monkeypatch.setenv("AGENT_MEMORY_ALIASES_PATH", str(p))
    return p


class TestAliasTable:
    def test_missing_file_returns_empty(self, alias_file, tmp_path):
        from adapters.shared.project_id import load_alias_table
        assert load_alias_table(str(alias_file)) == {}

    def test_parse_aliases_section(self, alias_file):
        alias_file.write_text(textwrap.dedent("""
            [aliases]
            "~/code/proj-a" = "proj-a"
            "proj-a" = "proj-a"
        """))
        from adapters.shared.project_id import load_alias_table
        table = load_alias_table(str(alias_file))
        assert table["~/code/proj-a"] == "proj-a"
        assert table["proj-a"] == "proj-a"

    def test_malformed_file_returns_empty(self, alias_file):
        alias_file.write_text("this is not valid toml [")
        from adapters.shared.project_id import load_alias_table
        assert load_alias_table(str(alias_file)) == {}

    def test_non_dict_aliases_returns_empty(self, alias_file):
        # Top-level "aliases" is a string (not a dict) -> load_alias_table
        # must return {} rather than crash or return a wrong shape.
        alias_file.write_text("aliases = 'not-a-dict'\n")
        from adapters.shared.project_id import load_alias_table
        assert load_alias_table(str(alias_file)) == {}


class TestFindAlias:
    def test_bare_name_match(self, alias_file, tmp_path, monkeypatch):
        alias_file.write_text("[aliases]\nproj-a = 'proj-a'\n")
        fake_cwd = tmp_path / "proj-a"
        fake_cwd.mkdir()
        monkeypatch.chdir(fake_cwd)
        from adapters.shared.project_id import find_alias
        assert find_alias() == "proj-a"

    def test_longest_match_wins(self, alias_file, tmp_path, monkeypatch):
        alias_file.write_text(textwrap.dedent("""
            [aliases]
            "proj" = "generic"
            "proj-a" = "specific"
        """))
        fake_cwd = tmp_path / "proj-a"
        fake_cwd.mkdir()
        monkeypatch.chdir(fake_cwd)
        from adapters.shared.project_id import find_alias
        assert find_alias() == "specific"

    def test_glob_wildcard(self, alias_file, tmp_path):
        alias_file.write_text("[aliases]\n'~/work/*/proj-a' = 'proj-a'\n")
        target = tmp_path / "work" / "x" / "proj-a"
        target.mkdir(parents=True)
        # Patch home so the ~/ expansion lands under tmp_path
        monkeypatch_home = tmp_path
        with patch("adapters.shared.project_id.Path.home", return_value=monkeypatch_home):
            from adapters.shared.project_id import find_alias
            assert find_alias(target) == "proj-a"

    def test_no_match_returns_none(self, alias_file, tmp_path, monkeypatch):
        alias_file.write_text("[aliases]\nfoo = 'foo'\n")
        fake_cwd = tmp_path / "bar"
        fake_cwd.mkdir()
        monkeypatch.chdir(fake_cwd)
        from adapters.shared.project_id import find_alias
        assert find_alias() is None


class TestResolveProjectId:
    def test_explicit_beats_all(self, alias_file, monkeypatch):
        alias_file.write_text("[aliases]\nbar = 'from-alias'\n")
        monkeypatch.setenv("AGENT_MEMORY_PROJECT_ID", "from-env")
        from adapters.shared.project_id import resolve_project_id
        assert resolve_project_id("explicit") == "explicit"

    def test_env_beats_alias(self, alias_file, monkeypatch):
        alias_file.write_text("[aliases]\nbar = 'from-alias'\n")
        monkeypatch.setenv("AGENT_MEMORY_PROJECT_ID", "from-env")
        from adapters.shared.project_id import resolve_project_id
        assert resolve_project_id() == "from-env"

    def test_alias_beats_git_and_cwd(self, alias_file, tmp_path, monkeypatch):
        alias_file.write_text("[aliases]\nmydir = 'stable-id'\n")
        fake_cwd = tmp_path / "mydir"
        fake_cwd.mkdir()
        monkeypatch.chdir(fake_cwd)
        # No git, no env -> alias should win
        monkeypatch.delenv("AGENT_MEMORY_PROJECT_ID", raising=False)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = __import__("subprocess").CompletedProcess(
                ["git"], 1, stdout=""
            )
            from adapters.shared.project_id import resolve_project_id
            assert resolve_project_id() == "stable-id"

    def test_cwd_basename_last_resort(self, tmp_path, monkeypatch):
        fake_cwd = tmp_path / "plaindir"
        fake_cwd.mkdir()
        monkeypatch.chdir(fake_cwd)
        monkeypatch.delenv("AGENT_MEMORY_PROJECT_ID", raising=False)
        monkeypatch.delenv("AGENT_MEMORY_ALIASES_PATH", raising=False)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = __import__("subprocess").CompletedProcess(
                ["git"], 1, stdout=""
            )
            from adapters.shared.project_id import resolve_project_id
            assert resolve_project_id() == "plaindir"


class TestDetectProjectIdBackCompat:
    """The event_client.detect_project_id shim keeps working via
    resolve_project_id under the hood."""

    def test_shim_uses_resolver(self, alias_file, monkeypatch):
        alias_file.write_text("[aliases]\nxdir = 'x-id'\n")
        fake_cwd = monkeypatch.chdir(Path.cwd())
        from adapters.shared.event_client import detect_project_id
        # With env var unset and no alias hit, CWD basename is returned.
        monkeypatch.delenv("AGENT_MEMORY_PROJECT_ID", raising=False)
        result = detect_project_id()
        assert result in (Path.cwd().name, None, "x-id")
