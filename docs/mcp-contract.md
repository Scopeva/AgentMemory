# MCP Tool Contract

## Tools Exposed to Agents

1. `resolve_project` – Identify project/workspace identity from a path or explicit ID.
2. `get_project_context` – Return compact project background within a token budget.
3. `search_memory` – Hybrid FTS5 + vector search for relevant knowledge.
4. `get_memory` – Fetch a specific knowledge item and its revision history.
5. `get_task_state` – Get task status, latest handoff, and recent events.
6. `get_latest_handoff` – Get the most recent valid handoff for a task or workspace.
7. `create_handoff` – Submit a new handoff record for a task.
8. `submit_memory_candidate` – Submit structured memory candidates for review.
9. `update_task_state` – Update task status with optimistic locking.

## Authorization

- Each agent must be registered in `security.mcp_allowed_agents`.
- Tools returning knowledge are scoped to the resolved project.
- `submit_memory_candidate` only creates candidates; it cannot accept or reject.
- `update_task_state` requires the caller to hold the task lease or be the owner.

## Unified Error Contract

All tool errors return a structured JSON with:

```json
{
  "error": {
    "code": "VERSION_CONFLICT",
    "message": "Task revision is stale; re-read and retry."
  }
}
```

Allowed codes: `PROJECT_UNRESOLVED`, `PROJECT_ACCESS_DENIED`, `SESSION_NOT_FOUND`,
`TASK_CONFLICT`, `VERSION_CONFLICT`, `INVALID_EVIDENCE`, `APPROVAL_REQUIRED`,
`MEMORY_DUPLICATE`, `EMBEDDING_UNAVAILABLE`, `INVALID_SCHEMA_VERSION`.

## Token Budgeting

- `get_project_context` accepts `max_output_tokens` and truncates deterministically.
- When truncation occurs, `truncated=true` and a list of `references` is returned
  so the agent can fetch more via `get_memory` or `search_memory`.

## Idempotency

- `submit_memory_candidate` requires `idempotency_key`; repeated submissions with the
  same key return the same result.
- `create_handoff` increments `revision`; callers should read latest first.


## Phase 4 Search Upgrade

`search_memory` now uses the chunk index (FTS5 + optional sqlite-vec)
when the SearchService is wired in. Falls back to LIKE over knowledge
rows when no index has been built yet. The `retrieval_mode` field in
the response indicates which path was taken:

| retrieval_mode  | Meaning |
|-----------------|---------|
| `hybrid`        | FTS5 + vector RRF fusion |
| `lexical_only`  | FTS5 only (vector unavailable) |
| `lexical_basic` | Phase 2 LIKE fallback |
| `none`          | No matches in index |
