# Source-Independent Plugin Runtime — Checkpoint

Branch/HEAD at start: `master` / `aa54321ebcc5aa7794700eb794bab57f043c70dd`.

Pre-existing worktree state preserved: modified `.gitignore`; deleted
`projects/agent-memory-dashboard-9ab415`; deleted `tmp/ssh_git_proxy.py`.

Todo:

1. completed — moved adapters into `src/agent_memory/adapters`; production,
   bridge, test, and go-live imports now use `agent_memory.adapters`.
2. completed — added the packaged Codex dispatcher and atomic registry merge.
3. completed — moved Pi/OpenCode TypeScript assets into package data and added
   installer targets that copy those assets from package resources.
4. completed — migrated active docs and source-tree installers to package
   commands; active code no longer reads `AGENT_MEMORY_REPO_ROOT`.
5. completed — staged-diff review finished; task-owned paths are ready for a
   scoped local commit and manual handoff.

TDD/verification: automated tests and builds are intentionally skipped by the
user's instruction. Allowed evidence is source inspection, package metadata
inspection, `git diff --check`, and the documented manual procedure.

Drift check: continue. The approved scope allows the package boundary and
one-release compatibility wrappers; it does not authorize destructive host or
persistent-state changes.

Evidence: source inspection confirms the adapter tree and TypeScript assets are
inside the `src` package boundary; package metadata exposes the two commands;
and active code has no repository-root environment dependency. Automated
tests/builds remain intentionally skipped.

Drift check: continue. The move matches the canonical package owner and did
not add host configuration mutation.

Next step: create the scoped local commit, then hand off the manual no-source
acceptance procedure.
