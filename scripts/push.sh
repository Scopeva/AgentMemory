#!/usr/bin/env bash
# push.sh — push sandbox commits to GitHub using the user's SSH key.
#
# Usage:
#   ./push.sh                     # uses key at default path below
#   KEY_FILE=~/.ssh/id_ed25519_sandbox ./push.sh
#
# The private key is expected at $KEY_FILE (default: ~/.ssh/id_ed25519_sandbox).
# The corresponding PUBLIC key must be registered on GitHub (repo deploy key
# or account-level SSH key) before pushing.

set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

KEY_FILE="${KEY_FILE:-$HOME/.ssh/id_ed25519_sandbox}"
REMOTE="${REMOTE:-origin}"

if [[ ! -f "$KEY_FILE" ]]; then
  echo "error: private key not found at $KEY_FILE" >&2
  echo "generate one locally: ssh-keygen -t ed25519 -C agent-memory-sandbox -f $KEY_FILE -N \"\"" >&2
  echo "then add its .pub to GitHub: https://github.com/Scopeva/AgentMemory/keys" >&2
  exit 1
fi

chmod 600 "$KEY_FILE"

export GIT_SSH_COMMAND="python3 tmp/ssh_git_proxy.py ssh"
export SSH_PROXY_KEY="$KEY_FILE"

git push "$REMOTE" HEAD
