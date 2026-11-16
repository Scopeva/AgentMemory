     1	"""SQLite storage layer: connection management, migrations, repositories."""
     2	
     3	from __future__ import annotations
     4	
     5	import json
     6	import sqlite3
     7	from contextlib import asynccontextmanager
     8	from dataclasses import dataclass
     9	from pathlib import Path
    10	from typing import AsyncGenerator
    11	
    12	import aiosqlite
    13	
    14	from agent_memory.config import DatabaseConfig
    15	
    16	
    17	MIGRATIONS_DIR = Path(__file__).parent / "migrations"
    18	
    19	
    20	@dataclass
    21	class Database:
    22	    """Async SQLite wrapper with WAL mode and migration support."""
    23	
    24	    config: DatabaseConfig
    25	
    26	    def __post_init__(self) -> None:
    27	        self.path = self.config.resolved_path()
    28	        self.path.parent.mkdir(parents=True, exist_ok=True)
    29	
    30	    @asynccontextmanager
    31	    async def connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
    32	        conn = await aiosqlite.connect(str(self.path))
    33	        conn.row_factory = aiosqlite.Row
    34	        await conn.execute(f"PRAGMA journal_mode = {self.config.journal_mode};")
    35	        await conn.execute("PRAGMA foreign_keys = ON;")
    36	        await conn.execute(f"PRAGMA busy_timeout = {self.config.busy_timeout_ms};")
    37	        try:
    38	            yield conn
    39	            await conn.commit()
    40	        except Exception:
    41	            await conn.rollback()
    42	            raise
    43	        finally:
    44	            await conn.close()
    45	
    46	    async def migrate(self) -> int:
    47	        """Apply all pending migrations. Returns highest version applied."""
    48	        highest = 0
    49	        async with self.connection() as conn:
    50	            await conn.execute(
    51	                "CREATE TABLE IF NOT EXISTS schema_migrations ("
    52	                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    53	            )
    54	            cursor = await conn.execute("SELECT MAX(version) FROM schema_migrations")
    55	            row = await cursor.fetchone()
    56	            current = row[0] or 0
    57	
    58	            migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    59	            for mf in migration_files:
    60	                version = int(mf.name.split("_")[0])
    61	                if version <= current:
    62	                    continue
    63	                sql = mf.read_text()
    64	                await conn.executescript(sql)
    65	                await conn.execute(
    66	                    "INSERT INTO schema_migrations (version, applied_at) "
    67	                    "VALUES (?, datetime('now'))",
    68	                    (version,),
    69	                )
    70	                highest = version
    71	        return highest
    72	
    73	    async def backup_to(self, target: Path) -> None:
    74	        """Create a consistent backup using SQLite backup API."""
    75	        target.parent.mkdir(parents=True, exist_ok=True)
    76	        async with self.connection() as src:
    77	            if target.exists():
    78	                target.unlink()
    79	            dst = await aiosqlite.connect(str(target))
    80	            await src.backup(dst)
    81	            await dst.close()
    82	
    83	
    84	# ---------------------------------------------------------------------------
    85	# Generic helpers
    86	# ---------------------------------------------------------------------------
    87	
    88	
    89	async def _execute(db: Database, sql: str, params: tuple = ()) -> None:
    90	    async with db.connection() as conn:
    91	        await conn.execute(sql, params)
    92	
    93	
    94	async def _query(db: Database, sql: str, params: tuple = ()) -> list[dict]:
    95	    async with db.connection() as conn:
    96	        cursor = await conn.execute(sql, params)
    97	        rows = await cursor.fetchall()
    98	        return [dict(r) for r in rows]
    99	
   100	
   101	def _json_dumps(obj) -> str:
   102	    return json.dumps(obj, ensure_ascii=False)
   103	
   104	
   105	def _json_loads(s: str):
   106	    try:
   107	        return json.loads(s)
   108	    except (TypeError, json.JSONDecodeError):
   109	        return []