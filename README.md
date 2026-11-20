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
| `[security]` | `admin_token_env` | token for privileged HTTP routes |
| `[workers]` | `interval_seconds`, `empty_backoff_seconds` | background indexing loop cadence |

Environment overrides: `AGENT_MEMORY_WORKERS_INTERVAL_SECONDS`,
`AGENT_MEMORY_WORKERS_EMPTY_BACKOFF_SECONDS`, and `SQLITE_VEC_PATH`
(see `.env.example`).

### Database Migrations

The schema is managed via SQL migration files in
`src/agent_memory/storage/migrations/`, applied in lexicographic order
on startup (tracked in `schema_migrations`).

| File | Description |
|---|---|
| `001_initial.sql` | Core tables: projects, runs, tasks, events, knowledge, handoffs, checkpoints, index_jobs |
| `002_retrieval.sql` | FTS5 `chunks_fts`, `memory_vectors` (vec0 virtual table), `chunk_index` |
| `003_project_id.sql` | Adds `project_id TEXT` column to `events` and `runs` tables + partial indexes; enables true per-project event isolation |

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
├── core/            # Business logic
│   ├── agent_capabilities.py   # adapter capability matrix (pi/codex/opencode)
│   ├── memory_policy.py        # candidate/promotion/governance rules
│   ├── knowledge_governance.py # supersession, archive, reject flows
│   └── projects/identity.py   # project_id detection + alias resolution
├── storage/
│   ├── database.py            # connection + WAL setup
│   ├── migrations/           # 001_initial, 002_retrieval, 003_project_id
│   └── repositories/         # projects, sessions, tasks, events, knowledge, handoffs, checkpoints
├── retrieval/
│   ├── chunker.py            # document → chunk splitter
│   ├── lexical.py            # FTS5 BM25 search
│   ├── vector.py             # sqlite-vec dense similarity
│   ├── sqlvec.py             # sqlite-vec loadable-extension loader (graceful degradation)
│   ├── embedding.py          # BGE-M3 HTTP client
│   ├── hybrid.py             # RRF fusion of lexical + vector
│   ├── dispatcher.py         # routing entry point
│   ├── search.py             # high-level search API
│   └── indexing.py           # index job worker
└── workers/
    └── indexing_loop.py      # BackgroundIndexingLoop (outbox drain)
```

## Connecting Your Agents

The memory server runs locally; agents talk to it over HTTP. Each adapter
reads its settings from environment variables — no TOML file on the agent
side.

### 1. Start the Server

Run one of these (whichever matches your deployment):

**Option A — bare process (dev / quick test)**
```bash
python -m agent_memory.main
# → FastAPI on 127.0.0.1:8765
```

**Option B — Docker (recommended for host agent use)**
```bash
docker compose up -d
# → maps host 127.0.0.1:8765 to the container's service port
```
See `docker-compose.yml` in the repo. The compose file wires:
- loopback-only port mapping `127.0.0.1:8765:8765` (host → container)
- a persistent volume `memory-data:/data` (SQLite survives restarts)
- `extra_hosts: host.docker.internal:host-gateway` (Linux only, so the
  container can reach a host-side BGE-M3 service)
- an optional commented line for mounting `SQLITE_VEC_PATH`

> **How the host agent reaches the container:** Docker's port mapping
> publishes the container's port on the host's loopback. No special URL is
> needed on the agent side — it just points at `127.0.0.1:8765` on the host.
> (This is the *container → host* direction for BGE-M3; *host → container*
> for agents goes through the published port, and the agent lives on the host.)

### 2. Set Shared Env Vars (all three agents)

```bash
export AGENT_MEMORY_SERVER_URL=http://127.0.0.1:8765
export AGENT_MEMORY_PROJECT_ID=my-project        # optional — auto-detected if unset
export AGENT_MEMORY_WORKSPACE_ID=main            # worktree / branch id
export AGENT_MEMORY_TASK_ID=feat-x               # optional logical task
export AGENT_MEMORY_REPO_ROOT=/path/to/AgentMemory  # where the repo lives
# Spool location (optional, defaults to ~/.local/state/agent-memory/<agent>)
export AGENT_MEMORY_SPOOL_ROOT=~/.local/state/agent-memory
```

These come from `adapters/shared/event_client.py` — every adapter
(Pi / Codex / OpenCode) reads the same vars, so a single shell profile
or `.env` file works for all of them.

The installers also register the agent-facing MCP endpoint at
`http://127.0.0.1:8765/mcp/`. It exposes `submit_memory_candidate` and the
memory/query tools to all three clients; the lifecycle plugins alone only
record events.

#### Project-ID Auto-Detection

`AGENT_MEMORY_PROJECT_ID` is **optional**. When unset (or empty), the
service auto-detects it in this priority order:

1. `aliases.toml` (see below) — longest-match, glob `*` supported
2. **git repo name** — runs `git rev-parse --show-toplevel` from the
   current working directory; the basename of the repo root wins
3. **cwd basename** — fallback when not inside a git repo

You can also pin it explicitly via `AGENT_MEMORY_PROJECT_ID` (highest
priority). The detected value is stored in `events.project_id` and
`runs.project_id` (migration 003), enabling true per-project event
isolation.

#### Alias Table

Create `~/.config/agent-memory/aliases.toml` (path overridable via
`AGENT_MEMORY_ALIASES_PATH`):

```toml
[aliases]
"*"        = "default"
"/home/u/work"  = "workspace"
"/home/u/work/api-*"  = "api"
"~/notes"  = "notes"
```

Exact / longest-match wins; glob patterns use `fnmatch` semantics;
`~` expands to home. Malformed TOML is logged and ignored (service
continues with no aliases).

**Docker note:** `AGENT_MEMORY_SERVER_URL` is read by the *host* agent,
not the container. It must always be a host-reachable address — for the
default compose setup that's `http://127.0.0.1:8765`. If you remap the
host port in compose, update this env var to match (the container-side
BGE-M3 URL is a separate setting, `AGENT_MEMORY_EMBEDDING_ENDPOINT`, that
uses `host.docker.internal:8001`).

### 3. Pi

Install the TypeScript extension into Pi's active global extension directory:

```bash
bash plugins/pi/install_pi.sh
```

It records session/run/turn lifecycle events and flushes a session-start event
immediately, which creates the project on the server. A structured extraction
result still needs to be submitted through MCP or as a
`memory.extraction_completed` event; lifecycle telemetry never sends chat text
to another model automatically.

### 4. Codex

Codex is hooks-based and observe-only (no extraction). Four lifecycle
hooks are declared in `~/.codex/hooks.json`; each is a thin shell wrapper
that calls into the shared bootstrap:

```
~/.codex/
├── hooks.json             # global registry; installer preserves other hooks
├── agent-memory/
│   ├── _bootstrap.py      # shared: sys.path setup, env, project_id detection
│   ├── am_session_start.py # SessionStart → CodexAdapter.on_session_start()
│   ├── am_pre_compact.py   # PreCompact → CodexAdapter.on_pre_compact()
│   ├── am_stop.py          # Stop → CodexAdapter.on_stop()
│   └── am_session_end.py   # SessionEnd → CodexAdapter.on_session_end()
└── …
```

All four `am_*.py` scripts call `_bootstrap()` from `_bootstrap.py`
(deduped — no more 50-line copy-paste per hook). The bootstrap reads the
same env vars and auto-detects `project_id` via the alias table when
`AGENT_MEMORY_PROJECT_ID` is unset.

**Install:** `bash plugins/codex/install_codex.sh` copies the hooks to
`~/.codex/agent-memory/` and merges entries into `~/.codex/hooks.json` (run
`/hooks` in Codex CLI once to trust them).

### 5. OpenCode

OpenCode 2.x supports TypeScript plugins; this one subscribes to the server's
native async event stream and delivers lifecycle events directly over HTTP:

```
plugins/opencode/
└── agent-memory.ts            # OpenCode 2.x plugin entry point (TypeScript)
```

The plugin flushes on session creation and each terminal execution event, and
spools delivery locally while the server is unreachable.

**Install:** `bash plugins/opencode/install_opencode.sh` copies the
plugin to `~/.config/opencode/plugins/agent-memory.ts`.

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
