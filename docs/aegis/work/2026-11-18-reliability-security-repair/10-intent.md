# Reliability and Security Repair - Intent

## TaskIntentDraft

- Requested outcome: Repair all seven confirmed audit findings without mutating existing live data.
- Goal: Repair all seven confirmed audit findings without mutating existing live data.
- Success evidence:
- Focused regression tests, Compose validation, and the available full test suite pass.
- Stop condition: Done when all planned repairs are implemented and verified; needs-verification if the local environment blocks required tests.
- Non-goals:
- No live database deletion, schema redesign, or MCP transport redesign.
- Scope: HTTP admin admission, retrieval derived index lifecycle, job recovery, project deletion order, Docker configuration, documentation, and focused tests.
- Change kinds:
- repair
- Risk hints:
- Security, data deletion, persistence, and public HTTP behavior

## BaselineReadSetHint

- docs/aegis/plans/2026-11-18-reliability-security-repair.md

## BaselineUsageDraft

- Required baseline refs:
- docs/aegis/plans/2026-11-18-reliability-security-repair.md
- Acknowledged before plan:
- none
- Cited in plan:
- none
- Missing refs:
- docs/aegis/plans/2026-11-18-reliability-security-repair.md
- Advisory decision: needs-baseline-readback

## ImpactStatementDraft

- Compatibility boundary: Admin endpoints require a configured token; valid-token route payloads remain stable.
- Affected layers:
- api,retrieval,storage,distribution
- Owners:
- existing routers, IndexingWorker, JobDispatcher, project deletion transaction
- Invariants:
- No unauthenticated admin mutation; derived chunks stay synchronized; project deletion respects every FK.
- Non-goals:
- No live database deletion, schema redesign, or MCP transport redesign.

These records are Method Pack drafts / hints, not authoritative runtime decisions.
