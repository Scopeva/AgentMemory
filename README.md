# Local Agent Memory & Handoff Service

A local, desktop-free service that gives multiple coding agents (Pi, Codex,
OpenCode) shared long-term memory and clean task handoffs.

## Architecture

- **Core service**: FastMCP (agent-facing tools) + FastAPI (hook/event HTTP API)
- **Primary store**: SQLite in WAL mode
- **Retrieval**: FTS5 lexical search + sqlite-vec dense vectors (BGE-M3)
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

## Module Layout

```
src/agent_memory/
├── config.py        # TOML + env config loading
├── schemas.py       # Pydantic contract models (Phase 0)
├── mcp_schemas.py   # MCP tool input/output models
├── main.py          # FastAPI + FastMCP entrypoint
├── api/             # HTTP event & admin endpoints
├── mcp/             # FastMCP server and tool implementations
├── core/            # Business logic (projects, tasks, handoffs, knowledge)
├── storage/         # SQLite database, migrations, repositories
├── retrieval/       # FTS5, sqlite-vec, hybrid search
└── workers/         # Background indexing and recovery
```

## Development

See `docs/` for detailed contracts and design notes.
