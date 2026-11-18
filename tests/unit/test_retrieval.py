"""Unit tests for Phase 4 hybrid retrieval.

Covers chunker, embedding provider mock, RRF fusion, hybrid search,
and indexing worker.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Make src importable
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_memory.config import EmbeddingConfig, RetrievalConfig
from agent_memory.retrieval.chunker import (
    ChunkerConfig,
    chunk_document,
    chunk_knowledge,
    chunk_conversation_turns,
)
from agent_memory.retrieval.embedding import BgeM3HttpProvider, create_provider
from agent_memory.retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion
from agent_memory.retrieval.indexing import IndexingWorker
from agent_memory.retrieval.lexical import LexicalIndex, fts5_query
from agent_memory.retrieval.vector import VectorIndex, vec_available


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------


class TestChunker:
    def test_short_document_single_chunk(self):
        chunks = chunk_document("Hello world", ChunkerConfig(max_chars=800))
        assert len(chunks) == 1
        assert chunks[0].text == "Hello world"

    def test_long_document_splits_on_max_chars(self):
        text = "word " * 500  # 2500 chars
        chunks = chunk_document(text, ChunkerConfig(max_chars=800, min_chars=200))
        assert len(chunks) > 1
        for c in chunks:
            assert len(c.text) <= 800

    def test_headers_split_sections(self):
        text = "# Intro\nShort intro.\n\n## Section A\nSection A content.\n\n## Section B\nSection B content."
        chunks = chunk_document(text, ChunkerConfig(max_chars=800))
        assert len(chunks) >= 1
        joined = " ".join(c.text for c in chunks)
        assert "Section A" in joined
        assert "Section B" in joined

    def test_token_estimate(self):
        chunks = chunk_document("x" * 800, ChunkerConfig(max_chars=800))
        assert chunks[0].token_estimate == 200  # 800 // 4

    def test_chunk_knowledge_uses_title_summary_content(self):
        k = {"title": "T", "content": "C" * 900, "summary": "S"}
        chunks = chunk_knowledge(k, ChunkerConfig(max_chars=200))
        assert len(chunks) > 1
        for c in chunks:
            assert len(c.text) <= 200

    def test_chunk_conversation_turns_groups_by_author(self):
        turns = [
            {"author": "alice", "content": "hi"},
            {"author": "alice", "content": "hello"},
            {"author": "bob", "content": "hey"},
            {"author": "bob", "content": "yo"},
            {"author": "alice", "content": "again"},
        ]
        chunks = chunk_conversation_turns(turns, ChunkerConfig(max_chars=1000))
        # groups: [alice(2)], [bob(2)], [alice(1)] = 3 chunks
        assert len(chunks) == 3


# ---------------------------------------------------------------------------
# FTS5 query builder
# ---------------------------------------------------------------------------


class TestFts5Query:
    def test_plain_query_quoted(self):
        q = fts5_query("fix memory leak")
        assert '"fix"' in q
        assert '"memory"' in q
        assert '"leak"' in q

    def test_explicit_fts_query_passthrough(self):
        q = fts5_query("ignored", fts_query='"foo" OR "bar"')
        assert q == '"foo" OR "bar"'

    def test_empty_and_quoted_tokens_are_safe(self):
        assert fts5_query("   ") == ""
        assert fts5_query('alpha"') == '"alpha"""'


# ---------------------------------------------------------------------------
# Embedding provider (mocked HTTP)
# ---------------------------------------------------------------------------


class TestBgeM3Provider:
    @pytest.mark.asyncio
    async def test_ollama_shape(self):
        provider = BgeM3HttpProvider(
            EmbeddingConfig(endpoint="http://127.0.0.1:9999", model="bge-m3", dimension=8)
        )
        # Mock httpx.AsyncClient.post to return ollama shape
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"embeddings": [[float(i) for i in range(8)] for _ in range(3)]}

        async def mock_post(url, json=None, timeout=None, **kw):
            if "/api/embed" in url:
                return mock_resp
            raise Exception("unexpected url " + url)

        provider._client.post = mock_post
        vecs = await provider.embed(["a", "b", "c"])
        assert len(vecs) == 3
        assert len(vecs[0]) == 8
        assert provider.dimension == 8

    @pytest.mark.asyncio
    async def test_openai_shape(self):
        provider = BgeM3HttpProvider(
            EmbeddingConfig(endpoint="http://127.0.0.1:9999", model="bge-m3", dimension=4)
        )
        provider._shape = "openai"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"embedding": [1.0, 2.0, 3.0, 4.0]}]}

        async def mock_post(url, json=None, timeout=None, **kw):
            if "/embeddings" in url:
                return mock_resp
            raise Exception("unexpected url " + url)

        provider._client.post = mock_post
        vecs = await provider.embed(["test"])
        assert vecs == [[1.0, 2.0, 3.0, 4.0]]

    def test_create_provider_factory(self):
        p = create_provider(EmbeddingConfig(provider="bge-m3-http"))
        assert isinstance(p, BgeM3HttpProvider)

    def test_create_provider_unknown_raises(self):
        with pytest.raises(ValueError):
            create_provider(EmbeddingConfig(provider="unknown"))


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------


class TestRRF:
    def test_basic_fusion(self):
        list_a = ["x", "y", "z"]
        list_b = ["y", "x", "w"]
        scores = reciprocal_rank_fusion([list_a, list_b], k=60)
        # y is rank 1 in b and rank 2 in a -> highest
        assert scores["y"] == (1 / 61) + (1 / 62)
        assert scores["w"] == 1 / 63
        assert set(scores) == {"x", "y", "z", "w"}

    def test_single_list(self):
        scores = reciprocal_rank_fusion([["a", "b", "c"]], k=60)
        assert scores["a"] > scores["b"] > scores["c"]


# ---------------------------------------------------------------------------
# Lexical index (in-memory sqlite)
# ---------------------------------------------------------------------------


@pytest.fixture
def sync_conn():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE VIRTUAL TABLE chunks_fts USING fts5("
        "chunk_id UNINDEXED, project_id UNINDEXED, entity_id UNINDEXED, "
        "document_type UNINDEXED, title, summary, text, active UNINDEXED, "
        "tokenize = 'unicode61')"
    )
    conn.commit()
    yield conn
    conn.close()


class TestLexicalIndex:
    def test_upsert_and_search(self, sync_conn):
        lex = LexicalIndex(sync_conn)
        lex.upsert_chunk(
            chunk_id="c1",
            project_id="p1",
            entity_id="k1",
            document_type="knowledge",
            text="use pytest for unit testing",
            title="Testing",
            summary="",
        )
        lex.upsert_chunk(
            chunk_id="c2",
            project_id="p1",
            entity_id="k2",
            document_type="knowledge",
            text="use jest for frontend tests",
            title="Frontend",
            summary="",
        )
        results = lex.search("p1", '"pytest"')
        assert len(results) == 1
        assert results[0]["chunk_id"] == "c1"

    def test_project_filter(self, sync_conn):
        lex = LexicalIndex(sync_conn)
        lex.upsert_chunk("c1", "p1", "k1", "knowledge", "alpha", "", "")
        lex.upsert_chunk("c2", "p2", "k2", "knowledge", "alpha", "", "")
        assert len(lex.search("p1", '"alpha"')) == 1
        assert len(lex.search("p2", '"alpha"')) == 1


# ---------------------------------------------------------------------------
# Vector index (graceful no-op without sqlite-vec)
# ---------------------------------------------------------------------------


class TestVectorIndex:
    def test_noop_when_unavailable(self, sync_conn):
        vi = VectorIndex(sync_conn, dimension=8)
        if vi.available:
            # sqlite-vec present: verify upsert works
            vi.upsert("k1", "c1", [0.1] * 8)
            results = vi.search([0.1] * 8, limit=5)
            assert len(results) >= 1
        else:
            # unavailable: methods are safe no-ops
            vi.upsert("k1", "c1", [0.1] * 8)
            assert vi.search([0.1] * 8) == []
            vi.delete("k1")
            vi.delete("k1", ["c1"])


# ---------------------------------------------------------------------------
# Hybrid retriever
# ---------------------------------------------------------------------------


class TestHybridRetriever:
    def test_lexical_only_when_no_vector(self, sync_conn):
        lex = LexicalIndex(sync_conn)
        lex.upsert_chunk("c1", "p1", "k1", "knowledge", "deploy pipeline", "", "")
        cfg = RetrievalConfig()
        retriever = HybridRetriever(lex, None, cfg)
        result = retriever.search("p1", "deploy", None)
        assert result["retrieval_mode"] == "lexical_only"
        assert "c1" in result["chunk_ids"]

    def test_none_when_no_hits(self, sync_conn):
        lex = LexicalIndex(sync_conn)
        cfg = RetrievalConfig()
        retriever = HybridRetriever(lex, None, cfg)
        result = retriever.search("p1", "zzz_no_match_zzz", None)
        assert result["retrieval_mode"] == "none"
        assert result["chunk_ids"] == []

    def test_hybrid_fuses_both(self, sync_conn):
        lex = LexicalIndex(sync_conn)
        lex.upsert_chunk("c1", "p1", "k1", "knowledge", "deploy pipeline", "", "")
        lex.upsert_chunk("c2", "p1", "k2", "knowledge", "deploy strategy", "", "")

        # Fake vector index that returns c2 first
        fake_vec = MagicMock()
        fake_vec.available = True
        fake_vec.search.return_value = [
            {"chunk_id": "c2", "rank": 1},
            {"chunk_id": "c1", "rank": 2},
        ]

        cfg = RetrievalConfig()
        retriever = HybridRetriever(lex, fake_vec, cfg)
        result = retriever.search("p1", "deploy", [0.1] * 8)
        assert result["retrieval_mode"] == "hybrid"
        assert len(result["chunk_ids"]) == 2


# ---------------------------------------------------------------------------
# Indexing worker
# ---------------------------------------------------------------------------


@pytest.fixture
def index_conn():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE chunks (
            chunk_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            memory_id TEXT NOT NULL,
            document_type TEXT NOT NULL DEFAULT 'knowledge',
            chunk_index INTEGER NOT NULL DEFAULT 0,
            char_start INTEGER NOT NULL DEFAULT 0,
            char_end INTEGER NOT NULL DEFAULT 0,
            token_estimate INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            indexed_at TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            chunk_id UNINDEXED, project_id UNINDEXED, entity_id UNINDEXED,
            document_type UNINDEXED, title, summary, text, active UNINDEXED,
            tokenize = 'unicode61'
        );
        """
    )
    conn.commit()
    yield conn
    conn.close()


class TestIndexingWorker:
    @pytest.mark.asyncio
    async def test_index_knowledge_creates_chunks(self, index_conn):
        worker = IndexingWorker(
            index_conn, RetrievalConfig(), embedding_provider=None
        )
        result = await worker.index_knowledge(
            "k1",
            {"project_id": "p1", "title": "T", "content": "C" * 300, "summary": ""},
        )
        assert result["chunks_indexed"] >= 1
        # Verify FTS row exists
        row = index_conn.execute(
            "SELECT chunk_id FROM chunks_fts WHERE chunk_id LIKE 'k1:%'"
        ).fetchall()
        assert len(row) == result["chunks_indexed"]
        chunks = index_conn.execute(
            "SELECT chunk_id FROM chunks WHERE memory_id = 'k1'"
        ).fetchall()
        assert len(chunks) == result["chunks_indexed"]

    @pytest.mark.asyncio
    async def test_index_batch_truncates(self, index_conn):
        worker = IndexingWorker(
            index_conn,
            RetrievalConfig(batch_index_max_docs=2),
            embedding_provider=None,
        )
        items = [(f"k{i}", {"project_id": "p1", "title": f"T{i}", "content": f"C{i}" * 50}) for i in range(5)]
        result = await worker.index_batch(items)
        assert result["docs_indexed"] == 2  # capped

    @pytest.mark.asyncio
    async def test_delete_knowledge_index(self, index_conn):
        worker = IndexingWorker(index_conn, RetrievalConfig(), embedding_provider=None)
        await worker.index_knowledge(
            "k1", {"project_id": "p1", "title": "T", "content": "word " * 500}
        )
        worker.delete_knowledge_index("k1")
        assert index_conn.execute("SELECT count(*) FROM chunks_fts").fetchone()[0] == 0
        assert index_conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0

    @pytest.mark.asyncio
    async def test_reindex_replaces_all_old_chunks(self, index_conn):
        worker = IndexingWorker(
            index_conn,
            RetrievalConfig(chunk_max_chars=10, chunk_min_chars=1),
            embedding_provider=None,
        )
        await worker.index_knowledge(
            "k1", {"project_id": "p1", "title": "T", "content": "alpha " + "x " * 30}
        )
        assert index_conn.execute("SELECT count(*) FROM chunks_fts").fetchone()[0] > 1

        result = await worker.index_knowledge(
            "k1", {"project_id": "p1", "title": "T", "content": "short"}
        )
        assert index_conn.execute("SELECT count(*) FROM chunks_fts").fetchone()[0] == result["chunks_indexed"]
        assert index_conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == result["chunks_indexed"]

    @pytest.mark.asyncio
    async def test_index_with_mocked_embedder(self, index_conn):
        class MockEmbedder:
            dimension = 8
            async def embed(self, texts):
                return [[0.5] * 8 for _ in texts]

        worker = IndexingWorker(
            index_conn, RetrievalConfig(), embedding_provider=MockEmbedder()
        )
        result = await worker.index_knowledge(
            "k1", {"project_id": "p1", "title": "T", "content": "C" * 300}
        )
        assert result["chunks_indexed"] >= 1
        # Vector upsert is no-op if sqlite-vec unavailable, but shouldn't error
        assert worker.vector is None or not worker.vector.available
