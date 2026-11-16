# Data Model

## Identity Hierarchy

```
Project (project_id)
 ├── Repository (repository_id, remote_url_hash, root_fingerprint)
 │    └── Workspace (workspace_id, canonical_path, worktree_id)
 │         └── Session (session_id, agent_type, native_session_id)
 │              └── Run (run_id, task_id, head_sha_start/end)
 │                   └── Event (event_id, sequence_no, payload)
 │                   └── Checkpoint (checkpoint_id, summary)
 └── Task (task_id, title, status, revision, owner_session_id)
      ├── Handoff (handoff_id, source_agent, summary, revision)
      └── Knowledge (memory_id, scope, type, status, revision)
           └── KnowledgeRevision (memory_id, revision)
```

## Key Invariants

1. A **Project** may have multiple Repositories and Workspaces.
2. A **Task** may span multiple Sessions and Runs (cross-agent handoff).
3. A **Session** belongs to exactly one Workspace and one AgentType.
4. A **Run** belongs to exactly one Session and optionally one Task.
5. **Events** are immutable; deduplication uses `(run_id, sequence_no)` or `event_id`.
6. **Knowledge** uses optimistic locking via `revision`; updates must supply `expected_revision`.
7. **Handoff** is versioned per Task; the latest non-stale handoff is authoritative.

## State Machines

### Task
```
pending -> active -> blocked -> active -> completed
                \----------------------> cancelled
```

### Run
```
running -> completed
        -> failed
        -> cancelled
        -> interrupted (recovery required)
```

### Knowledge
```
candidate -> accepted -> superseded
    \------> rejected
    \------> archived
```

## Scope Levels

| Scope     | Visibility                        |
|-----------|-----------------------------------|
| run       | Current run only                  |
| task      | Same logical task across agents   |
| project   | All sessions in one project       |
| global    | Cross-project (requires explicit approval) |

## SQLite PRAGMAs

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = FULL;
```

- `journal_mode` is a persistent database setting.
- `foreign_keys` and `busy_timeout` must be set on every new connection.
- All write transactions must be short; never block on BGE-M3 or LLM inside a tx.


## Retrieval Index (Phase 4)

The retrieval layer maintains a materialized chunk index alongside
knowledge. FTS5 handles lexical search; sqlite-vec handles dense
vector search when available. Both are fused with RRF.

```
knowledge (memory_id, revision)
 └── chunks (chunk_id, project_id, memory_id, chunk_index, text, active)
      ├── chunks_fts (FTS5 virtual table over chunk text)
      └── memory_vectors (sqlite-vec virtual table, when available)
```

- `chunk_id` is `{memory_id}:{chunk_index}`.
- `chunks.active=0` rows are excluded from search.
- `index_jobs` queue drives batch indexing out-of-band.

## Governance Operations (Phase 6)

| Operation             | Terminal? | Target status |
|-----------------------|-----------|---------------|
| approve candidate      | no        | accepted        |
| reject candidate       | yes       | rejected        |
| archive knowledge      | yes       | archived        |
| supersede (old → new)  | yes       | superseded      |

Governance metrics (via `governance_summary`):
- status_counts (candidate / accepted / superseded / rejected / archived)
- potential_supersessions (content similarity heuristic, same type)
- potential_duplicates (title + content similarity)
- stale_items (accepted, not updated within `max_age_days`)
