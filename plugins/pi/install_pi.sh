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
# (POST /v1/events/batch). No Python subprocess is spawned.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PI_EXT_DIR="${PI_EXTENSIONS_DIR:-$HOME/.config/pi/extensions}"
mkdir -p "$PI_EXT_DIR"

TARGET="$PI_EXT_DIR/agent-memory-pi.ts"

if [ -L "$TARGET" ]; then
  echo "==> Removing old Python symlink: $TARGET"
  rm -f "$TARGET"
fi

echo "==> Copying agent-memory.ts to $TARGET"
cp "${SCRIPT_DIR}/agent-memory.ts" "$TARGET"

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
echo " 2. In your Pi extension code, import the functions:"
echo
echo "    import {"
echo "      onSessionStart, onRunStarted, onTurnEnd,"
echo "      onSessionBeforeCompact, onRunSettled,"
echo "      submitExtractionResult, onRunInterrupted,"
echo "      onSessionShutdown, flush,"
echo "    } from \"\$PI_EXT_DIR/agent-memory-pi\";"
echo
echo " 3. Call them at the matching Pi lifecycle points. onRunSettled"
echo "    returns { extract: true } when extraction is warranted; then"
echo "    ask the model for a structured result and call"
echo "    submitExtractionResult. Call onSessionShutdown to flush."
echo
echo " 4. Verify events are landing:"
echo "    python3 -m memoryctl index status --json   # on the service side"
echo
