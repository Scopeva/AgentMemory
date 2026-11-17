# Agent Plugins

Installable plugin packages for the three supported coding agents. Each
plugin is a thin shell over the shared `adapters/` code in this repo:
it reads the same `AGENT_MEMORY_*` env vars and persists events through
the durable spool.

```
plugins/
├── codex/
│   ├── hooks/
│   │   ├── _bootstrap.py        # shared sys.path + env config helper
│   │   ├── am_session_start.py
│   │   ├── am_pre_compact.py
│   │   ├── am_stop.py
│   │   ├── am_session_end.py
│   │   └── hooks.json           # Codex hooks config template
│   └── install_codex.sh
├── opencode/
│   ├── agent-memory.ts          # OpenCode TypeScript plugin (batch mode)
│   ├── opencode_bridge.py       # single-event bridge (legacy, kept for reference)
│   ├── opencode_bridge_batch.py # long-lived batch bridge (one process, many events)
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
# 可选：不设 AGENT_MEMORY_PROJECT_ID 时，会自动取当前目录 / git 仓库名
export AGENT_MEMORY_PROJECT_ID=my-project              # 可选，覆盖自动探测
export AGENT_MEMORY_WORKSPACE_ID=main                    # optional
export AGENT_MEMORY_TASK_ID=feat-x                       # optional
```

`AGENT_MEMORY_REPO_ROOT` is what lets the hook scripts / TS plugin import
the `adapters` package at runtime. Without it, each plugin falls back to
auto-detecting the repo by walking up from its own location.

`AGENT_MEMORY_PROJECT_ID` is **optional**: when unset, the adapter
auto-detects it from your working directory (git repo basename, or CWD
name). This means different checkouts of different repos map to
different memory namespaces automatically — no per-project env juggling.
Set the variable explicitly to override (e.g. to use a stable name
across several local directories of the same logical project).

### Project-id alias table

If you have several local checkouts of the same logical project (say
`~/code/proj-a` and `~/work/proj-a`) you want them to map to one stable
`project_id`, create `~/.config/agent-memory/aliases.toml`:

```bash
./scripts/gen_aliases.sh          # writes a starter file
$EDITOR ~/.config/agent-memory/aliases.toml
```

```toml
[aliases]
"~/code/proj-a"      = "proj-a"     # absolute path
"~/work/*/proj-a"    = "proj-a"     # glob (fnmatch)
"proj-a"             = "proj-a"     # bare-name fallback
```

Resolution order (most specific wins):
1. explicit `project_id` argument
2. `AGENT_MEMORY_PROJECT_ID` env var
3. alias table (longest-match, wildcards allowed)
4. git repo basename
5. CWD basename

Set `AGENT_MEMORY_ALIASES_PATH` to point at a different file (useful in
tests or team-shared configs checked into the repo).

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
2. The TS plugin spawns **one** long-lived Python bridge
   (`opencode_bridge_batch.py`) and pipes every event to its stdin as
   a JSON line — no per-message process fork. The bridge persists +
   flushes internally, closing on session end.
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
