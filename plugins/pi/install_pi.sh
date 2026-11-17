#!/usr/bin/env bash
# install_pi.sh — install the agent-memory extension into Pi.
#
# Usage (from the repo):
#   ./plugins/pi/install_pi.sh
#
# Pi's extension mechanism is JS/TS-based and loads a plugin that shells
# out to Python. This script:
#   1. Symlinks plugins/pi/pi_extension.py into Pi's extensions dir so Pi
#      can import it.
#   2. Prints the env vars you must set before launching Pi.
#
# If Pi ships its own extension loader config, point it at pi_extension.py
# and call the on_* functions at the matching lifecycle points.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PI_EXT_DIR="${PI_EXTENSIONS_DIR:-$HOME/.config/pi/extensions}"
mkdir -p "$PI_EXT_DIR"

echo "==> Symlinking pi_extension.py into $PI_EXT_DIR"
ln -sf "${SCRIPT_DIR}/pi_extension.py" "$PI_EXT_DIR/agent-memory-pi.py"

echo
echo "============================================================"
echo " Installed. Next steps:"
echo "============================================================"
echo " 1. Set these env vars before launching Pi:"
echo "    export AGENT_MEMORY_REPO_ROOT=${REPO_ROOT}"
echo "    export AGENT_MEMORY_SERVER_URL=http://127.0.0.1:8765"
echo "    export AGENT_MEMORY_PROJECT_ID=<your-project>"
echo "    # optional: export AGENT_MEMORY_WORKSPACE_ID / AGENT_MEMORY_TASK_ID"
echo
echo " 2. Register the extension in Pi (point its lifecycle hooks at"
echo "    \$PI_EXT_DIR/agent-memory-pi.py and call on_session_start etc)."
echo " 3. Verify events are landing:"
echo "    python3 -m memoryctl index status --json"
echo
