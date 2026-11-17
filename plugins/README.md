# Agent Plugins

Installable plugin packages for the three supported coding agents. Each
plugin is a thin shell over the shared `adapters/` code in this repo:
it reads the same `AGENT_MEMORY_*` env vars and persists events through
the durable spool.

```
plugins/
├── codex/
│   ├── hooks/
│   │   ├── am_session_start.py
│   │   ├── am_pre_compact.py
│   │   ├── am_stop.py
│   │   ├── am_session_end.py
│   │   └── hooks.json           # Codex hooks config template
│   └── install_codex.sh
├── opencode/
│   ├── agent-memory.ts          # OpenCode TypeScript plugin
│   ├── opencode_bridge.py       # bridge shell-out target
│   └── install_opencode.sh
└── pi/
    ├── pi_extension.py          # installable Pi extension entry
    └── install_pi.sh
```

## Common env (all three agents)

Set these in your shell profile (or a project `.env`) before launching
the agent:

```bash
export AGENT_MEMORY_REPO_ROOT=/path/to/AgentMemory
export AGENT_MEMORY_SERVER_URL=http://127.0.0.1:8765   # host-side Docker: same
export AGENT_MEMORY_PROJECT_ID=my-project
export AGENT_MEMORY_WORKSPACE_ID=main                    # optional
export AGENT_MEMORY_TASK_ID=feat-x                       # optional
```

`AGENT_MEMORY_REPO_ROOT` is what lets the hook scripts / TS plugin import
the `adapters` package at runtime. Without it, each plugin falls back to
auto-detecting the repo by walking up from its own location.

## Codex

```bash
./plugins/codex/install_codex.sh
```

What happens:
1. The four Python hook scripts + a generated `hooks.json` are copied
   into `~/.codex/hooks/` (or `$CODEX_HOME/hooks` if set).
2. `hooks.json` is rewritten so `${PLUGIN_ROOT}` resolves to the install
   directory.
3. Codex auto-discovers `hooks.json` in its config layer; no manifest
   needed.

Then in the Codex CLI:
- Run `/hooks` to **review and trust** the four new hooks (Codex will
  skip untrusted hooks otherwise).
- Trust is recorded per hook-definition hash; if you edit the scripts,
  re-trust them.

## OpenCode

```bash
./plugins/opencode/install_opencode.sh
```

What happens:
1. `agent-memory.ts` is copied to `~/.config/opencode/plugin/` (or
   `$OPENCODE_PLUGIN_DIR` if set).
2. The TS plugin shells out to `plugins/opencode/opencode_bridge.py`
   via `execFileSync` — the bridge reads the same env vars and imports
   the adapter.
3. OpenCode loads the plugin automatically on startup. No further
   install step.

## Pi

```bash
./plugins/pi/install_pi.sh
```

What happens:
1. `plugins/pi/pi_extension.py` is symlinked into
   `~/.config/pi/extensions/agent-memory-pi.py` (or
   `$PI_EXTENSIONS_DIR` if set).
2. Pi's extension mechanism loads it and calls the `on_*` functions at
   the matching lifecycle points.

## Verify (all agents)

```bash
# Watch events arriving while an agent session runs
python -m memoryctl index status --json

# Search captured memories
python -m memoryctl memory search --project-id my-project "关键词"
```

## Notes

- **Host agents → Docker container**: the container publishes
  `127.0.0.1:8765` on the host (see `docker-compose.yml`). Agents point
  at that; no container-specific URL needed.
- **sqlite-vec**: optional. Without it the service runs in lexical-only
  mode; with it (via `SQLITE_VEC_PATH`), hybrid vector search is on.
- **At-least-once delivery**: each adapter writes to a durable spool
  before hitting the network. If the server is down, events are
  replayed on the next session start.
