"""Vector index backed by sqlite-vec (graceful fallback when unavailable).

sqlite-vec is loaded as a loadable extension via the ``sqlvec`` module.
If it is not available in the environment, the index transparently
degrades to a no-op and hybrid search falls back to lexical-only.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from agent_memory.retrieval.sqlvec import load_sqlite_vec

# Probe once at import time using a throwaway in-memory connection.
# The real per-connection load happens in VectorIndex.__init__ so the
# virtual table can be created on the live connection that owns it.
_VEC_AVAILABLE = False
try:
    _probe = sqlite3.connect(":memory:")
    _VEC_AVAILABLE = load_sqlite_vec(_probe)
    _probe.close()
except Exception:
    _VEC_AVAILABLE = False


def vec_available() -> bool:
    return _VEC_AVAILABLE


def ensure_vec0(conn: sqlite3.Connection) -> bool:
    """Load sqlite-vec on a live connection and report success.

    Per-connection: each new sqlite3.Connection must call this before
    using ``vec0`` virtual tables.
    """
    return load_sqlite_vec(conn)


class VectorIndex:
    """Manage a sqlite-vec virtual table ``memory_vectors``.

    When sqlite-vec is not available, all methods become no-ops and
    ``available`` is False.
    """

    def __init__(self, conn: sqlite3.Connection, dimension: int = 1024):
        self._conn = conn
        self._dimension = dimension
        # Per-connection load; the import-time probe tells us whether the
        # shared object exists anywhere, but each live connection must load
        # it before the virtual table can be created.
        self._enabled = False
        if _VEC_AVAILABLE:
            if ensure_vec0(conn):
                try:
                    conn.execute(
                        f"CREATE VIRTUAL TABLE IF NOT EXISTS memory_vectors USING vec0("
                        f"memory_id TEXT, chunk_id TEXT, embedding FLOAT[{dimension}])"
                    )
                    self._enabled = True
                except sqlite3.Error:
                    self._enabled = False
            else:
                self._enabled = False

    @property
    def available(self) -> bool:
        return self._enabled

    def upsert(self, memory_id: str, chunk_id: str, embedding: list[float]) -> None:
        if not self._enabled:
            return
        import struct
        self._conn.execute(
            "DELETE FROM memory_vectors WHERE chunk_id = ?", (chunk_id,)
        )
        blob = struct.pack(f"<{len(embedding)}f", *embedding)
        self._conn.execute(
            "INSERT INTO memory_vectors (memory_id, chunk_id, embedding) VALUES (?, ?, ?)",
            (memory_id, chunk_id, blob),
        )

    def delete(self, memory_id: str, chunk_ids: list[str] | None = None) -> None:
        if not self._enabled:
            return
        if chunk_ids:
            for cid in chunk_ids:
                self._conn.execute(
                    "DELETE FROM memory_vectors WHERE chunk_id = ?", (cid,)
                )
        else:
            self._conn.execute(
                "DELETE FROM memory_vectors WHERE memory_id = ?", (memory_id,)
            )

    def search(self, query_embedding: list[float], limit: int = 50) -> list[dict[str, Any]]:
        if not self._enabled:
            return []
        import struct
        blob = struct.pack(f"<{len(query_embedding)}f", *query_embedding)
        rows = self._conn.execute(
            "SELECT memory_id, chunk_id, distance FROM memory_vectors "
            "WHERE embedding MATCH ? AND k = ? "
            "ORDER BY distance LIMIT ?",
            (blob, limit, limit),
        ).fetchall()
        return [
            {"memory_id": r[0], "chunk_id": r[1], "distance": r[2], "rank": i + 1}
            for i, r in enumerate(rows)
        ]

    def search_project(
        self, query_embedding: list[float], project_filter: list[str] | None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Search and optionally filter by memory_id (project filter)."""
        results = self.search(query_embedding, limit=limit * 3)
        if project_filter:
            allowed = set(project_filter)
            results = [r for r in results if r["memory_id"] in allowed][:limit]
        return results[:limit]


def create_vector_index(conn: sqlite3.Connection, dimension: int = 1024) -> VectorIndex:
    return VectorIndex(conn, dimension=dimension)
