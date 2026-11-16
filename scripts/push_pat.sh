#!/usr/bin/env bash
# push_pat.sh — push to GitHub over HTTPS using a fine-grained PAT.
#
# Usage:
#   GITHUB_PAT=gh_xxx... ./scripts/push_pat.sh
#
# The PAT must be a fine-grained token with:
#   - Repository: Scopeva/AgentMemory only
#   - Permissions: Contents = Read and write
#   - Expiry: 1 day recommended
#
# The token is NOT stored; it is passed via the GITHUB_PAT env var and
# used inline in the push URL. When the token expires, simply generate a
# new one — no cleanup needed.

set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

: "${GITHUB_PAT:?error: set GITHUB_PAT to a fine-grained GitHub PAT with Contents: Read and write on Scopeva/AgentMemory}"

# Build a URL with embedded token auth (token is not echoed to stdout by git)
REMOTE_URL="https://x-access-token:${GITHUB_PAT}@github.com/Scopeva/AgentMemory.git"

# Use the token URL for this push only; do not rewrite the stored remote.
git push "${REMOTE_URL#https://}" master

echo "pushed master to Scopeva/AgentMemory"
