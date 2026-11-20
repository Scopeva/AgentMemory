#!/usr/bin/env bash
# install_opencode.sh — install the agent-memory plugin into OpenCode 2.x.
#
# Usage (from the repo):
#   ./plugins/opencode/install_opencode.sh
#
# OpenCode 2.x auto-discovers plugins from two places:
#   - Global:  ~/.config/opencode/plugins/
#   - Project: <project>/.opencode/plugins/
# (the 1.x `plugin/` dir is still read, but 2.x recommends `plugins/`)
#
# This script copies agent-memory.ts into the global dir so it applies to
# every OpenCode session. The plugin talks directly to the server's HTTP
# API (POST /v1/events/batch) — no Python or subprocess is involved.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_URL="${AGENT_MEMORY_MCP_URL:-http://127.0.0.1:8765/mcp/}"

PLUGIN_DIR="${OPENCODE_PLUGIN_DIR:-$HOME/.config/opencode/plugins}"
mkdir -p "$PLUGIN_DIR"

echo "==> Copying plugin to $PLUGIN_DIR/agent-memory.ts"
cp "${SCRIPT_DIR}/agent-memory.ts" "$PLUGIN_DIR/agent-memory.ts"

if [ "${AGENT_MEMORY_SKIP_MCP_REGISTRATION:-}" != "1" ]; then
  OPENCODE_BIN="${OPENCODE_BIN:-opencode}"
  if ! command -v "$OPENCODE_BIN" >/dev/null 2>&1; then
    echo "OpenCode executable not found; set OPENCODE_BIN or register $MCP_URL manually." >&2
    exit 1
  fi
  "$OPENCODE_BIN" mcp add --global agent-memory --url "$MCP_URL"
  echo "==> Registered Agent Memory MCP server at $MCP_URL"
fi

echo
echo "============================================================"
echo " Installed. Next steps:"
echo "============================================================"
echo " 1. Set these env vars before launching OpenCode:"
echo "    export AGENT_MEMORY_SERVER_URL=http://127.0.0.1:8765"
echo "    export AGENT_MEMORY_PROJECT_ID=<your-project>   # optional, auto-detected if unset"
echo "    # optional: export AGENT_MEMORY_WORKSPACE_ID / AGENT_MEMORY_TASK_ID"
echo "    # optional: export AGENT_MEMORY_SPOOL_ROOT=~/.local/state/agent-memory"
echo
echo " 2. Restart OpenCode. The plugin loads automatically from"
echo "    $PLUGIN_DIR."
echo " 3. Verify events are landing (no Python needed):"
echo "    - Browser dashboard: open the agent-memory web UI and check"
echo "      the Events / Index Status panels."
echo "    - Or with curl:"
echo "      curl http://127.0.0.1:8765/v1/projects/<your-project>/events"
echo
