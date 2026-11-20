"""memoryctl CLI tests: run subcommands against a fresh DB."""

from __future__ import annotations

import importlib.util
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
def db_env(tmp_path: Path, monkeypatch):
    """Set up a migrated DB and canonical TOML pointing at it."""
    from agent_memory.config import DatabaseConfig
    from agent_memory.storage.database import Database

    import asyncio

    db_path = tmp_path / "memory.db"
    db = Database(DatabaseConfig(path=str(db_path)))
    asyncio.run(db.migrate())
    (tmp_path / "config.toml").write_text(
        f"[database]\npath = {str(db_path)!r}\n\n[embedding]\nenabled = false\n"
    )
    monkeypatch.chdir(tmp_path)
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

    def test_index_rebuild_queues_jobs(self, db_env: str):
        rc = main(["index", "rebuild"])
        assert rc == 0

    def test_index_rebuild_scoped_project(self, db_env: str):
        import sqlite3

        # Register two projects, seed one knowledge row each
        rc = main(["projects", "register", "--name", "pA", "--project-id", "projA"])
        assert rc == 0
        rc = main(["projects", "register", "--name", "pB", "--project-id", "projB"])
        assert rc == 0
        conn = sqlite3.connect(db_env)
        conn.row_factory = sqlite3.Row
        now = "2026-01-01T00:00:00Z"
        import uuid
        for pid in ("projA", "projB"):
            conn.execute(
                "INSERT INTO knowledge (memory_id, project_id, scope, type, status, title, content, revision, created_at, updated_at) "
                "VALUES (?, ?, 'project', 'note', 'accepted', 't', 'c', 1, ?, ?)",
                (str(uuid.uuid4()), pid, now, now),
            )
        conn.commit()
        conn.close()

        # Scoped rebuild must only queue projA jobs
        rc = main(["index", "rebuild", "--project-id", "projA"])
        assert rc == 0
        conn = sqlite3.connect(db_env)
        conn.row_factory = sqlite3.Row
        jobs = conn.execute(
            "SELECT project_id, COUNT(*) AS n FROM index_jobs GROUP BY project_id"
        ).fetchall()
        conn.close()
        assert [j["project_id"] for j in jobs] == ["projA"], f"scoped rebuild leaked: {jobs}"

    def test_index_status_json_output(self, db_env: str):
        import io, json, contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["index", "status", "--json"])
        assert rc == 0
        data = json.loads(buf.getvalue())
        assert "fts_chunks" in data and "index_jobs" in data

    def test_index_drain_no_pending(self, db_env: str):
        rc = main(["index", "drain", "--batch-size", "5"])
        assert rc == 0

    def test_jobs_retry_no_failed(self, db_env: str):
        rc = main(["jobs", "retry"])
        assert rc == 0

    def test_backup_create_and_verify(self, db_env: str, tmp_path: Path):
        backup = str(tmp_path / "backup.db")
        rc = main(["backup", "create", "--target", backup])
        assert rc == 0
        assert Path(backup).exists()
        rc = main(["backup", "verify", "--target", backup])
        assert rc == 0
