# Source-Independent Plugin Runtime

Status: draft for user review. The user selected the packaged-runtime approach
on 2026-11-20; implementation starts only after review of this design.

## Intent and acceptance

The published Agent Memory distribution must install and run the Codex,
OpenCode, and Pi integrations after the source checkout has been removed.
`AGENT_MEMORY_REPO_ROOT` must not be required by any newly installed plugin.

Acceptance evidence:

1. A wheel installed into an isolated virtual environment contains every
   Python module used by the Codex hook runtime and the assets used by the Pi
   and OpenCode installers.
2. The three package-provided installers work from outside the repository and
   do not write `AGENT_MEMORY_REPO_ROOT` into host configuration.
3. With the checkout made unavailable, a Codex hook can import its runtime and
   record an event; Pi and OpenCode can load their installed TypeScript assets
   and make the same HTTP/spool delivery path available.
4. Existing non-Agent-Memory host hooks and MCP registrations remain intact.

Non-goals: changing the service API, changing `config.toml`, replacing the
per-session adapter variables (`AGENT_MEMORY_SERVER_URL`, project/workspace/
task IDs, and spool root), or adding transcript-derived memory extraction.

## Current facts

`pyproject.toml` packages only `src/agent_memory`. Codex copies Python hook
files to `~/.codex/agent-memory`, then writes an absolute checkout path as
`AGENT_MEMORY_REPO_ROOT` in `hooks.json`; the hook imports `adapters.*` from
that checkout. It cannot survive checkout removal.

Pi and OpenCode currently install self-contained TypeScript extensions that
do not read `AGENT_MEMORY_REPO_ROOT` at runtime. Their shell installers still
copy assets from the checkout, so they too cannot be installed from a wheel.
The older Python bridge files are not the active installer path.

## Selected architecture

`agent_memory` is the sole packaged runtime owner.

- Move the shared Python adapter tree beneath `src/agent_memory/adapters` and
  update internal imports to `agent_memory.adapters.*`.
- Add package-owned Codex hook dispatch, invoked by a console/module entry
  point using the Python interpreter that owns the installed wheel. The
  registry command names that installed entry point; it has no checkout path
  and no `AGENT_MEMORY_REPO_ROOT` assignment.
- Ship the Pi and OpenCode TypeScript extensions as package data. Package
  installers obtain them through `importlib.resources` and copy them to each
  host's active extension directory; they do not depend on repository-relative
  paths.
- Offer package-owned install commands for `codex`, `opencode`, and `pi`.
  Each command updates only Agent-Memory's own host registration and preserves
  unrelated hooks, extensions, and MCP servers.
- Keep server URL and per-session project metadata as launcher environment
  inputs. They vary by agent invocation and are not service configuration.

The intended delivery flow is:

```text
wheel / pipx install
        |
package installer ----> Codex registry / Pi extension / OpenCode extension
        |                         |
installed package runtime <-------+---- lifecycle event -> Agent Memory HTTP API
```

## Compatibility and retirement

Anti-Entropy Declaration:

- Deletion class: code-retirement.
- Old authority: the checkout-root bootstrap and the copied Python hook files
  as the primary runtime owner.
- New canonical owner: the installed `agent_memory` package and its packaged
  plugin assets.
- Preserved behavior: lifecycle event delivery, durable spooling, MCP
  registration, and preservation of unrelated host configuration.
- Retired behavior: new installations injecting or requiring
  `AGENT_MEMORY_REPO_ROOT`.
- External boundary: yes. Existing Codex host registries may invoke copied
  legacy hook files.
- Source-of-truth data risk: none.

Retirement Decision: compat-exception. The new installer migrates its own
recognizable legacy registrations in place but does not delete arbitrary
existing files or third-party hooks. Legacy source-tree scripts are retained
only as a migration carrier for one release and documented as deprecated; a
subsequent removal requires an explicit compatibility review and release-note
notice.

## Verification plan

- Main path: build a wheel, install it in a disposable virtual environment,
  run each package installer from a non-repository directory, and inspect the
  generated host registrations.
- Negative check: remove/unset `AGENT_MEMORY_REPO_ROOT`, hide the checkout,
  then invoke the Codex hook entry point; it must import and spool/deliver an
  event.
- Asset check: assert the installed Pi and OpenCode TypeScript assets are
  discoverable through package resources and copied byte-for-byte by their
  installers.
- Boundary check: tests prove only Agent-Memory registrations change; existing
  Codex hooks, MCP entries, and host configuration survive installation.
- Lingering-reference check: no active installer, generated registration, or
  active TypeScript extension refers to `AGENT_MEMORY_REPO_ROOT`.

## Boundary and complexity decision

This is an architecture correction, not a server-config change. The current
implementation drifts from the newly approved packaged-install requirement by
making a checkout a runtime dependency. A single package-owned runtime avoids
three separately versioned plugin copies. The one-release compatibility carrier
is bounded to existing external Codex registrations and must not become a
second primary path.

ADR signal: yes. The implementation plan must record the package-runtime
ownership decision and the compatibility removal trigger before deleting the
legacy carrier.
