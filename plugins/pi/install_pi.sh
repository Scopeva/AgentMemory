#!/usr/bin/env bash
# Deprecated source-tree wrapper. Install from the wheel when possible.
set -euo pipefail

PYTHON_BIN="${AGENT_MEMORY_PYTHON:-python3}"
exec "$PYTHON_BIN" -m agent_memory.integrations.installer pi "$@"
