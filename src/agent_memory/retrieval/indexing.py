"""Background indexing worker.

Indexes knowledge rows into the lexical (FTS5) and vector (sqlite-vec)
indexes. Runs outbox-driven batch jobs; degrades to lexical-only when
the embedding provider is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_memory.config import RetrievalConfig
from agent_memory.retrieval.chunker import ChunkerConfig, chunk_knowledge
from agent_memory.retrieval.lexical import LexicalIndex
from agent_memory.retrieval.vector import VectorIndex, create_vector_index

logger = logging.getLogger(__name__)


class IndexingWorker:
    """Build and maintain the chunk + lexical + vector indexes."""

    def __init__(
        self,
        conn: Any,
        retrieval_config: RetrievalConfig,
        embedding_provider: Any = None,
    ):
        self._conn = conn
        self._retrieval = retrieval_config
        self._chunker_cfg = ChunkerConfig(
            max_chars=retrieval_config.chunk_max_chars,
            min_chars=retrieval_config.chunk_min_chars,
        )
        self._lexical = LexicalIndex(conn)
        self._vector = (
            create_vector_index(conn, embedding_provider.dimension)
            if embedding_provider is not None
            else None
        )
        self._embedder = embedding_provider

    @property
    def lexical(self) -> LexicalIndex:
        return self._lexical

    @property
    def vector(self) -> VectorIndex | None:
        return self._vector

    async def index_knowledge(self, memory_id: str, knowledge: dict) -> dict:
        """Chunk + index a single knowledge row. Returns chunk count.

        When an embedding provider is available, also computes and stores
        dense vectors for each chunk.
        """
        chunks = chunk_knowledge(knowledge, self._chunker_cfg)
        title = knowledge.get("title", "")
        summary = knowledge.get("summary", "")
        indexed = 0

        self._clear_knowledge_index(memory_id)

        for chunk in chunks:
            chunk_id = f"{memory_id}:{chunk.chunk_index}"
            self._conn.execute(
                "INSERT INTO chunks ("
                "chunk_id, project_id, memory_id, document_type, chunk_index, "
                "char_start, char_end, token_estimate, title, summary, text, active, indexed_at"
                ") VALUES (?, ?, ?, 'knowledge', ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'))",
                (
                    chunk_id,
                    knowledge.get("project_id", ""),
                    memory_id,
                    chunk.chunk_index,
                    chunk.char_start,
                    chunk.char_end,
                    chunk.token_estimate,
                    title,
                    summary,
                    chunk.text,
                ),
            )
            # Lexical upsert
            self._lexical.upsert_chunk(
                chunk_id=chunk_id,
                project_id=knowledge.get("project_id", ""),
                entity_id=memory_id,
                document_type="knowledge",
                text=chunk.text,
                title=title,
                summary=summary,
            )
            indexed += 1

        # Vector upsert (if provider available)
        if self._embedder is not None:
            texts = [c.text for c in chunks if c.text.strip()]
            if texts:
                embeddings = await self._embedder.embed(texts)
                if self._vector and self._vector.available:
                    for i, c in enumerate(chunks):
                        if not c.text.strip():
                            continue
                        chunk_id = f"{memory_id}:{c.chunk_index}"
                        self._vector.upsert(memory_id, chunk_id, embeddings[i])

        self._conn.commit()
        return {"memory_id": memory_id, "chunks_indexed": indexed}

    async def index_batch(self, items: list[tuple[str, dict]]) -> dict:
        """Index a batch of (memory_id, knowledge_row) pairs.

        Caps at ``batch_index_max_docs`` to bound memory and embedding calls.
        """
        max_docs = self._retrieval.batch_index_max_docs
        if len(items) > max_docs:
            logger.warning(
                "index_batch: %d items exceeds cap %d; truncating",
                len(items), max_docs,
            )
            items = items[:max_docs]

        total = 0
        for memory_id, row in items:
            result = await self.index_knowledge(memory_id, row)
            total += result["chunks_indexed"]

        self._conn.commit()
        return {"docs_indexed": len(items), "chunks_indexed": total}

    def delete_knowledge_index(self, memory_id: str) -> None:
        """Remove lexical + vector entries for a knowledge row."""
        self._clear_knowledge_index(memory_id)
        self._conn.commit()

    def _clear_knowledge_index(self, memory_id: str) -> None:
        """Remove all derived entries before reindexing or deleting a memory."""
        self._conn.execute("DELETE FROM chunks_fts WHERE entity_id = ?", (memory_id,))
        self._conn.execute("DELETE FROM chunks WHERE memory_id = ?", (memory_id,))
        if self._vector:
            self._vector.delete(memory_id)
