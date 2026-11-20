# Configuration Single Source

## Goal

Make `config.toml` the sole owner of Agent Memory's non-sensitive service
settings. Environment variables may supply only the admin-token value named by
`[security].admin_token_env`.

## Scope and boundary

The service loader, sqlite-vec path, Docker Compose, container image, examples,
documentation, and configuration-dependent tests change together. Agent
session metadata (`AGENT_MEMORY_PROJECT_ID`, task identity, and similar
per-session adapter inputs) is outside this service-configuration migration.

## Anti-entropy declaration

- Deletion class: internal code/config retirement.
- Old authority: environment overrides and `.env.example` values for runtime
  service settings; `config.example.toml` as the competing template.
- New canonical owner: repository `config.toml`.
- Preserved behavior: TOML-defined database, embedding, retrieval, workers,
  CORS, and security-token *name* still configure the running service.
- Retired behavior: non-token runtime settings no longer change from process
  environment or Compose environment entries.
- External boundary: Docker Compose mounts the canonical file and keeps the
  token injected from its environment.
- Retirement decision: delete-first for internal override code and old
  template; no live database or user record is changed.

## TDD route

Mode: `off`; focused post-change regression tests cover canonical TOML loading,
ignored legacy non-token environment values, and configured sqlite-vec paths.

## Tasks

1. Replace the application configuration source with `config.toml`; remove
   service-setting environment overrides while retaining the token lookup.
2. Move sqlite-vec path selection into `[retrieval]` and pass it through the
   existing retrieval/index owners.
3. Make Docker and both Compose descriptors mount the same canonical file and
   inject only `AGENT_MEMORY_ADMIN_TOKEN`.
4. Retire the non-token `.env` example and update setup/docs/tests to configure
   values in TOML.
5. Verify TOML wins over legacy environment values, the container starts with
   the mounted file, and no retired override references remain.

## Verification

Run focused config/sqlite-vec tests, the full suite, `git diff --check`, and a
rebuilt local container health check. Confirm `.env.example` and Compose retain
only the admin-token value and that source/docs no longer describe non-token
service overrides.
