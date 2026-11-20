# Source-Independent Plugin Runtime — Intent

Requested outcome: package and install the three Agent Memory integrations
without a source checkout or `AGENT_MEMORY_REPO_ROOT`.

Parent plan: `docs/aegis/plans/2026-11-20-source-independent-plugin-runtime.md`.
Approved design: `docs/aegis/specs/2026-11-20-source-independent-plugin-runtime-design.md`.

Scope: package the adapter runtime and TS assets, replace active installers and
Codex hook dispatch with package-owned entry points, migrate docs, and retain a
one-release legacy source-script migration carrier.

Non-goals: service API/config changes, persistent-data changes, transcript
extraction behavior, automatic test/build execution, and deletion of arbitrary
host Agent configuration.

Baseline usage: the approved spec and implementation plan are the requirement
and runtime-boundary sources. `docs/aegis/BASELINE-GOVERNANCE.md` applies;
current implementation is architecture drift against the newly approved
source-independent packaging requirement.

Compatibility: preserve unrelated host hooks/MCP entries. New installs stop
generating checkout-root paths; legacy copied Codex hooks are not deleted.

Success evidence: package-owned paths contain no active repository-root
bootstrap and the user can complete the documented isolated-wheel manual
acceptance sequence.

Stop condition: implementation and scoped commit delivered as
`needs-manual-verification`; no runtime success claim without the user's
manual host-agent checks.
