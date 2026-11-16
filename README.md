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

Environment overrides: `AGENT_MEMORY_WORKERS_INTERVAL_SECONDS` and
`AGENT_MEMORY_WORKERS_EMPTY_BACKOFF_SECONDS` (see `.env.example`).

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
