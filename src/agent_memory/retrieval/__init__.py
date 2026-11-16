"""Hybrid retrieval package: chunking, embedding, lexical, vector, hybrid, indexing, dispatch."""

from agent_memory.retrieval.chunker import Chunk, ChunkerConfig, chunk_document, chunk_knowledge, chunk_conversation_turns, build_search_text
from agent_memory.retrieval.embedding import EmbeddingProvider, BgeM3HttpProvider, create_provider
from agent_memory.retrieval.lexical import LexicalIndex, fts5_query
from agent_memory.retrieval.vector import VectorIndex, vec_available, create_vector_index, ensure_vec0
from agent_memory.retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion
from agent_memory.retrieval.indexing import IndexingWorker
from agent_memory.retrieval.dispatcher import JobDispatcher
from agent_memory.retrieval.search import SearchService

__all__ = [
    "Chunk", "ChunkerConfig", "chunk_document", "chunk_knowledge",
    "chunk_conversation_turns", "build_search_text",
    "EmbeddingProvider", "BgeM3HttpProvider", "create_provider",
    "LexicalIndex", "fts5_query",
    "VectorIndex", "vec_available", "create_vector_index", "ensure_vec0",
    "HybridRetriever", "reciprocal_rank_fusion",
    "IndexingWorker", "JobDispatcher", "SearchService",
]
