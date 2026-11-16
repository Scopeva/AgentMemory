     1	-- Migration 001: initial schema
     2	-- Apply after enabling WAL and foreign_keys.
     3	
     4	PRAGMA foreign_keys = ON;
     5	
     6	CREATE TABLE IF NOT EXISTS schema_migrations (
     7	    version INTEGER PRIMARY KEY,
     8	    applied_at TEXT NOT NULL
     9	);
    10	
    11	CREATE TABLE IF NOT EXISTS projects (
    12	    project_id TEXT PRIMARY KEY,
    13	    name TEXT NOT NULL,
    14	    status TEXT NOT NULL DEFAULT 'active'
    15	        CHECK (status IN ('active', 'archived')),
    16	    created_at TEXT NOT NULL,
    17	    updated_at TEXT NOT NULL
    18	);
    19	
    20	CREATE TABLE IF NOT EXISTS repositories (
    21	    repository_id TEXT PRIMARY KEY,
    22	    project_id TEXT NOT NULL REFERENCES projects(project_id),
    23	    remote_url_hash TEXT NOT NULL,
    24	    root_fingerprint TEXT NOT NULL,
    25	    created_at TEXT NOT NULL,
    26	    UNIQUE (project_id, remote_url_hash)
    27	);
    28	
    29	CREATE TABLE IF NOT EXISTS workspaces (
    30	    workspace_id TEXT PRIMARY KEY,
    31	    repository_id TEXT NOT NULL REFERENCES repositories(repository_id),
    32	    canonical_path TEXT NOT NULL,
    33	    worktree_id TEXT,
    34	    created_at TEXT NOT NULL,
    35	    UNIQUE (repository_id, canonical_path)
    36	);
    37	
    38	CREATE TABLE IF NOT EXISTS sessions (
    39	    session_id TEXT PRIMARY KEY,
    40	    agent_type TEXT NOT NULL,
    41	    native_session_id TEXT,
    42	    workspace_id TEXT,
    43	    created_at TEXT NOT NULL
    44	);
    45	
    46	CREATE INDEX idx_sessions_workspace ON sessions(workspace_id, created_at DESC);
    47	
    48	CREATE TABLE IF NOT EXISTS tasks (
    49	    task_id TEXT PRIMARY KEY,
    50	    project_id TEXT NOT NULL REFERENCES projects(project_id),
    51	    title TEXT NOT NULL,
    52	    status TEXT NOT NULL DEFAULT 'pending'
    53	        CHECK (status IN ('pending', 'active', 'blocked', 'completed', 'cancelled')),
    54	    revision INTEGER NOT NULL DEFAULT 1,
    55	    owner_session_id TEXT,
    56	    created_at TEXT NOT NULL,
    57	    updated_at TEXT NOT NULL
    58	);
    59	
    60	CREATE INDEX idx_tasks_project ON tasks(project_id, status);
    61	CREATE INDEX idx_tasks_owner ON tasks(owner_session_id);
    62	
    63	CREATE TABLE IF NOT EXISTS runs (
    64	    run_id TEXT PRIMARY KEY,
    65	    task_id TEXT REFERENCES tasks(task_id),
    66	    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    67	    status TEXT NOT NULL DEFAULT 'running'
    68	        CHECK (status IN ('running', 'completed', 'failed', 'cancelled', 'interrupted')),
    69	    head_sha_start TEXT,
    70	    head_sha_end TEXT,
    71	    started_at TEXT NOT NULL,
    72	    ended_at TEXT
    73	);
    74	
    75	CREATE INDEX idx_runs_session ON runs(session_id, started_at DESC);
    76	CREATE INDEX idx_runs_task ON runs(task_id, started_at DESC);
    77	
    78	CREATE TABLE IF NOT EXISTS events (
    79	    event_id TEXT PRIMARY KEY,
    80	    run_id TEXT NOT NULL REFERENCES runs(run_id),
    81	    event_type TEXT NOT NULL,
    82	    sequence_no INTEGER,
    83	    payload_json TEXT NOT NULL,
    84	    created_at TEXT NOT NULL,
    85	    UNIQUE (run_id, sequence_no)
    86	);
    87	
    88	CREATE INDEX idx_events_run ON events(run_id, created_at);
    89	
    90	CREATE TABLE IF NOT EXISTS checkpoints (
    91	    checkpoint_id TEXT PRIMARY KEY,
    92	    run_id TEXT NOT NULL REFERENCES runs(run_id),
    93	    source_revision TEXT,
    94	    summary TEXT NOT NULL,
    95	    created_at TEXT NOT NULL
    96	);
    97	
    98	CREATE INDEX idx_checkpoints_run ON checkpoints(run_id, created_at DESC);
    99	
   100	CREATE TABLE IF NOT EXISTS handoffs (
   101	    handoff_id TEXT PRIMARY KEY,
   102	    task_id TEXT NOT NULL REFERENCES tasks(task_id),
   103	    source_agent TEXT NOT NULL,
   104	    source_session_id TEXT,
   105	    source_run_id TEXT,
   106	    source_workspace_id TEXT,
   107	    source_head_sha TEXT,
   108	    state TEXT NOT NULL DEFAULT 'in_progress',
   109	    summary TEXT NOT NULL,
   110	    completed_json TEXT NOT NULL DEFAULT '[]',
   111	    pending_json TEXT NOT NULL DEFAULT '[]',
   112	    blockers_json TEXT NOT NULL DEFAULT '[]',
   113	    decisions_json TEXT NOT NULL DEFAULT '[]',
   114	    verification_refs_json TEXT NOT NULL DEFAULT '[]',
   115	    next_actions_json TEXT NOT NULL DEFAULT '[]',
   116	    revision INTEGER NOT NULL DEFAULT 1,
   117	    is_stale INTEGER NOT NULL DEFAULT 0,
   118	    created_at TEXT NOT NULL,
   119	    updated_at TEXT NOT NULL
   120	);
   121	
   122	CREATE INDEX idx_handoffs_task ON handoffs(task_id, revision DESC);
   123	CREATE INDEX idx_handoffs_workspace ON handoffs(source_workspace_id, created_at DESC);
   124	
   125	CREATE TABLE IF NOT EXISTS knowledge (
   126	    memory_id TEXT PRIMARY KEY,
   127	    project_id TEXT NOT NULL REFERENCES projects(project_id),
   128	    scope TEXT NOT NULL DEFAULT 'project'
   129	        CHECK (scope IN ('run', 'task', 'project', 'global')),
   130	    type TEXT NOT NULL,
   131	    status TEXT NOT NULL DEFAULT 'candidate'
   132	        CHECK (status IN ('candidate', 'accepted', 'superseded', 'rejected', 'archived')),
   133	    title TEXT NOT NULL,
   134	    content TEXT NOT NULL,
   135	    revision INTEGER NOT NULL DEFAULT 1,
   136	    current_source_revision TEXT,
   137	    supersedes_memory_id TEXT,
   138	    created_at TEXT NOT NULL,
   139	    updated_at TEXT NOT NULL
   140	);
   141	
   142	CREATE INDEX idx_knowledge_project ON knowledge(project_id, status);
   143	CREATE INDEX idx_knowledge_type ON knowledge(type, status);
   144	
   145	CREATE TABLE IF NOT EXISTS knowledge_revisions (
   146	    memory_id TEXT NOT NULL REFERENCES knowledge(memory_id),
   147	    revision INTEGER NOT NULL,
   148	    title TEXT NOT NULL,
   149	    content TEXT NOT NULL,
   150	    status TEXT NOT NULL,
   151	    changed_by TEXT NOT NULL,
   152	    changed_at TEXT NOT NULL,
   153	    PRIMARY KEY (memory_id, revision)
   154	);
   155	
   156	CREATE TABLE IF NOT EXISTS knowledge_sources (
   157	    source_id TEXT PRIMARY KEY,
   158	    memory_id TEXT NOT NULL REFERENCES knowledge(memory_id),
   159	    kind TEXT NOT NULL,
   160	    value TEXT NOT NULL,
   161	    verified_at TEXT,
   162	    created_at TEXT NOT NULL
   163	);
   164	
   165	CREATE INDEX idx_knowledge_sources_memory ON knowledge_sources(memory_id);
   166	
   167	CREATE TABLE IF NOT EXISTS memory_candidates (
   168	    candidate_id TEXT PRIMARY KEY,
   169	    project_id TEXT NOT NULL REFERENCES projects(project_id),
   170	    run_id TEXT REFERENCES runs(run_id),
   171	    idempotency_key TEXT NOT NULL,
   172	    memory_json TEXT NOT NULL,
   173	    status TEXT NOT NULL DEFAULT 'pending'
   174	        CHECK (status IN ('pending', 'approved', 'rejected', 'archived')),
   175	    created_at TEXT NOT NULL,
   176	    updated_at TEXT NOT NULL,
   177	    UNIQUE (project_id, idempotency_key)
   178	);
   179	
   180	CREATE INDEX idx_memory_candidates_project ON memory_candidates(project_id, status);
   181	
   182	CREATE TABLE IF NOT EXISTS approvals (
   183	    approval_id TEXT PRIMARY KEY,
   184	    candidate_id TEXT NOT NULL REFERENCES memory_candidates(candidate_id),
   185	    decision TEXT NOT NULL,
   186	    decided_by TEXT NOT NULL,
   187	    decided_at TEXT NOT NULL
   188	);
   189	
   190	CREATE TABLE IF NOT EXISTS jobs (
   191	    job_id TEXT PRIMARY KEY,
   192	    job_type TEXT NOT NULL,
   193	    status TEXT NOT NULL DEFAULT 'pending'
   194	        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
   195	    payload_json TEXT NOT NULL,
   196	    attempts INTEGER NOT NULL DEFAULT 0,
   197	    created_at TEXT NOT NULL,
   198	    updated_at TEXT NOT NULL,
   199	    started_at TEXT,
   200	    finished_at TEXT,

... [truncated, showing 200/232 lines, 7898/9059 chars]