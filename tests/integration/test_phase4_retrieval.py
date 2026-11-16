"""Integration tests: dispatcher drains index jobs; end-to-end hybrid search."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_memory.config import AppConfig, DatabaseConfig, RetrievalConfig
from agent_memory.retrieval.indexing import IndexingWorker
from agent_memory.retrieval.dispatcher import JobDispatcher
from agent_memory.retrieval.search import SearchService
from agent_memory.services import core
from agent_memory.services.core import set_search_service
from agent_memory.storage.database import Database


@pytest.fixture
async def e2e_db(tmp_path):
    db = Database(DatabaseConfig(path=str(tmp_path / "e2e.db")))
    await db.migrate()
    yield db


@pytest.fixture
def sync_conn(tmp_path):
    import sqlite3
    # Run migrations on the sync conn so tables exist
    conn = sqlite3.connect(str(tmp_path / "e2e_sync.db"), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY, name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS knowledge (
            memory_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT 'project', type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'candidate', title TEXT NOT NULL,
            content TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
            current_source_revision TEXT, supersedes_memory_id TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            memory_id TEXT NOT NULL, document_type TEXT NOT NULL DEFAULT 'knowledge',
            chunk_index INTEGER NOT NULL DEFAULT 0,
            char_start INTEGER NOT NULL DEFAULT 0, char_end INTEGER NOT NULL DEFAULT 0,
            token_estimate INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            indexed_at TEXT NOT NULL, UNIQUE (memory_id, chunk_index)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED, project_id UNINDEXED, entity_id UNINDEXED,
            document_type UNINDEXED, title, summary, text, active UNINDEXED,
            tokenize = 'unicode61'
        );
        CREATE TABLE IF NOT EXISTS index_jobs (
            job_id TEXT PRIMARY KEY, memory_id TEXT NOT NULL,
            project_id TEXT NOT NULL, job_type TEXT NOT NULL DEFAULT 'index',
            status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.mark.asyncio
class TestDispatcherDrain:
    async def test_enqueue_and_drain(self, e2e_db, sync_conn):
        # Insert project + knowledge row into the e2e (async) db
        await _seed_project_and_knowledge(e2e_db)

        worker = IndexingWorker(sync_conn, RetrievalConfig())
        dispatcher = JobDispatcher(e2e_db, worker, RetrievalConfig(), sync_conn)

        job_id = dispatcher.enqueue_index("k1", "p1")
        assert dispatcher.pending_count() == 1

        # Drain: dispatcher reads knowledge from e2e_db (async) and writes FTS to sync_conn
        # Simulate knowledge row also in sync_conn
        sync_conn.execute(
            "INSERT INTO knowledge (memory_id, project_id, type, title, content, "
            "created_at, updated_at) VALUES ('k1', 'p1', 'adr', 'Use WAL mode', "
            "'We always set PRAGMA journal_mode=WAL', '2026-01-01', '2026-01-01')"
        )
        sync_conn.commit()

        result = await dispatcher.drain(batch_size=10)
        assert result["completed"] == 1
        assert dispatcher.pending_count() == 0
        # Verify FTS row
        rows = sync_conn.execute(
            "SELECT chunk_id FROM chunks_fts WHERE chunk_id LIKE 'k1:%'"
        ).fetchall()
        assert len(rows) >= 1

    async def test_drain_skips_missing_knowledge(self, e2e_db, sync_conn):
        worker = IndexingWorker(sync_conn, RetrievalConfig())
        dispatcher = JobDispatcher(e2e_db, worker, RetrievalConfig(), sync_conn)

        # Enqueue for a knowledge row that does NOT exist in the db
        dispatcher.enqueue_index("ghost", "p1")
        result = await dispatcher.drain(batch_size=10)
        # Since e2e_db has no 'ghost', it is skipped
        assert result["skipped"] == 1

    async def test_idempotent_enqueue(self, e2e_db, sync_conn):
        worker = IndexingWorker(sync_conn, RetrievalConfig())
        dispatcher = JobDispatcher(e2e_db, worker, RetrievalConfig(), sync_conn)

        j1 = dispatcher.enqueue_index("k1", "p1")
        j2 = dispatcher.enqueue_index("k1", "p1")
        assert j1 == j2  # same pending job returned


@pytest.mark.asyncio
class TestHybridSearchEndToEnd:
    async def test_search_finds_indexed_knowledge(self, e2e_db, sync_conn):
        # Seed knowledge + run indexer manually
        worker = IndexingWorker(sync_conn, RetrievalConfig())
        await worker.index_knowledge(
            "k1",
            {"project_id": "p1", "title": "WAL Mode", "content": "PRAGMA journal_mode=WAL improves concurrency", "summary": ""},
        )
        sync_conn.execute(
            "INSERT INTO chunks (chunk_id, project_id, memory_id, chunk_index, "
            "token_estimate, title, text, active, indexed_at) VALUES "
            "('k1:0', 'p1', 'k1', 0, 10, 'WAL Mode', "
            "'WAL Mode PRAGMA journal_mode=WAL improves concurrency', 1, '2026-01-01')"
        )
        sync_conn.commit()

        search = SearchService(
            db=e2e_db,
            retrieval_config=RetrievalConfig(),
            embedding_provider=None,
            synchronous_conn=sync_conn,
        )
        result = await search.search("p1", "WAL concurrency", limit=5)
        assert result["retrieval_mode"] in {"lexical_only", "hybrid"}
        assert any(r["chunk_id"] == "k1:0" for r in result["results"])

    async def test_search_service_injection(self, e2e_db, sync_conn):
        search = SearchService(
            db=e2e_db,
            retrieval_config=RetrievalConfig(),
            embedding_provider=None,
            synchronous_conn=sync_conn,
        )
        set_search_service(search)
        try:
            result = await core.search_memory(e2e_db, "p1", "anything")
            # No FTS rows for "p1": hybrid service reports mode "none"
            assert result["retrieval_mode"] in {"lexical_basic", "lexical_only", "hybrid", "none", "fallback_like"}
        finally:
            set_search_service(None)


async def _seed_project_and_knowledge(db: Database) -> None:
    """Insert a project and knowledge row into the e2e database."""
    import uuid
    from agent_memory.schemas import Project, Knowledge, KnowledgeStatus

    from agent_memory.storage import repositories as repo

    pid = "p1"
    await repo.projects.register_project(
        db,
        Project(project_id=pid, name="Test Project", created_at="2026-01-01", updated_at="2026-01-01"),
    )
    k = Knowledge(
        memory_id="k1",
        project_id=pid,
        type="adr",
        title="Use WAL mode",
        content="We always set PRAGMA journal_mode=WAL",
        status=KnowledgeStatus.ACCEPTED,
    )
    await repo.knowledge.create_knowledge(db, k)
