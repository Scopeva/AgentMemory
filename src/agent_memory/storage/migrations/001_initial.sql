-- Migration 001: initial schema
-- Apply after enabling WAL and foreign_keys.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repositories (
    repository_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    remote_url_hash TEXT NOT NULL,
    root_fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (project_id, remote_url_hash)
);

CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL REFERENCES repositories(repository_id),
    canonical_path TEXT NOT NULL,
    worktree_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (repository_id, canonical_path)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    agent_type TEXT NOT NULL,
    native_session_id TEXT,
    workspace_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_sessions_workspace ON sessions(workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'blocked', 'completed', 'cancelled')),
    revision INTEGER NOT NULL DEFAULT 1,
    owner_session_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_tasks_project ON tasks(project_id, status);
CREATE INDEX idx_tasks_owner ON tasks(owner_session_id);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    task_id TEXT REFERENCES tasks(task_id),
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed', 'cancelled', 'interrupted')),
    head_sha_start TEXT,
    head_sha_end TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE INDEX idx_runs_session ON runs(session_id, started_at DESC);
CREATE INDEX idx_runs_task ON runs(task_id, started_at DESC);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    event_type TEXT NOT NULL,
    sequence_no INTEGER,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (run_id, sequence_no)
);

CREATE INDEX idx_events_run ON events(run_id, created_at);

CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    source_revision TEXT,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_checkpoints_run ON checkpoints(run_id, created_at DESC);

CREATE TABLE IF NOT EXISTS handoffs (
    handoff_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    source_agent TEXT NOT NULL,
    source_session_id TEXT,
    source_run_id TEXT,
    source_workspace_id TEXT,
    source_head_sha TEXT,
    state TEXT NOT NULL DEFAULT 'in_progress',
    summary TEXT NOT NULL,
    completed_json TEXT NOT NULL DEFAULT '[]',
    pending_json TEXT NOT NULL DEFAULT '[]',
    blockers_json TEXT NOT NULL DEFAULT '[]',
    decisions_json TEXT NOT NULL DEFAULT '[]',
    verification_refs_json TEXT NOT NULL DEFAULT '[]',
    next_actions_json TEXT NOT NULL DEFAULT '[]',
    revision INTEGER NOT NULL DEFAULT 1,
    is_stale INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_handoffs_task ON handoffs(task_id, revision DESC);
CREATE INDEX idx_handoffs_workspace ON handoffs(source_workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS knowledge (
    memory_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    scope TEXT NOT NULL DEFAULT 'project'
        CHECK (scope IN ('run', 'task', 'project', 'global')),
    type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate', 'accepted', 'superseded', 'rejected', 'archived')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    current_source_revision TEXT,
    supersedes_memory_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_knowledge_project ON knowledge(project_id, status);
CREATE INDEX idx_knowledge_type ON knowledge(type, status);

CREATE TABLE IF NOT EXISTS knowledge_revisions (
    memory_id TEXT NOT NULL REFERENCES knowledge(memory_id),
    revision INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    PRIMARY KEY (memory_id, revision)
);

CREATE TABLE IF NOT EXISTS knowledge_sources (
    source_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES knowledge(memory_id),
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    verified_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_knowledge_sources_memory ON knowledge_sources(memory_id);

CREATE TABLE IF NOT EXISTS memory_candidates (
    candidate_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    run_id TEXT REFERENCES runs(run_id),
    idempotency_key TEXT NOT NULL,
    memory_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (project_id, idempotency_key)
);

CREATE INDEX idx_memory_candidates_project ON memory_candidates(project_id, status);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES memory_candidates(candidate_id),
    decision TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    payload_json TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT
);

CREATE INDEX idx_jobs_status ON jobs(status, updated_at);

CREATE TABLE IF NOT EXISTS outbox (
    outbox_id TEXT PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT
);

CREATE INDEX idx_outbox_unpublished ON outbox(published_at) WHERE published_at IS NULL;

-- FTS5 virtual table for lexical search (materialized later from knowledge).
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    memory_id UNINDEXED,
    title,
    content,
    tokenize = "unicode61"
);

-- sqlite-vec virtual table; dimension must match embedding config (1024).
-- Create only if sqlite-vec extension is available; Phase 1 does not require it.
-- CREATE VIRTUAL TABLE IF NOT EXISTS memory_vectors USING vec0(
--     memory_id TEXT,
--     chunk_id TEXT,
--     embedding FLOAT[1024]
-- );
