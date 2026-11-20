# Source-Independent Plugin Runtime Implementation

## Goal and plan basis

Implement the approved design in
`docs/aegis/specs/2026-11-20-source-independent-plugin-runtime-design.md`:
the three plugin installers and their active runtimes must work from an
installed wheel after the source checkout is absent. New installations must not
require or generate `AGENT_MEMORY_REPO_ROOT`.

The user's explicit test posture is manual follow-up testing. Do not run or add
automated tests/builds for this slice. Keep the manual acceptance procedure in
the updated documentation.

## Baseline and architecture

Current package ownership excludes the root-level `adapters/` tree and all
plugin assets. Codex hooks compensate by importing through a checkout path;
Pi/OpenCode runtime assets are self-contained after copy, but their installers
still require a checkout.

The canonical owner becomes the installed `agent_memory` package:

- `src/agent_memory/adapters/` owns the Python delivery/runtime code.
- one package-owned Codex hook dispatcher owns all four lifecycle hook
  invocations;
- one package-owned plugin installer owns host registration and resource-copy
  behavior for Codex, OpenCode, and Pi;
- package data owns the two TypeScript extension assets.

The HTTP event contract, durable spool semantics, MCP endpoint, service
configuration, and per-session launcher variables remain unchanged.

## Compatibility and retirement boundary

The checkout-root bootstrap and copied Codex hook scripts are an external host
compatibility boundary. Do not delete arbitrary existing host files or
third-party hooks. New installations replace only recognizable Agent-Memory
registrations with package entry points. Keep source-tree installer/script
paths as deprecation wrappers for one release; do not let them remain a second
primary implementation. A later removal needs an explicit compatibility
review and release-note notice.

## Change necessity and plan pressure

Documentation or configuration cannot make a wheel contain its missing
Python modules and TypeScript assets. The smallest complete code change is to
move existing runtime logic into the existing distribution namespace and add a
single installer/dispatcher boundary, rather than vendoring another runtime
under each host directory.

Existence check:

- New surface: package installer and Codex dispatcher.
- Reuse candidate: current shell installers and four copied hook scripts.
- Why insufficient: they derive paths from a checkout and duplicate host
  integration logic.
- Creation proof: one packaged owner is required to resolve resources and
  record the installed interpreter in Codex's registry.
- Entropy result: add-with-proof; the duplicated installer and hook ownership
  become thin deprecation wrappers.

Plan pressure test: proceed. The approved spec fixes the canonical owner,
external compatibility is bounded, and each task has a measurable manual
result.

Complexity budget:

- Artifact class: source, package metadata, installer assets, documentation.
- Current pressure: adapter code is split outside the distribution; Codex has
  five copied Python scripts and installer logic is duplicated across hosts.
- Projected pressure: one dispatcher and one installer add focused owners but
  eliminate checkout bootstrap from the active path.
- Budget result: within-budget if event behavior is moved unchanged and host
  mutations stay in one installer module.
- Governance: do not add host-specific delivery logic to adapters; update
  documentation and legacy wrappers only after package ownership works.

## TDD route

Mode: off. Decision: skipped. Authority: the user explicitly requested manual
testing instead of follow-up automated testing. Post-change evidence is source
inspection, package metadata inspection, and the documented manual acceptance
procedure; it does not claim runtime delivery success.

## Tasks

1. **Package the runtime modules.**
   - Move `adapters/` into `src/agent_memory/adapters/`, add missing package
     markers, and change all production, legacy bridge, test, and documentation
     imports to `agent_memory.adapters.*`.
   - Preserve adapter classes, event payloads, project-id resolution, durable
     spool paths, and error handling exactly. Remove source-root `sys.path`
     mutation from active package code.
   - Update `pyproject.toml` only as needed to expose the package runtime and
     later console commands.

2. **Create the package-owned Codex integration.**
   - Add a single dispatcher in `src/agent_memory/` that reads Codex hook JSON
     from stdin, maps the four lifecycle events to the existing `CodexAdapter`,
     and preserves non-blocking failures and spool flushing.
   - Add a Codex installer in the same package boundary. It atomically merges
     only recognizable Agent-Memory hook groups, writes an absolute installed
     Python/entry-point command, preserves unrelated hook groups, and performs
     the existing optional MCP registration.
   - Replace the source shell installer and hook templates with deprecation
     wrappers/documentation that delegate to the installed package. No newly
     generated command may contain `AGENT_MEMORY_REPO_ROOT`.

3. **Package Pi/OpenCode assets and installation.**
   - Move `plugins/pi/agent-memory.ts` and `plugins/opencode/agent-memory.ts`
     into a package-data directory beneath `src/agent_memory/`; configure wheel
     inclusion explicitly.
   - Extend the package installer with Pi and OpenCode targets. Resolve asset
     bytes using `importlib.resources`, copy to each host's current extension
     path, preserve optional environment overrides for the target directory,
     and retain optional MCP registration.
   - Convert the source shell installers into deprecation wrappers so all
     active installation behavior has one package owner. The active TypeScript
     assets continue using only server/project/session/spool environment data.

4. **Migrate documentation and removal references.**
   - Update `README.md`, `plugins/README.md`, and `docs/go-live.md` to use the
     package installer commands and remove the `AGENT_MEMORY_REPO_ROOT`
     prerequisite.
   - Add a manual no-source acceptance sequence: build/install wheel in an
     isolated environment, run each installer outside the checkout, remove or
     hide the checkout, restart each agent, and verify project creation plus
     event/candidate delivery.
   - Search active source, installer templates, and generated command tests for
     `AGENT_MEMORY_REPO_ROOT`; only explicitly labelled one-release legacy
     migration text may remain.

5. **Review and handoff.**
   - Inspect the final diff and run `git diff --check`; do not run automated
     tests or builds per user instruction.
   - Record that the runtime outcome remains `needs-manual-verification` until
     the user performs the documented isolated-wheel checks.
   - Commit only task-owned files, leaving the existing `.gitignore`, submodule
     deletion, and temporary-script deletion untouched.

## Manual acceptance

1. Build and install the wheel into an isolated environment, then change into
   a directory that is not the source checkout.
2. Run the packaged installer for `codex`, `opencode`, and `pi`; inspect the
   generated Codex hook commands and installed TS assets. None may contain
   `AGENT_MEMORY_REPO_ROOT` or a checkout path.
3. Make the original checkout unavailable and restart each host agent.
4. In each agent, open a project and trigger one lifecycle event. Confirm the
   project and event appear in the service; submit a memory candidate through
   MCP and confirm it is saved.
5. Stop the service briefly, trigger an event, restart it, then confirm the
   agent-specific spool replays the event.

## Risks and stop conditions

- Host CLI registration syntax or extension discovery can change independently
  of the Python package; manual validation must use the installed host versions.
- Existing copied Codex scripts remain a bounded migration carrier, not proof
  that new source-free installation works.
- Do not delete existing host configuration, MCP servers, spool files, or user
  data. Stop for direction if the host installer cannot identify an
  Agent-Memory-owned registration safely.
