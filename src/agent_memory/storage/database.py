"""SQLite storage layer: connection management, migrations, repositories."""

from __future__ import annotations

import json
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

from agent_memory.config import DatabaseConfig


MIGRATIONS_DIR = Path(__file__).parent / "migrations"


@dataclass
class Database:
    """Async SQLite wrapper with WAL mode and migration support."""

    config: DatabaseConfig

    def __post_init__(self) -> None:
        self.path = self.config.resolved_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        conn = await aiosqlite.connect(str(self.path))
        conn.row_factory = aiosqlite.Row
        await conn.execute(f"PRAGMA journal_mode = {self.config.journal_mode};")
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.execute(f"PRAGMA busy_timeout = {self.config.busy_timeout_ms};")
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        finally:
            await conn.close()

    async def migrate(self) -> int:
        """Apply all pending migrations. Returns highest version applied."""
        highest = 0
        async with self.connection() as conn:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            cursor = await conn.execute("SELECT MAX(version) FROM schema_migrations")
            row = await cursor.fetchone()
            current = row[0] or 0

            migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
            for mf in migration_files:
                version = int(mf.name.split("_")[0])
                if version <= current:
                    continue
                sql = mf.read_text()
                await conn.executescript(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) "
                    "VALUES (?, datetime('now'))",
                    (version,),
                )
                highest = version
        return highest

    async def backup_to(self, target: Path) -> None:
        """Create a consistent backup using SQLite backup API."""
        target.parent.mkdir(parents=True, exist_ok=True)
        async with self.connection() as src:
            if target.exists():
                target.unlink()
            dst = await aiosqlite.connect(str(target))
            await src.backup(dst)
            await dst.close()


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


async def _execute(db: Database, sql: str, params: tuple = ()) -> None:
    async with db.connection() as conn:
        await conn.execute(sql, params)


async def _query(db: Database, sql: str, params: tuple = ()) -> list[dict]:
    async with db.connection() as conn:
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


def _json_dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(s: str):
    try:
        return json.loads(s)
    except (TypeError, json.JSONDecodeError):
        return []
