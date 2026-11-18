# Reliability and Security Repair

## Goal

Repair every confirmed finding from the 2026-11-18 repository audit: protect
administrative actions, make indexed knowledge retrievable and removable,
recover interrupted work, make project deletion referentially safe, fix the
Docker entry path, and reject malformed search input.

## Architecture and scope

The existing owners remain canonical: HTTP routers own request validation and
admin admission, `IndexingWorker` owns the derived chunk index, `JobDispatcher`
owns job state, and the project deletion route owns its transaction. No schema
or live database data is deleted; existing tables are used as designed.

Files in scope: API routers, retrieval worker/dispatcher/search helpers,
application startup, Docker/Compose/config/docs, and focused integration/unit
tests. Adapters, MCP transport implementation, and public data payload shapes
are not redesigned.

## Baseline and compatibility

Baseline: audit findings in the active conversation and `HEAD`
`808af2b58ee8574daed68d91954b72d64822a632`.

HTTP admin routes will now require a configured token. This intentionally
changes the insecure default from open access to a `503` configuration error;
wrong or missing tokens return `403`. Existing valid-token callers retain the
same endpoints and payloads. Search keeps its response shape; blank queries
become client validation errors instead of FTS failures.

## TDD Route

Mode: `off`; decision: `skipped`; authority: local Aegis configuration.
Test posture: add focused regression tests before completion and run the
smallest relevant suites. Strict RED/GREEN steps are not authorized.

## Change necessity

Configuration or documentation alone cannot make the derived index consistent,
secure privileged routes, or recover jobs. The minimum code boundary is the
existing HTTP/router, indexing, dispatcher, and startup owners; no new service
layer is needed.

## Tasks

1. Add one shared HTTP admin guard; apply it to all `/v1/admin` routes and the
   project deletion route. Bind Compose ports to loopback, require an injected
   token, remove the unsupported MCP ACL claim, and keep the Docker config
   file present.
2. Make `IndexingWorker` rebuild the complete derived state for one memory:
   clear prior chunks/FTS/vector entries, insert `chunks` and FTS entries, and
   remove all derived entries on delete. Make blank search safe and escape
   quoted FTS tokens.
3. Reclaim jobs left `running` by an interrupted process during startup and
   the CLI drain path. Retain the single-process assumption as an explicit
   upgrade boundary.
4. Correct project deletion ordering for every direct and transitive FK child
   without touching live data outside a requested DELETE call.
5. Add focused tests for authorization, project deletion with all dependent
   rows, index/search lifecycle, cleanup/reindex, interrupted-job recovery,
   query validation, and Compose parsing. Run formatting, targeted tests, full
   tests when dependencies permit, and Docker Compose config validation.

## Anti-entropy declaration

Deletion class: internal code/config retirement. The invalid owner is the
unenforced `mcp_allowed_agents` setting and duplicated local admin checks;
the shared HTTP guard becomes the canonical owner. No source-of-truth data is
being deleted and no externally distributed dependency is evidenced. Decision:
delete-first for the stale claim/config, with legacy TOML input treated as a
compatibility concern only if source inspection finds a consumer.

## Verification

Prove each audited failure at its seam: request authorization, end-to-end
index/search, FK-rich project deletion, restart recovery, stale-index cleanup,
and FTS edge input. Confirm both Compose files parse and inspect the final
diff for unintended data or API changes.
