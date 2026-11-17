#!/usr/bin/env bash
# install_opencode.sh — install the agent-memory plugin into OpenCode.
#
# Usage (from the repo):
#   ./plugins/opencode/install_opencode.sh
#
# OpenCode loads TypeScript plugins from two places:
#   - Global:  ~/.config/opencode/plugin/
#   - Project: <project>/.opencode/plugin/
#
# This script copies agent-memory.ts into the global dir so it applies to
# every OpenCode session. The batch bridge (opencode_bridge_batch.py)
# stays in the repo; the TS plugin spawns it and pipes events over stdin.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PLUGIN_DIR="${OPENCODE_PLUGIN_DIR:-$HOME/.config/opencode/plugin}"
mkdir -p "$PLUGIN_DIR"

echo "==> Copying plugin to $PLUGIN_DIR/agent-memory.ts"
cp "${SCRIPT_DIR}/agent-memory.ts" "$PLUGIN_DIR/agent-memory.ts"

echo
echo "============================================================"
echo " Installed. Next steps:"
echo "============================================================"
echo " 1. Set these env vars before launching OpenCode:"
echo "    export AGENT_MEMORY_REPO_ROOT=${REPO_ROOT}"
echo "    export AGENT_MEMORY_SERVER_URL=http://127.0.0.1:8765"
echo "    export AGENT_MEMORY_PROJECT_ID=<your-project>"
echo "    # optional: export AGENT_MEMORY_WORKSPACE_ID / AGENT_MEMORY_TASK_ID"
echo
echo " 2. Restart OpenCode. The plugin loads automatically from"
echo "    $PLUGIN_DIR."
echo " 3. Verify events are landing:"
echo "    python3 -m memoryctl index status --json"
echo
