     1	"""Unit tests for Phase 4 hybrid retrieval.
     2	
     3	Covers chunker, embedding provider mock, RRF fusion, hybrid search,
     4	and indexing worker.
     5	"""
     6	
     7	from __future__ import annotations
     8	
     9	import os
    10	import sys
    11	import tempfile
    12	from dataclasses import dataclass, field
    13	from pathlib import Path
    14	from unittest.mock import AsyncMock, MagicMock
    15	
    16	import pytest
    17	
    18	# Make src importable
    19	sys.path.insert(0, str(Path(__file__).parent.parent))
    20	sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    21	
    22	from agent_memory.config import EmbeddingConfig, RetrievalConfig
    23	from agent_memory.retrieval.chunker import (
    24	    ChunkerConfig,
    25	    chunk_document,
    26	    chunk_knowledge,
    27	    chunk_conversation_turns,
    28	)
    29	from agent_memory.retrieval.embedding import BgeM3HttpProvider, create_provider
    30	from agent_memory.retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion
    31	from agent_memory.retrieval.indexing import IndexingWorker
    32	from agent_memory.retrieval.lexical import LexicalIndex, fts5_query
    33	from agent_memory.retrieval.vector import VectorIndex, vec_available
    34	
    35	
    36	# ---------------------------------------------------------------------------
    37	# Chunker
    38	# ---------------------------------------------------------------------------
    39	
    40	
    41	class TestChunker:
    42	    def test_short_document_single_chunk(self):
    43	        chunks = chunk_document("Hello world", ChunkerConfig(max_chars=800))
    44	        assert len(chunks) == 1
    45	        assert chunks[0].text == "Hello world"
    46	
    47	    def test_long_document_splits_on_max_chars(self):
    48	        text = "word " * 500  # 2500 chars
    49	        chunks = chunk_document(text, ChunkerConfig(max_chars=800, min_chars=200))
    50	        assert len(chunks) > 1
    51	        for c in chunks:
    52	            assert len(c.text) <= 800
    53	
    54	    def test_headers_split_sections(self):
    55	        text = "# Intro\nShort intro.\n\n## Section A\nSection A content.\n\n## Section B\nSection B content."
    56	        chunks = chunk_document(text, ChunkerConfig(max_chars=800))
    57	        assert len(chunks) >= 1
    58	        joined = " ".join(c.text for c in chunks)
    59	        assert "Section A" in joined
    60	        assert "Section B" in joined
    61	
    62	    def test_token_estimate(self):
    63	        chunks = chunk_document("x" * 800, ChunkerConfig(max_chars=800))
    64	        assert chunks[0].token_estimate == 200  # 800 // 4
    65	
    66	    def test_chunk_knowledge_uses_title_summary_content(self):
    67	        k = {"title": "T", "content": "C" * 900, "summary": "S"}
    68	        chunks = chunk_knowledge(k, ChunkerConfig(max_chars=200))
    69	        assert len(chunks) > 1
    70	        for c in chunks:
    71	            assert len(c.text) <= 200
    72	
    73	    def test_chunk_conversation_turns_groups_by_author(self):
    74	        turns = [
    75	            {"author": "alice", "content": "hi"},
    76	            {"author": "alice", "content": "hello"},
    77	            {"author": "bob", "content": "hey"},
    78	            {"author": "bob", "content": "yo"},
    79	            {"author": "alice", "content": "again"},
    80	        ]
    81	        chunks = chunk_conversation_turns(turns, ChunkerConfig(max_chars=1000))
    82	        # groups: [alice(2)], [bob(2)], [alice(1)] = 3 chunks
    83	        assert len(chunks) == 3
    84	
    85	
    86	# ---------------------------------------------------------------------------
    87	# FTS5 query builder
    88	# ---------------------------------------------------------------------------
    89	
    90	
    91	class TestFts5Query:
    92	    def test_plain_query_quoted(self):
    93	        q = fts5_query("fix memory leak")
    94	        assert '"fix"' in q
    95	        assert '"memory"' in q
    96	        assert '"leak"' in q
    97	
    98	    def test_explicit_fts_query_passthrough(self):
    99	        q = fts5_query("ignored", fts_query='"foo" OR "bar"')
   100	        assert q == '"foo" OR "bar"'
   101	
   102	
   103	# ---------------------------------------------------------------------------
   104	# Embedding provider (mocked HTTP)
   105	# ---------------------------------------------------------------------------
   106	
   107	
   108	class TestBgeM3Provider:
   109	    @pytest.mark.asyncio
   110	    async def test_ollama_shape(self):
   111	        provider = BgeM3HttpProvider(
   112	            EmbeddingConfig(endpoint="http://127.0.0.1:9999", model="bge-m3", dimension=8)
   113	        )
   114	        # Mock httpx.AsyncClient.post to return ollama shape
   115	        mock_resp = MagicMock()
   116	        mock_resp.status_code = 200
   117	        mock_resp.json.return_value = {"embeddings": [[float(i) for i in range(8)] for _ in range(3)]}
   118	
   119	        async def mock_post(url, json=None, timeout=None, **kw):
   120	            if "/api/embed" in url:
   121	                return mock_resp
   122	            raise Exception("unexpected url " + url)
   123	
   124	        provider._client.post = mock_post
   125	        vecs = await provider.embed(["a", "b", "c"])
   126	        assert len(vecs) == 3
   127	        assert len(vecs[0]) == 8
   128	        assert provider.dimension == 8
   129	
   130	    @pytest.mark.asyncio
   131	    async def test_openai_shape(self):
   132	        provider = BgeM3HttpProvider(
   133	            EmbeddingConfig(endpoint="http://127.0.0.1:9999", model="bge-m3", dimension=4)
   134	        )
   135	        provider._shape = "openai"
   136	        mock_resp = MagicMock()
   137	        mock_resp.status_code = 200
   138	        mock_resp.json.return_value = {"data": [{"embedding": [1.0, 2.0, 3.0, 4.0]}]}
   139	
   140	        async def mock_post(url, json=None, timeout=None, **kw):
   141	            if "/embeddings" in url:
   142	                return mock_resp
   143	            raise Exception("unexpected url " + url)
   144	
   145	        provider._client.post = mock_post
   146	        vecs = await provider.embed(["test"])
   147	        assert vecs == [[1.0, 2.0, 3.0, 4.0]]
   148	
   149	    def test_create_provider_factory(self):
   150	        p = create_provider(EmbeddingConfig(provider="bge-m3-http"))
   151	        assert isinstance(p, BgeM3HttpProvider)
   152	
   153	    def test_create_provider_unknown_raises(self):
   154	        with pytest.raises(ValueError):
   155	            create_provider(EmbeddingConfig(provider="unknown"))
   156	
   157	
   158	# ---------------------------------------------------------------------------
   159	# RRF fusion
   160	# ---------------------------------------------------------------------------
   161	
   162	
   163	class TestRRF:
   164	    def test_basic_fusion(self):
   165	        list_a = ["x", "y", "z"]
   166	        list_b = ["y", "x", "w"]
   167	        scores = reciprocal_rank_fusion([list_a, list_b], k=60)
   168	        # y is rank 1 in b and rank 2 in a -> highest
   169	        assert scores["y"] == (1 / 61) + (1 / 62)
   170	        assert scores["w"] == 1 / 63
   171	        assert set(scores) == {"x", "y", "z", "w"}
   172	
   173	    def test_single_list(self):
   174	        scores = reciprocal_rank_fusion([["a", "b", "c"]], k=60)
   175	        assert scores["a"] > scores["b"] > scores["c"]
   176	
   177	
   178	# ---------------------------------------------------------------------------
   179	# Lexical index (in-memory sqlite)
   180	# ---------------------------------------------------------------------------
   181	
   182	
   183	@pytest.fixture
   184	def sync_conn():
   185	    import sqlite3
   186	
   187	    conn = sqlite3.connect("

... [truncated, showing 200/390 lines, 8000/16852 chars]