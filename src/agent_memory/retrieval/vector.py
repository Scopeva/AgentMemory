"""Vector index backed by sqlite-vec (graceful fallback when unavailable).

sqlite-vec is loaded as a loadable extension. If it is not available in the
environment, the index transparently degrades to a no-op and the hybrid
search falls back to lexical-only.
"""

from __future__ import annotations

import sqlite3
from typing import Any

# Attempt to load sqlite-vec extension at module import time.
_VEC_AVAILABLE = False
try:
    # The extension can be loaded per-connection; we probe once here using
    # an in-memory connection.
    _probe = sqlite3.connect(":memory:")
    _probe.enable_load_extension(True)
    _probe.load_extension("vec0")
    _probe.close()
    _VEC_AVAILABLE = True
except Exception:
    _VEC_AVAILABLE = False


def vec_available() -> bool:
    return _VEC_AVAILABLE


class VectorIndex:
    """Manage a sqlite-vec virtual table ``memory_vectors``.

    When sqlite-vec is not available, all methods become no-ops and
    ``available`` is False.
    """

    def __init__(self, conn: sqlite3.Connection, dimension: int = 1024):
        self._conn = conn
        self._dimension = dimension
        self._enabled = _VEC_AVAILABLE
        if self._enabled:
            try:
                conn.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS memory_vectors USING vec0("
                              f"memory_id TEXT, chunk_id TEXT, embedding FLOAT[{dimension}])")
            except sqlite3.Error:
                self._enabled = False

    @property
    def available(self) -> bool:
        return self._enabled

    def upsert(self, memory_id: str, chunk_id: str, embedding: list[float]) -> None:
        if not self._enabled:
            return
        self._conn.execute(
            "DELETE FROM memory_vectors WHERE chunk_id = ?", (chunk_id,)
        )
        blob = bytes(
            b for v in embedding for b in _float_to_bytes(v)
        )
        # sqlite-vec stores embeddings as binary BLOBs
        import struct
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


def _float_to_bytes(f: float) -> bytes:
    import struct
    return struct.pack("<f", f)


def create_vector_index(conn: sqlite3.Connection, dimension: int = 1024) -> VectorIndex:
    return VectorIndex(conn, dimension=dimension)
