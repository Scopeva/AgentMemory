"""Outbox-driven dispatch: enqueue / drain indexing jobs.

Bridges the outbox table and IndexingWorker. When a knowledge row is
created or updated, an index job is enqueued. The dispatcher drains
pending jobs, running them through the IndexingWorker.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from agent_memory.config import RetrievalConfig
from agent_memory.retrieval.indexing import IndexingWorker
from agent_memory.storage.database import Database

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


class JobDispatcher:
    """Enqueue and drain outbox-driven index/delete jobs.

    Uses the sync connection for job table operations (mirrors the
    CLI sync-sqlite3 pattern). The IndexingWorker performs the actual
    chunking + FTS5/vector writes.
    """

    def __init__(
        self,
        db: Database,
        indexing_worker: IndexingWorker,
        retrieval_config: RetrievalConfig,
        sync_conn: Any,
    ):
        self._db = db
        self._worker = indexing_worker
        self._cfg = retrieval_config
        self._conn = sync_conn

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    def enqueue_index(self, memory_id: str, project_id: str) -> str:
        """Enqueue an index job for a knowledge row. Idempotent per row:
        an already-pending job for the same memory_id is not duplicated.
        """
        existing = self._conn.execute(
            "SELECT job_id FROM index_jobs WHERE memory_id = ? AND status = 'pending'",
            (memory_id,),
        ).fetchone()
        if existing:
            return existing["job_id"]

        job_id = str(uuid.uuid4())
        now = _utcnow()
        self._conn.execute(
            "INSERT INTO index_jobs (job_id, memory_id, project_id, job_type, status, "
            "attempts, created_at, updated_at) VALUES (?, ?, ?, 'index', 'pending', 0, ?, ?)",
            (job_id, memory_id, project_id, now, now),
        )
        self._conn.commit()
        return job_id

    def enqueue_delete(self, memory_id: str, project_id: str) -> str:
        """Enqueue a delete job for a knowledge row's index entries."""
        job_id = str(uuid.uuid4())
        now = _utcnow()
        self._conn.execute(
            "INSERT INTO index_jobs (job_id, memory_id, project_id, job_type, status, "
            "attempts, created_at, updated_at) VALUES (?, ?, ?, 'delete', 'pending', 0, ?, ?)",
            (job_id, memory_id, project_id, now, now),
        )
        self._conn.commit()
        return job_id

    # ------------------------------------------------------------------
    # Drain
    # ------------------------------------------------------------------

    async def drain(self, batch_size: Optional[int] = None) -> dict:
        """Process pending index jobs up to ``batch_size``.

        Returns counts of completed/failed/skipped jobs.
        """
        if batch_size is None:
            batch_size = self._cfg.batch_index_max_docs

        rows = self._conn.execute(
            "SELECT job_id, memory_id, project_id, job_type "
            "FROM index_jobs WHERE status = 'pending' "
            "ORDER BY created_at ASC LIMIT ?",
            (batch_size,),
        ).fetchall()

        completed = failed = skipped = 0
        for row in rows:
            job_id = row["job_id"]
            self._conn.execute(
                "UPDATE index_jobs SET status = 'running', attempts = attempts + 1, "
                "updated_at = ? WHERE job_id = ?",
                (_utcnow(), job_id),
            )
            self._conn.commit()

            try:
                if row["job_type"] == "delete":
                    self._worker.delete_knowledge_index(row["memory_id"])
                    skipped += 1
                else:
                    # Fetch knowledge row for chunking
                    async with self._db.connection() as conn:
                        cursor = await conn.execute(
                            "SELECT memory_id, project_id, title, content "
                            "FROM knowledge WHERE memory_id = ?",
                            (row["memory_id"],),
                        )
                        krow = await cursor.fetchone()
                    if krow is None:
                        # Knowledge was removed; skip index
                        self._conn.execute(
                            "UPDATE index_jobs SET status = 'skipped', updated_at = ? "
                            "WHERE job_id = ?",
                            (_utcnow(), job_id),
                        )
                        self._conn.commit()
                        skipped += 1
                        continue
                    kdict = dict(krow)
                    await self._worker.index_knowledge(row["memory_id"], kdict)
                    self._conn.execute(
                        "UPDATE index_jobs SET status = 'completed', updated_at = ? "
                        "WHERE job_id = ?",
                        (_utcnow(), job_id),
                    )
                    self._conn.commit()
                    completed += 1
            except Exception as exc:
                logger.warning("index job %s failed: %s", job_id, exc)
                self._conn.execute(
                    "UPDATE index_jobs SET status = 'failed', error = ?, updated_at = ? "
                    "WHERE job_id = ?",
                    (str(exc), _utcnow(), job_id),
                )
                self._conn.commit()
                failed += 1

        return {"completed": completed, "failed": failed, "skipped": skipped, "total": len(rows)}

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def pending_count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM index_jobs WHERE status = 'pending'"
        ).fetchone()
        return row["n"] if row else 0
