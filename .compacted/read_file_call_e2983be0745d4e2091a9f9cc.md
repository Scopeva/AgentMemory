     1	# MCP Tool Contract
     2	
     3	## Tools Exposed to Agents
     4	
     5	1. `resolve_project` – Identify project/workspace identity from a path or explicit ID.
     6	2. `get_project_context` – Return compact project background within a token budget.
     7	3. `search_memory` – Hybrid FTS5 + vector search for relevant knowledge.
     8	4. `get_memory` – Fetch a specific knowledge item and its revision history.
     9	5. `get_task_state` – Get task status, latest handoff, and recent events.
    10	6. `get_latest_handoff` – Get the most recent valid handoff for a task or workspace.
    11	7. `create_handoff` – Submit a new handoff record for a task.
    12	8. `submit_memory_candidate` – Submit structured memory candidates for review.
    13	9. `update_task_state` – Update task status with optimistic locking.
    14	
    15	## Authorization
    16	
    17	- Each agent must be registered in `security.mcp_allowed_agents`.
    18	- Tools returning knowledge are scoped to the resolved project.
    19	- `submit_memory_candidate` only creates candidates; it cannot accept or reject.
    20	- `update_task_state` requires the caller to hold the task lease or be the owner.
    21	
    22	## Unified Error Contract
    23	
    24	All tool errors return a structured JSON with:
    25	
    26	```json
    27	{
    28	  "error": {
    29	    "code": "VERSION_CONFLICT",
    30	    "message": "Task revision is stale; re-read and retry."
    31	  }
    32	}
    33	```
    34	
    35	Allowed codes: `PROJECT_UNRESOLVED`, `PROJECT_ACCESS_DENIED`, `SESSION_NOT_FOUND`,
    36	`TASK_CONFLICT`, `VERSION_CONFLICT`, `INVALID_EVIDENCE`, `APPROVAL_REQUIRED`,
    37	`MEMORY_DUPLICATE`, `EMBEDDING_UNAVAILABLE`, `INVALID_SCHEMA_VERSION`.
    38	
    39	## Token Budgeting
    40	
    41	- `get_project_context` accepts `max_output_tokens` and truncates deterministically.
    42	- When truncation occurs, `truncated=true` and a list of `references` is returned
    43	  so the agent can fetch more via `get_memory` or `search_memory`.
    44	
    45	## Idempotency
    46	
    47	- `submit_memory_candidate` requires `idempotency_key`; repeated submissions with the
    48	  same key return the same result.
    49	- `create_handoff` increments `revision`; callers should read latest first.