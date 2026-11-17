# Local Agent Memory & Handoff Service

A local, desktop-free service that gives multiple coding agents (Pi, Codex,
OpenCode) shared long-term memory and clean task handoffs.

## Architecture

- **Core service**: FastMCP (agent-facing tools) + FastAPI (hook/event HTTP API)
- **Primary store**: SQLite in WAL mode
- **Retrieval**: FTS5 lexical search + sqlite-vec dense vectors (BGE-M3)
- **Background indexing**: `BackgroundIndexingLoop` (in `src/agent_memory/workers/`)
  drains the `index_jobs` outbox every `workers.interval_seconds` (30 s
  default); sleeps `workers.empty_backoff_seconds` (120 s default) when the
  queue is empty. Cadence is configurable via TOML and environment variables
  (see `config.example.toml` / `.env.example`).
- **LLM inference**: Uses the existing agent's own model; no separate LLM provider

## Getting Started

```bash
# Install
uv sync
# or
pip install -e .

# Run tests
pytest
```

## Configuration

Copy `config.example.toml` to `config.toml` and adjust paths. Environment
variables override TOML values; see `.env.example`.

| Section | Keys | Notes |
|---|---|---|
| `[server]` | `host`, `port`, `transport` | FastAPI + FastMCP bind |
| `[database]` | `path`, `journal_mode`, `busy_timeout_ms` | SQLite + WAL |
| `[embedding]` | `provider`, `endpoint`, `model`, `dimension`, `enabled` | BGE-M3 llama service |
| `[retrieval]` | `lexical_top_k`, `vector_top_k`, `final_top_k`, `rrf_k`, `chunk_max_chars`, `chunk_min_chars`, `batch_index_max_docs` | hybrid FTS5 + vector RRF fusion |
| `[memory]` | `auto_capture`, `approval_required_for_adr`, `max_context_tokens` | candidate/promotion policy |
| `[events]` | `durable_spool`, `retry_enabled`, `max_extraction_attempts` | at-least-once spool + dedup |
| `[security]` | `mcp_allowed_agents`, `admin_token_env` | agent ACL + admin token |
| `[workers]` | `interval_seconds`, `empty_backoff_seconds` | background indexing loop cadence |

Environment overrides: `AGENT_MEMORY_WORKERS_INTERVAL_SECONDS`,
`AGENT_MEMORY_WORKERS_EMPTY_BACKOFF_SECONDS`, and `SQLITE_VEC_PATH`
(see `.env.example`).

## Enabling Hybrid Vector Search (sqlite-vec)

Hybrid search combines FTS5 lexical ranking with dense-vector similarity.
The vector component requires the [sqlite-vec](https://github.com/ashtum/sqlite-vec)
loadable C extension. Without it the system degrades gracefully to
lexical-only retrieval; no code changes are required to fall back.

1. Download a prebuilt binary matching your platform from the
   [sqlite-vec releases page](https://github.com/ashtum/sqlite-vec/releases).
2. Place the shared object (`vec0.so` / `vec0.dylib`) in a directory,
   e.g. `/usr/local/lib/sqlite-vec/`.
3. Set the environment variable:
   ```bash
   export SQLITE_VEC_PATH=/usr/local/lib/sqlite-vec/vec0.so
   ```
   Alternatively, point it at a directory; the loader will try the common
   base names (`vec0`, `sqlite_vec`, `vec`) with platform suffixes.
4. Restart the service.
5. Verify: `GET /v1/admin/index/status` should report
   `"vector_available": true` (requires the admin token).

## Module Layout

```
src/agent_memory/
├── config.py        # TOML + env config loading (incl. WorkersConfig)
├── schemas.py       # Pydantic contract models (Phase 0)
├── mcp_schemas.py   # MCP tool input/output models
├── main.py          # FastAPI + FastMCP entrypoint (wires bg indexing loop)
├── api/             # HTTP event & admin endpoints
├── mcp/             # FastMCP server and tool implementations
├── core/            # Business logic (projects, tasks, handoffs, knowledge)
├── storage/         # SQLite database, migrations, repositories
├── retrieval/       # FTS5, sqlite-vec, hybrid search
└── workers/         # BackgroundIndexingLoop (outbox drain)
```

## Connecting Your Agents

The memory server runs locally; agents talk to it over HTTP. Each adapter
reads its settings from environment variables — no TOML file on the agent
side.

### 1. Start the Server

```bash
# Terminal A — start the memory service
python -m agent_memory.main
# → FastAPI on 127.0.0.1:8765 + FastMCP (MCP endpoint)
```

### 2. Set Shared Env Vars (all three agents)

```bash
export AGENT_MEMORY_SERVER_URL=http://127.0.0.1:8765
export AGENT_MEMORY_PROJECT_ID=my-project        # which project's memory
export AGENT_MEMORY_WORKSPACE_ID=main            # worktree / branch id
export AGENT_MEMORY_TASK_ID=feat-x               # optional logical task
# Spool location (optional, defaults to ~/.local/state/agent-memory/<agent>)
export AGENT_MEMORY_SPOOL_ROOT=~/.local/state/agent-memory
```

These come from `adapters/shared/event_client.py` — every adapter
(Pi / Codex / OpenCode) reads the same four vars, so a single shell profile
or `.env` file works for all of them.

### 3. Pi

Pi supports extensions; wire the lifecycle hooks to
`adapters/pi/pi_extension.py`:

```python
# Inside your Pi extension entry point
import sys
sys.path.insert(0, "<repo>/adapters/pi")
from pi_extension import (
    on_session_start, on_run_started, on_turn_end,
    on_session_before_compact, on_run_settled,
    submit_extraction_result, on_run_interrupted, on_session_shutdown,
    get_capabilities,
)
```

Call each hook at the corresponding Pi lifecycle point. `on_run_settled`
returns `{"extract": true}` when it thinks extraction is warranted; then
the model produces the structured result and you call
`submit_extraction_result` to persist it.

### 4. Codex

Codex is hooks-based and observe-only (no extraction). Inside each Codex
hook script:

```python
import sys, os
sys.path.insert(0, "<repo>/adapters/codex")
from codex_adapter import CodexAdapter, CodexAdapterConfig

adapter = CodexAdapter(CodexAdapterConfig(
    project_id=os.environ.get("AGENT_MEMORY_PROJECT_ID"),
    workspace_id=os.environ.get("AGENT_MEMORY_WORKSPACE_ID"),
    task_id=os.environ.get("AGENT_MEMORY_TASK_ID"),
))

# SessionStart hook:
adapter.on_session_start(session_id, native_session_id, head_sha)
# PreCompact hook:
adapter.on_pre_compact(session_id, summary)
# Stop hook:
adapter.on_stop(session_id, outcome="completed", head_sha_end=head_sha)
# SessionEnd hook:
adapter.on_session_end(session_id)   # flushes spool
```

### 5. OpenCode

OpenCode supports project-level plugins; also observe-only. In your plugin:

```python
import sys, os
sys.path.insert(0, "<repo>/adapters/opencode")
from opencode_adapter import OpenCodeAdapter, OpenCodeAdapterConfig

adapter = OpenCodeAdapter(OpenCodeAdapterConfig(
    project_id=os.environ.get("AGENT_MEMORY_PROJECT_ID"),
    workspace_id=os.environ.get("AGENT_MEMORY_WORKSPACE_ID"),
    task_id=os.environ.get("AGENT_MEMORY_TASK_ID"),
))

# onSessionStart:
adapter.on_session_start(session_id, native_session_id, head_sha)
# onTurnStart / onTurnEnd:
adapter.on_turn_start(run_id, session_id)
adapter.on_turn_end(run_id, session_id)
# onSessionEnd:
adapter.on_session_end(session_id, outcome="completed", head_sha_end=head_sha)
```

### 6. Verify

```bash
# Watch events arriving while an agent runs
python -m memoryctl index status --json
# Should show pending_index_jobs increasing, then draining as the
# background loop processes them.

# Search what was captured
python -m memoryctl memory search --project-id my-project "query"

# Inspect a specific memory
python -m memoryctl memory inspect <memory_id>
```

## CLI (`memoryctl`)

```
memoryctl doctor                        # DB + schema + BGE-M3 health
memoryctl status                        # record counts across all tables
memoryctl projects register|list        # project identity
memoryctl tasks list                    # task inspection
memoryctl handoffs latest               # show latest handoff
memoryctl memory search|inspect         # knowledge search
memoryctl pending list|approve          # candidate review
memoryctl index status [--json]        # FTS/vector/job queue snapshot (--json for scripting)
memoryctl index drain [--batch-size N] # one-shot outbox drain
memoryctl index rebuild [--project-id] # requeue all (or one project's) knowledge rows
memoryctl jobs retry [job-id|--all]     # reset failed index jobs to pending
memoryctl backup create|verify          # SQLite backup + integrity check
memoryctl knowledge supersede|archive|reject|governance
```

## HTTP Job Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/jobs/{job_id}` | Return status/attempts/error/created/updated for a single index job. 404 if unknown. |
| `POST` | `/v1/admin/jobs/{job_id}/retry` | Reset a failed index job back to `pending` so the background loop picks it up. 404 if unknown, 409 if not in `failed` state. |
| `POST` | `/v1/admin/index/drain` | Manually drain pending index jobs (requires admin token). |
| `GET` | `/v1/admin/index/status` | Pending count + sqlite-vec availability (requires admin token). |

## Development

See `docs/` for detailed contracts and design notes.
