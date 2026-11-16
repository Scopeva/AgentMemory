     1	# Data Model
     2	
     3	## Identity Hierarchy
     4	
     5	```
     6	Project (project_id)
     7	 ├── Repository (repository_id, remote_url_hash, root_fingerprint)
     8	 │    └── Workspace (workspace_id, canonical_path, worktree_id)
     9	 │         └── Session (session_id, agent_type, native_session_id)
    10	 │              └── Run (run_id, task_id, head_sha_start/end)
    11	 │                   └── Event (event_id, sequence_no, payload)
    12	 │                   └── Checkpoint (checkpoint_id, summary)
    13	 └── Task (task_id, title, status, revision, owner_session_id)
    14	      ├── Handoff (handoff_id, source_agent, summary, revision)
    15	      └── Knowledge (memory_id, scope, type, status, revision)
    16	           └── KnowledgeRevision (memory_id, revision)
    17	```
    18	
    19	## Key Invariants
    20	
    21	1. A **Project** may have multiple Repositories and Workspaces.
    22	2. A **Task** may span multiple Sessions and Runs (cross-agent handoff).
    23	3. A **Session** belongs to exactly one Workspace and one AgentType.
    24	4. A **Run** belongs to exactly one Session and optionally one Task.
    25	5. **Events** are immutable; deduplication uses `(run_id, sequence_no)` or `event_id`.
    26	6. **Knowledge** uses optimistic locking via `revision`; updates must supply `expected_revision`.
    27	7. **Handoff** is versioned per Task; the latest non-stale handoff is authoritative.
    28	
    29	## State Machines
    30	
    31	### Task
    32	```
    33	pending -> active -> blocked -> active -> completed
    34	                \----------------------> cancelled
    35	```
    36	
    37	### Run
    38	```
    39	running -> completed
    40	        -> failed
    41	        -> cancelled
    42	        -> interrupted (recovery required)
    43	```
    44	
    45	### Knowledge
    46	```
    47	candidate -> accepted -> superseded
    48	    \------> rejected
    49	    \------> archived
    50	```
    51	
    52	## Scope Levels
    53	
    54	| Scope     | Visibility                        |
    55	|-----------|-----------------------------------|
    56	| run       | Current run only                  |
    57	| task      | Same logical task across agents   |
    58	| project   | All sessions in one project       |
    59	| global    | Cross-project (requires explicit approval) |
    60	
    61	## SQLite PRAGMAs
    62	
    63	```sql
    64	PRAGMA journal_mode = WAL;
    65	PRAGMA foreign_keys = ON;
    66	PRAGMA busy_timeout = 5000;
    67	PRAGMA synchronous = FULL;
    68	```
    69	
    70	- `journal_mode` is a persistent database setting.
    71	- `foreign_keys` and `busy_timeout` must be set on every new connection.
    72	- All write transactions must be short; never block on BGE-M3 or LLM inside a tx.