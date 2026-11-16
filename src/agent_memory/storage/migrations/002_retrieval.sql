-- Migration 002: retrieval infrastructure (Phase 4)
-- Adds the chunk index table backing FTS5 search and an outbox-driven
-- indexing job queue.

PRAGMA foreign_keys = ON;

-- Materialized chunk index: one row per indexed chunk.
-- Lexical search joins FTS5 results against this table so we can filter
-- by project/status at query time.
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    memory_id TEXT NOT NULL REFERENCES knowledge(memory_id),
    document_type TEXT NOT NULL DEFAULT 'knowledge',
    chunk_index INTEGER NOT NULL DEFAULT 0,
    char_start INTEGER NOT NULL DEFAULT 0,
    char_end INTEGER NOT NULL DEFAULT 0,
    token_estimate INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    indexed_at TEXT NOT NULL,
    UNIQUE (memory_id, chunk_index)
);

CREATE INDEX idx_chunks_project ON chunks(project_id, active);
CREATE INDEX idx_chunks_memory ON chunks(memory_id, chunk_index);

-- FTS5 index over chunks. content= is manual-synced: the chunk text is
-- written explicitly to keep FTS rows consistent with the chunks table.
-- (Replaces the Phase 1 memory_fts placeholder which indexes knowledge rows.)
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    project_id UNINDEXED,
    entity_id UNINDEXED,
    document_type UNINDEXED,
    title,
    summary,
    text,
    active UNINDEXED,
    tokenize = "unicode61"
);

-- Indexing job queue (outbox-driven batch jobs).
CREATE TABLE IF NOT EXISTS index_jobs (
    job_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    job_type TEXT NOT NULL DEFAULT 'index'
        CHECK (job_type IN ('index', 'delete')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_index_jobs_pending ON index_jobs(status, created_at) WHERE status = 'pending';
