"""Hybrid search service wiring.

Connects the retrieval index to the storage layer and exposes an async
API that both the MCP tool and HTTP endpoints can call.
"""

from __future__ import annotations

from typing import Any, Optional

from agent_memory.config import RetrievalConfig
from agent_memory.retrieval.hybrid import HybridRetriever
from agent_memory.retrieval.indexing import IndexingWorker
from agent_memory.retrieval.lexical import LexicalIndex
from agent_memory.retrieval.vector import create_vector_index
from agent_memory.storage.database import Database


class SearchService:
    """High-level async search over the retrieval index.

    Holds references to the lexical + vector indexes and the embedding
    provider; builds the HybridRetriever on demand.
    """

    def __init__(
        self,
        db: Database,
        retrieval_config: RetrievalConfig,
        embedding_provider: Any = None,
        synchronous_conn: Any = None,
    ):
        self._db = db
        self._retrieval = retrieval_config
        self._embedder = embedding_provider
        self._sync_conn = synchronous_conn  # sqlite3.Connection for sync index ops

        if self._sync_conn is not None:
            self._lexical = LexicalIndex(self._sync_conn)
            dim = getattr(embedding_provider, "dimension", 1024) if embedding_provider else 1024
            self._vector = create_vector_index(
                self._sync_conn,
                dimension=dim,
                sqlite_vec_path=retrieval_config.sqlite_vec_path,
            )
        else:
            self._lexical = None
            self._vector = None

    @property
    def has_index(self) -> bool:
        return self._lexical is not None

    def _get_retriever(self) -> HybridRetriever:
        return HybridRetriever(self._lexical, self._vector, self._retrieval)

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 6,
        status: Optional[str] = None,
    ) -> dict[str, Any]:
        """Run hybrid search and return full chunk rows.

        Falls back to lexical-only if vector index unavailable.
        Falls back to a simple LIKE search if no FTS5 index is built yet.
        """
        query = query.strip()
        if not query:
            return {
                "results": [],
                "retrieval_mode": "none",
                "lexical_hits": 0,
                "vector_hits": 0,
            }
        if not self.has_index:
            # No index built; fall back to SQL LIKE
            return await self._fallback_search(project_id, query, limit, status)

        # Embed query if provider available
        query_embedding = None
        if self._embedder is not None:
            try:
                vecs = await self._embedder.embed([query])
                if vecs:
                    query_embedding = vecs[0]
            except Exception:
                query_embedding = None

        retriever = self._get_retriever()
        result = retriever.search(project_id, query, query_embedding, status=status)

        chunk_ids = result["chunk_ids"][:limit]
        if not chunk_ids:
            return {
                "results": [],
                "retrieval_mode": result["retrieval_mode"],
            }

        # Fetch chunk rows
        placeholders = ",".join("?" * len(chunk_ids))
        rows = []
        import sqlite3
        if self._sync_conn is not None:
            cursor = self._sync_conn.execute(
                f"SELECT chunk_id, project_id, memory_id, chunk_index, "
                f"title, summary, text, token_estimate, active "
                f"FROM chunks WHERE chunk_id IN ({placeholders}) AND active = 1",
                chunk_ids,
            )
            rows = [dict(r) for r in cursor.fetchall()]

        # Preserve rank order
        row_map = {r["chunk_id"]: r for r in rows}
        ordered = [row_map[cid] for cid in chunk_ids if cid in row_map]

        return {
            "results": ordered,
            "retrieval_mode": result["retrieval_mode"],
            "lexical_hits": result["lexical_hits"],
            "vector_hits": result["vector_hits"],
        }

    async def _fallback_search(
        self, project_id: str, query: str, limit: int, status: Optional[str]
    ) -> dict[str, Any]:
        """LIKE-based fallback when no FTS5 index is available."""
        sql = (
            "SELECT c.chunk_id, c.project_id, c.memory_id, c.chunk_index, "
            "c.title, c.summary, c.text, c.token_estimate, c.active "
            "FROM chunks c "
            "WHERE c.project_id = ? AND c.active = 1 "
        )
        params: list = [project_id]
        if query:
            sql += " AND (c.title LIKE ? OR c.text LIKE ?)"
            like = f"%{query}%"
            params.extend([like, like])
        if status:
            sql += " AND c.memory_id IN (SELECT memory_id FROM knowledge WHERE status = ?)"
            params.append(status)
        sql += " LIMIT ?"
        params.append(limit)

        rows: list[dict] = []
        if self._sync_conn is not None:
            cursor = self._sync_conn.execute(sql, params)
            rows = [dict(r) for r in cursor.fetchall()]
        else:
            # async fallback
            async with self._db.connection() as conn:
                cursor = await conn.execute(sql, params)
                results = await cursor.fetchall()
                rows = [dict(r) for r in results]

        return {"results": rows, "retrieval_mode": "fallback_like"}


def build_indexing_worker(
    sync_conn: Any,
    retrieval_config: RetrievalConfig,
    embedding_provider: Any = None,
) -> IndexingWorker:
    """Factory for the indexing worker."""
    return IndexingWorker(sync_conn, retrieval_config, embedding_provider)
