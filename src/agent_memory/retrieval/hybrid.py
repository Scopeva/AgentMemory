"""Hybrid retrieval: FTS5 lexical + sqlite-vec vector fused with RRF.

When the vector index or embedding provider is unavailable, degrades
gracefully to lexical-only and reports ``retrieval_mode`` accordingly.
"""

from __future__ import annotations

from typing import Any

from agent_memory.config import RetrievalConfig
from agent_memory.retrieval.lexical import LexicalIndex, fts5_query
from agent_memory.retrieval.vector import VectorIndex, vec_available


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]], k: int = 60
) -> dict[str, float]:
    """Fuse multiple ranked lists of chunk_ids using Reciprocal Rank Fusion.

    Each list is an ordered list of chunk_ids (best first). Returns a dict
    mapping chunk_id -> fused score (higher is better).
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


class HybridRetriever:
    """Coordinate lexical + vector search and fuse results with RRF."""

    def __init__(
        self,
        lexical: LexicalIndex,
        vector: VectorIndex | None,
        retrieval_config: RetrievalConfig,
    ):
        self._lexical = lexical
        self._vector = vector
        self._cfg = retrieval_config

    @property
    def vector_enabled(self) -> bool:
        return self._vector is not None and self._vector.available

    def search(
        self,
        project_id: str,
        query: str,
        query_embedding: list[float] | None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Run hybrid search. Returns {chunk_ids, retrieval_mode, per_list}.

        ``chunk_ids`` is the fused, ordered list of chunk_ids (best first).
        ``retrieval_mode`` is one of: hybrid, lexical_only, none.
        """
        top_k = self._cfg.lexical_top_k
        q = fts5_query(query)
        lexical_hits = self._lexical.search(project_id, q, limit=top_k)
        lexical_order = [h["chunk_id"] for h in lexical_hits]

        vector_order: list[str] = []
        if self.vector_enabled and query_embedding:
            # Map project's memory_ids for vector filter
            # (chunk rows are keyed by memory_id; filter after retrieval)
            vec_hits = self._vector.search(
                query_embedding, limit=self._cfg.vector_top_k
            )
            vector_order = [h["chunk_id"] for h in vec_hits]

        if self.vector_enabled and query_embedding:
            fused = reciprocal_rank_fusion(
                [lexical_order, vector_order], k=self._cfg.rrf_k
            )
            mode = "hybrid"
        elif lexical_order:
            fused = {cid: 1.0 / (self._cfg.rrf_k + i) for i, cid in enumerate(lexical_order, 1)}
            mode = "lexical_only"
        else:
            fused = {}
            mode = "none"

        # Sort by fused score desc
        ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
        chunk_ids = [cid for cid, _ in ordered][: self._cfg.final_top_k]
        return {
            "chunk_ids": chunk_ids,
            "retrieval_mode": mode,
            "lexical_hits": len(lexical_order),
            "vector_hits": len(vector_order),
        }
