#!/usr/bin/env bash
# install_pi.sh — install the agent-memory extension into Pi (TypeScript).
#
# Usage (from the repo):
#   ./plugins/pi/install_pi.sh
#
# Pi's extension mechanism is JS/TS-based. This script:
#   1. Copies plugins/pi/agent-memory.ts into Pi's extensions dir.
#   2. Prints the env vars you must set before launching Pi.
#
# The TS extension talks directly to the agent-memory server's HTTP API
# (POST /v1/events/batch). No Python or node subprocess is required —
# the extension is a self-contained TypeScript module that only calls
# the server's HTTP API.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MCP_URL="${AGENT_MEMORY_MCP_URL:-http://127.0.0.1:8765/mcp/}"

# Pi 1.x loads global extensions from its agent installation, not XDG config.
PI_EXT_DIR="${PI_EXTENSIONS_DIR:-$HOME/.pi/agent/extensions}"
mkdir -p "$PI_EXT_DIR"

TARGET="$PI_EXT_DIR/agent-memory-pi.ts"

if [ -L "$TARGET" ]; then
  echo "==> Removing old Python symlink: $TARGET"
  rm -f "$TARGET"
fi

echo "==> Copying agent-memory.ts to $TARGET"
cp "${SCRIPT_DIR}/agent-memory.ts" "$TARGET"

if [ "${AGENT_MEMORY_SKIP_MCP_REGISTRATION:-}" != "1" ]; then
  PI_BIN="${PI_BIN:-pi}"
  if ! command -v "$PI_BIN" >/dev/null 2>&1; then
    echo "Pi executable not found; set PI_BIN or register $MCP_URL manually." >&2
    exit 1
  fi
  "$PI_BIN" mcp add agent-memory --url "$MCP_URL"
  echo "==> Registered Agent Memory MCP server at $MCP_URL"
fi

echo
echo "============================================================"
echo " Installed. Next steps:"
echo "============================================================"
echo " 1. Set these env vars before launching Pi:"
echo "    export AGENT_MEMORY_SERVER_URL=http://127.0.0.1:8765"
echo "    export AGENT_MEMORY_PROJECT_ID=<your-project>   # optional, auto-detected if unset"
echo "    # optional: export AGENT_MEMORY_WORKSPACE_ID / AGENT_MEMORY_TASK_ID"
echo "    # optional: export AGENT_MEMORY_SPOOL_ROOT=~/.local/state/agent-memory"
echo
echo " 2. The extension auto-registers these Pi events:"
echo "    session_start    → session.start"
echo "    agent_start      → run.started"
echo "    turn_end         → turn.end"
echo "    agent_settled    → run.settled"
echo "    session_shutdown → session.end + flush to server"
echo
echo " 3. Session-start and settled events flush immediately; remaining"
echo "    events flush at shutdown. If the server"
echo "    is unreachable, events are spooled to"
echo "    ~/.local/state/agent-memory/pi/spool.jsonl and retried"
echo "    on the next session."
echo
echo " 4. Verify events are landing (no Python needed):"
echo "    - Browser dashboard: open the agent-memory web UI and check"
echo "      the Events / Index Status panels."
echo "    - Or with curl:"
echo "      curl http://127.0.0.1:8765/v1/projects/<your-project>/events"
echo
