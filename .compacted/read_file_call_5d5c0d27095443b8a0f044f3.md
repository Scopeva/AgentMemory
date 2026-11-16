     1	"""Background indexing worker.
     2	
     3	Indexes knowledge rows into the lexical (FTS5) and vector (sqlite-vec)
     4	indexes. Runs outbox-driven batch jobs; degrades to lexical-only when
     5	the embedding provider is unavailable.
     6	"""
     7	
     8	from __future__ import annotations
     9	
    10	import logging
    11	from typing import Any
    12	
    13	from agent_memory.config import RetrievalConfig
    14	from agent_memory.retrieval.chunker import ChunkerConfig, chunk_knowledge, build_search_text
    15	from agent_memory.retrieval.lexical import LexicalIndex
    16	from agent_memory.retrieval.vector import VectorIndex, create_vector_index
    17	
    18	logger = logging.getLogger(__name__)
    19	
    20	
    21	class IndexingWorker:
    22	    """Build and maintain the chunk + lexical + vector indexes."""
    23	
    24	    def __init__(
    25	        self,
    26	        conn: Any,
    27	        retrieval_config: RetrievalConfig,
    28	        embedding_provider: Any = None,
    29	    ):
    30	        self._conn = conn
    31	        self._retrieval = retrieval_config
    32	        self._chunker_cfg = ChunkerConfig(
    33	            max_chars=retrieval_config.chunk_max_chars,
    34	            min_chars=retrieval_config.chunk_min_chars,
    35	        )
    36	        self._lexical = LexicalIndex(conn)
    37	        self._vector = (
    38	            create_vector_index(conn, embedding_provider.dimension)
    39	            if embedding_provider is not None
    40	            else None
    41	        )
    42	        self._embedder = embedding_provider
    43	
    44	    @property
    45	    def lexical(self) -> LexicalIndex:
    46	        return self._lexical
    47	
    48	    @property
    49	    def vector(self) -> VectorIndex | None:
    50	        return self._vector
    51	
    52	    async def index_knowledge(self, memory_id: str, knowledge: dict) -> dict:
    53	        """Chunk + index a single knowledge row. Returns chunk count.
    54	
    55	        When an embedding provider is available, also computes and stores
    56	        dense vectors for each chunk.
    57	        """
    58	        chunks = chunk_knowledge(knowledge, self._chunker_cfg)
    59	        title = knowledge.get("title", "")
    60	        summary = knowledge.get("summary", "")
    61	        indexed = 0
    62	
    63	        for chunk in chunks:
    64	            chunk_id = f"{memory_id}:{chunk.chunk_index}"
    65	            # Lexical upsert
    66	            self._lexical.upsert_chunk(
    67	                chunk_id=chunk_id,
    68	                project_id=knowledge.get("project_id", ""),
    69	                entity_id=memory_id,
    70	                document_type="knowledge",
    71	                text=chunk.text,
    72	                title=title,
    73	                summary=summary,
    74	            )
    75	            indexed += 1
    76	
    77	        # Vector upsert (if provider available)
    78	        if self._embedder is not None:
    79	            import asyncio
    80	            texts = [c.text for c in chunks if c.text.strip()]
    81	            if texts:
    82	                embeddings = await self._embedder.embed(texts)
    83	                if self._vector and self._vector.available:
    84	                    for i, c in enumerate(chunks):
    85	                        if not c.text.strip():
    86	                            continue
    87	                        chunk_id = f"{memory_id}:{c.chunk_index}"
    88	                        self._vector.upsert(memory_id, chunk_id, embeddings[i])
    89	
    90	        self._conn.commit()
    91	        return {"memory_id": memory_id, "chunks_indexed": indexed}
    92	
    93	    async def index_batch(self, items: list[tuple[str, dict]]) -> dict:
    94	        """Index a batch of (memory_id, knowledge_row) pairs.
    95	
    96	        Caps at ``batch_index_max_docs`` to bound memory and embedding calls.
    97	        """
    98	        max_docs = self._retrieval.batch_index_max_docs
    99	        if len(items) > max_docs:
   100	            logger.warning(
   101	                "index_batch: %d items exceeds cap %d; truncating",
   102	                len(items), max_docs,
   103	            )
   104	            items = items[:max_docs]
   105	
   106	        total = 0
   107	        for memory_id, row in items:
   108	            result = await self.index_knowledge(memory_id, row)
   109	            total += result["chunks_indexed"]
   110	
   111	        self._conn.commit()
   112	        return {"docs_indexed": len(items), "chunks_indexed": total}
   113	
   114	    def delete_knowledge_index(self, memory_id: str, chunk_count: int = 0) -> None:
   115	        """Remove lexical + vector entries for a knowledge row."""
   116	        for i in range(max(chunk_count, 1)):
   117	            chunk_id = f"{memory_id}:{i}"
   118	            self._lexical.delete_chunk(chunk_id)
   119	        if self._vector:
   120	            self._vector.delete(memory_id)
   121	        self._conn.commit()