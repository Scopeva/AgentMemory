"""memoryctl CLI tests: run subcommands against a fresh DB."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

# Load memoryctl module directly from the file path (avoids package name issues).
_CLI_DIR = Path(__file__).parent.parent / "cli"
_spec = importlib.util.spec_from_file_location(
    "memoryctl", _CLI_DIR / "memoryctl" / "memoryctl.py"
)
_memoryctl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_memoryctl)
main = _memoryctl.main


@pytest.fixture
def db_env(tmp_path: Path):
    """Set up a migrated DB and env vars pointing at it."""
    from agent_memory.config import DatabaseConfig
    from agent_memory.storage.database import Database

    import asyncio

    db_path = tmp_path / "memory.db"
    db = Database(DatabaseConfig(path=str(db_path)))
    asyncio.run(db.migrate())
    os.environ["AGENT_MEMORY_DATABASE_PATH"] = str(db_path)
    os.environ["AGENT_MEMORY_CONFIG_PATH"] = ""
    return str(db_path)


class TestMemoryctlCLI:
    def test_doctor(self, db_env: str):
        rc = main(["doctor"])
        assert rc == 0

    def test_status(self, db_env: str):
        rc = main(["status"])
        assert rc == 0

    def test_projects_register_and_list(self, db_env: str):
        rc = main(["projects", "register", "--name", "cli-test-proj"])
        assert rc == 0
        rc = main(["projects", "list"])
        assert rc == 0

    def test_tasks_list_empty(self, db_env: str):
        rc = main(["tasks", "list"])
        assert rc == 0

    def test_pending_list_empty(self, db_env: str):
        rc = main(["pending", "list"])
        assert rc == 0

    def test_handoffs_latest_not_found(self, db_env: str):
        rc = main(["handoffs", "latest"])
        assert rc == 1  # not found

    def test_index_status(self, db_env: str):
        rc = main(["index", "status"])
        assert rc == 0

    def test_index_rebuild_not_implemented(self, db_env: str):
        rc = main(["index", "rebuild"])
        assert rc == 1

    def test_jobs_retry_not_implemented(self, db_env: str):
        rc = main(["jobs", "retry"])
        assert rc == 1

    def test_backup_create_and_verify(self, db_env: str, tmp_path: Path):
        backup = str(tmp_path / "backup.db")
        rc = main(["backup", "create", "--target", backup])
        assert rc == 0
        assert Path(backup).exists()
        rc = main(["backup", "verify", "--target", backup])
        assert rc == 0
