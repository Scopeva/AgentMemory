#!/usr/bin/env bash
# install_codex.sh — install Agent Memory lifecycle hooks for Codex.
#
# The current Codex CLI reads one global hooks registry at
# $CODEX_HOME/hooks.json. Keep user hooks intact and add only our four entries.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${AGENT_MEMORY_PYTHON:-${REPO_ROOT}/.venv/bin/python}"
CODEX_ROOT="${CODEX_HOME:-$HOME/.codex}"
INSTALL_DIR="${CODEX_ROOT}/agent-memory"
HOOKS_FILE="${CODEX_ROOT}/hooks.json"
MCP_URL="${AGENT_MEMORY_MCP_URL:-http://127.0.0.1:8765/mcp/}"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi
if ! "$PYTHON_BIN" -c 'import httpx' >/dev/null 2>&1; then
  echo "Agent Memory dependencies are unavailable in $PYTHON_BIN; set AGENT_MEMORY_PYTHON." >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR"
echo "==> Copying hook scripts to $INSTALL_DIR"
cp "${SCRIPT_DIR}/hooks/_bootstrap.py" "$INSTALL_DIR/"
cp "${SCRIPT_DIR}/hooks/am_session_start.py" "$INSTALL_DIR/"
cp "${SCRIPT_DIR}/hooks/am_pre_compact.py" "$INSTALL_DIR/"
cp "${SCRIPT_DIR}/hooks/am_stop.py" "$INSTALL_DIR/"
cp "${SCRIPT_DIR}/hooks/am_session_end.py" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR"/am_*.py

if [ -f "$HOOKS_FILE" ] && [ ! -e "${HOOKS_FILE}.agent-memory.bak" ]; then
  cp "$HOOKS_FILE" "${HOOKS_FILE}.agent-memory.bak"
fi

"$PYTHON_BIN" - "$HOOKS_FILE" "$INSTALL_DIR" "$REPO_ROOT" "$PYTHON_BIN" <<'PY'
import json
import os
import shlex
import sys
import tempfile
from pathlib import Path

hooks_file = Path(sys.argv[1])
install_dir = Path(sys.argv[2])
repo_root = sys.argv[3]
python_bin = sys.argv[4]
spec = {
    "SessionStart": ("am_session_start.py", 5, None),
    "PreCompact": ("am_pre_compact.py", 5, "Capturing pre-compact context"),
    "Stop": ("am_stop.py", 30, "Recording run result"),
    "SessionEnd": ("am_session_end.py", 3, None),
}

try:
    config = json.loads(hooks_file.read_text()) if hooks_file.exists() else {}
except json.JSONDecodeError as error:
    raise SystemExit(f"Cannot merge invalid JSON in {hooks_file}: {error}")

hooks = config.setdefault("hooks", {})
if not isinstance(hooks, dict):
    raise SystemExit(f"Cannot merge {hooks_file}: 'hooks' must be an object")

script_names = set(name for name, _, _ in spec.values())

def is_agent_memory_group(group: object) -> bool:
    if not isinstance(group, dict):
        return False
    for hook in group.get("hooks", []):
        command = str(hook.get("command", "")) if isinstance(hook, dict) else ""
        if "agent-memory" in command or any(name in command for name in script_names):
            return True
    return False

for event, (script, timeout, status_message) in spec.items():
    existing = hooks.get(event, [])
    if not isinstance(existing, list):
        raise SystemExit(f"Cannot merge {hooks_file}: hooks.{event} must be a list")
    command = (
        f"AGENT_MEMORY_REPO_ROOT={shlex.quote(repo_root)} "
        f"{shlex.quote(python_bin)} {shlex.quote(str(install_dir / script))}"
    )
    hook = {"type": "command", "command": command, "timeout": timeout}
    if status_message:
        hook["statusMessage"] = status_message
    hooks[event] = [group for group in existing if not is_agent_memory_group(group)] + [{"hooks": [hook]}]

fd, temp_name = tempfile.mkstemp(prefix="hooks.", suffix=".json", dir=hooks_file.parent)
try:
    with os.fdopen(fd, "w") as temp:
        json.dump(config, temp, indent=2)
        temp.write("\n")
    os.replace(temp_name, hooks_file)
finally:
    if os.path.exists(temp_name):
        os.unlink(temp_name)
PY

echo "==> Merged Agent Memory entries into $HOOKS_FILE"
if [ "${AGENT_MEMORY_SKIP_MCP_REGISTRATION:-}" != "1" ]; then
  CODEX_BIN="${CODEX_BIN:-codex}"
  if ! command -v "$CODEX_BIN" >/dev/null 2>&1; then
    echo "Codex executable not found; set CODEX_BIN or register $MCP_URL manually." >&2
    exit 1
  fi
  "$CODEX_BIN" mcp add agent-memory --url "$MCP_URL"
  echo "==> Registered Agent Memory MCP server at $MCP_URL"
fi
echo
echo "Installed. Restart Codex, then run /hooks and explicitly trust the four"
echo "Agent Memory hooks. Codex owns that approval; this installer does not bypass it."
echo "The first pre-install registry is retained at ${HOOKS_FILE}.agent-memory.bak."
