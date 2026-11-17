#!/usr/bin/env bash
# gen_aliases.sh — generate a starter aliases.toml for agent-memory project-id
# normalization.
#
# Usage:
#   ./scripts/gen_aliases.sh                 # write to ~/.config/agent-memory/aliases.toml
#   ./scripts/gen_aliases.sh /custom/path    # write to a specific file
#
# The generated file maps several common directory names to stable
# project identifiers. Edit it to match your actual checkouts.

set -euo pipefail

OUT="${1:-$HOME/.config/agent-memory/aliases.toml}"
mkdir -p "$(dirname "$OUT")"

if [ -f "$OUT" ] && [ ! -w "$OUT" ]; then
    echo "error: $OUT is not writable" >&2
    exit 1
fi

if [ -f "$OUT" ]; then
    echo "note: $OUT already exists; backing up to $OUT.bak.$(date +%s)"
    cp "$OUT" "$OUT.bak.$(date +%s)"
fi

cat > "$OUT" <<'EOF'
# agent-memory: project-id alias table
#
# Maps local directory names / paths to stable project identifiers.
# The adapters consult this file when AGENT_MEMORY_PROJECT_ID is not set,
# so that multiple checkouts of the same logical project map to one ID.
#
# Key forms:
#   - bare name:              "~/code/proj-a" -> matches any dir named proj-a
#   - absolute / glob path:   "~/work/*/proj-a" -> fnmatch glob
#   - relative path prefix:   "src/backend" -> matches CWD or sub-path
#
# Resolution: longest, most specific key wins.

[aliases]
# --- example entries; replace with your real checkouts --------------------
# "~/code/agent-memory"       = "agent-memory"
# "~/work/agent-memory"       = "agent-memory"
# "~/projects/*/agent-memory" = "agent-memory"
# "agent-memory"              = "agent-memory"
EOF

echo "wrote $OUT"
echo "edit it to add your directory -> project_id mappings."
