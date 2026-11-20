# Source-Independent Plugin Runtime — Evidence

Outcome: `needs-manual-verification`.

Static evidence:

- `git diff --check` passed for the task diff and staged task diff.
- Repository-wide literal inspection found no active
  `AGENT_MEMORY_REPO_ROOT`, `from adapters`, or `import adapters` reference.
  The sole remaining text is the manual negative assertion in
  `plugins/README.md`.
- Staged rename detection confirms the Python adapters and both TypeScript
  assets moved beneath `src/agent_memory/`; `pyproject.toml` exposes the
  package-owned hook and installer commands.

Skipped by explicit user instruction: automated tests, wheel build, isolated
installation, host CLI registration, Agent startup, event delivery, MCP
candidate submission, and offline spool replay.

Residual risk: package-data inclusion and host-agent command compatibility are
not established by source inspection. The manual no-source procedure in
`plugins/README.md` is the next required verification.
