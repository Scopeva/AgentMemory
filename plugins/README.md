# Agent Plugins

Installable integrations for the three supported coding agents. They are
shipped inside the `agent-memory` wheel, so installation does not require a
source checkout. They share the `AGENT_MEMORY_*` session metadata and persist
lifecycle events through a durable local spool.

```
agent_memory/
├── adapters/                    # Python lifecycle runtime
└── integrations/
    ├── codex.py                 # four Codex hook dispatches
    ├── installer.py             # agent-memory-install <agent>
    └── assets/                  # Pi/OpenCode TypeScript extensions
```

## Common env (all three agents)

Set these in your shell profile (or a project `.env`) before launching
the agent:

```bash
export AGENT_MEMORY_SERVER_URL=http://127.0.0.1:8765   # host-side Docker: same
# 可选：不设 AGENT_MEMORY_PROJECT_ID 时，会自动取当前目录 / git 仓库名
export AGENT_MEMORY_PROJECT_ID=my-project              # 可选，覆盖自动探测
export AGENT_MEMORY_WORKSPACE_ID=main                    # optional
export AGENT_MEMORY_TASK_ID=feat-x                       # optional
```

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
agent-memory-install codex
```

What happens:
1. The installer merges only Agent Memory entries into `$CODEX_HOME/hooks.json`.
2. Each registered command uses the Python environment that owns the installed
   wheel and imports `agent_memory.integrations.codex`; no repository path is
   recorded.

Then in the Codex CLI:
- Run `/hooks` to **review and trust** the four new hooks (Codex will
  skip untrusted hooks otherwise).
- Trust is recorded per hook-definition hash; if you edit the scripts,
  re-trust them.

## OpenCode

```bash
agent-memory-install opencode
```

What happens:
1. The packaged `agent-memory.ts` is copied to `~/.config/opencode/plugins/` (or
   `$OPENCODE_PLUGIN_DIR` if set).
2. The OpenCode 2.x plugin consumes its async lifecycle event stream,
   posts first-session and terminal-run batches directly, and spools on
   delivery failure.
3. OpenCode loads the plugin automatically on startup. No further
   install step.

## Pi

```bash
agent-memory-install pi
```

What happens:
1. The packaged `agent-memory.ts` is copied to
   `~/.pi/agent/extensions/agent-memory-pi.ts` (or `$PI_EXTENSIONS_DIR`
   if set).
2. Pi loads it and the extension reads the current session ID from the
   extension context rather than from lifecycle payloads.

## Verify (all agents)

```bash
# Watch events arriving while an agent session runs
python -m memoryctl index status --json

# Search captured memories
python -m memoryctl memory search --project-id my-project "关键词"
```

## Manual no-source verification

1. Build and install the wheel into an isolated Python environment, then leave
   the source checkout.
2. Run `agent-memory-install codex`, `agent-memory-install opencode`, and
   `agent-memory-install pi` from another directory. The Codex command in
   `hooks.json` must not contain `AGENT_MEMORY_REPO_ROOT` or a checkout path.
3. Make the checkout unavailable, restart each host agent, and create a
   project/session. Confirm lifecycle events create the project and that MCP
   candidate submission still saves a candidate.
4. With the service stopped, create an event, restart it, and confirm the
   agent-specific spool replays it.

## Notes

- **Host agents → Docker container**: the container publishes
  `127.0.0.1:8765` on the host (see `docker-compose.yml`). Agents point
  at that; no container-specific URL needed.
- **sqlite-vec**: optional. Without it the service runs in lexical-only
  mode; set `retrieval.sqlite_vec_path` in `config.toml` to enable hybrid
  vector search.
- **At-least-once delivery**: each adapter writes to a durable spool
  before hitting the network. If the server is down, events are
  replayed on the next session start.
- **Memory content**: lifecycle hooks create projects and record events. To
  create reviewable memory candidates, an agent must call the MCP
  `submit_memory_candidate` tool or post a structured
  `memory.extraction_completed.memories` payload. The plugins never send
  transcript text to an external model automatically.
