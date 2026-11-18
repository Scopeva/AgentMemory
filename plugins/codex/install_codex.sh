#!/usr/bin/env bash
# install_codex.sh — install the agent-memory plugin into Codex.
#
# Usage (from the repo):
#   ./plugins/codex/install_codex.sh
#
# What it does:
#   1. Copies the four hook scripts + hooks.json into ~/.codex/hooks/
#      (or the path given by $CODEX_HOME, which Codex honors if set).
#   2. Points AGENT_MEMORY_REPO_ROOT at this repo so the hooks can import
#      the adapters package at runtime.
#   3. Prints the env vars you must export before launching Codex.
#
# Codex has no "plugin marketplace"; hooks are installed by dropping files
# into its config layer. After install, open the Codex CLI and run /hooks
# to review + trust the new hooks (otherwise they are skipped).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

CODEX_HOOK_DIR="${CODEX_HOME:-$HOME/.codex}/hooks"
mkdir -p "$CODEX_HOOK_DIR"

echo "==> Copying hook scripts to $CODEX_HOOK_DIR"
cp "${SCRIPT_DIR}/hooks/_bootstrap.py"      "$CODEX_HOOK_DIR/"
cp "${SCRIPT_DIR}/hooks/am_session_start.py" "$CODEX_HOOK_DIR/"
cp "${SCRIPT_DIR}/hooks/am_pre_compact.py"  "$CODEX_HOOK_DIR/"
cp "${SCRIPT_DIR}/hooks/am_stop.py"         "$CODEX_HOOK_DIR/"
cp "${SCRIPT_DIR}/hooks/am_session_end.py"  "$CODEX_HOOK_DIR/"
chmod +x "$CODEX_HOOK_DIR"/am_*.py

# --- Write hooks.json, rewriting ${PLUGIN_ROOT} to the installed dir -------
HOOKS_OUT="${CODEX_HOOK_DIR}/agent-memory-hooks.json"
sed "s|\${PLUGIN_ROOT}|${CODEX_HOOK_DIR}|g" \
    "${SCRIPT_DIR}/hooks/hooks.json" > "$HOOKS_OUT"
echo "==> Wrote $HOOKS_OUT"

# Codex auto-discovers hooks.json files in the config layer. If the user
# already has a hooks.json, we write a separate file so we don't clobber it.
echo
echo "============================================================"
echo " Installed. Next steps:"
echo "============================================================"
echo " 1. Set these env vars before launching Codex:"
echo "    export AGENT_MEMORY_REPO_ROOT=${REPO_ROOT}"
echo "    export AGENT_MEMORY_SERVER_URL=http://127.0.0.1:8765"
echo "    export AGENT_MEMORY_PROJECT_ID=<your-project>"
echo "    # optional: export AGENT_MEMORY_WORKSPACE_ID / AGENT_MEMORY_TASK_ID"
echo
echo " 2. In the Codex CLI, run /hooks and trust the four new hooks."
echo " 3. Verify events are landing (hooks still use Python; for a"
echo "    no-Python check use the browser dashboard or curl):"
echo "    - Browser dashboard: open the agent-memory web UI and check"
echo "      the Events / Index Status panels."
echo "    - Or with curl:"
echo "      curl http://127.0.0.1:8765/v1/projects/<your-project>/events"
echo
