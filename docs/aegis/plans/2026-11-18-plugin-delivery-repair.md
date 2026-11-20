# Plugin Delivery Repair

## Goal

Make the installed Codex, OpenCode, and Pi integrations deliver lifecycle
events to Agent Memory so projects are created on first use. Persist explicit
`memory.extraction_completed` payloads as reviewable memory candidates.

## Root-cause contract

This is an independent-compound integration failure, not one shared runtime
defect: Codex was installed outside its active hook registry, OpenCode used a
pre-v2 subscription contract, and Pi was copied to an inactive directory and
read a session ID absent from its event payload. Separately, the service
persisted extraction-completed events but never consumed their memory payload.

The service continues to be the canonical project creator: inserting an event
with a project ID registers that project. Plugin installers and adapters only
deliver events; they do not create a second project owner.

## Scope and compatibility

Update the three plugin integrations/installers, the event-ingestion owner,
focused tests, and user-facing plugin documentation. Preserve existing hook
entries when installing Codex. The Codex client retains its own hook-trust
approval; this repair does not bypass it.

The plugins do not infer memories from transcript text or call an LLM. A
producer may submit a structured `memory.extraction_completed.memories` list,
which becomes reviewable candidates. Automatic semantic extraction requires a
separate model, privacy, and approval policy.

## Anti-entropy declaration

- Deletion class: code-retirement considered only.
- Old paths: the unused OpenCode Python bridge files and standalone Codex hook
  template.
- Invalid authority: neither may define the active installer path; the active
  registries/installers are the canonical owners.
- Legitimate remaining capability: existing distributed/manual installations
  may still invoke those files.
- Retirement decision: compat-exception. Do not delete or rewrite those
  external-compatibility carriers without a scoped user confirmation.
- Source-of-truth data risk: none.

## TDD Route

Mode: `off`; add focused regression checks after the smallest repair.

## Tasks

1. Update Pi for its active extension directory and context-owned session ID;
   flush first and terminal lifecycle events.
2. Replace the obsolete OpenCode callback subscription with the installed v2
   plugin/event contract.
3. Install Codex hooks into its active global registry without overwriting
   unrelated hooks, while leaving trust approval to Codex.
4. Mount the existing MCP server at the loopback-bound service endpoint and
   register that endpoint for all three clients so agents can submit memory
   candidates rather than only lifecycle events.
5. Turn extraction-completed event payloads into idempotent memory candidates;
   enqueue indexing only after an accepted knowledge record exists.
6. Add targeted lifecycle/persistence tests, validate plugin loading and
   installers in disposable locations, then install the repaired integrations.

## Verification

Prove event delivery produces a project, a completed extraction produces one
candidate only under retries, accepted knowledge gets an index job, and the
three installed plugin entry points parse/load. Run the relevant test suite
and inspect the final diff.
