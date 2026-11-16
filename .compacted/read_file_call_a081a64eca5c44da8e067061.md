     1	# Event Contract
     2	
     3	## HTTP Endpoints
     4	
     5	| Method | Path | Purpose |
     6	|--------|------|---------|
     7	| POST   | `/v1/events` | Submit a single lifecycle event |
     8	| POST   | `/v1/events/batch` | Submit multiple events in one request |
     9	| POST   | `/v1/checkpoints` | Persist a checkpoint |
    10	| POST   | `/v1/extractions` | Record memory extraction outcome |
    11	| GET    | `/v1/runs/{run_id}` | Query run state and pending work |
    12	| GET    | `/v1/jobs/{job_id}` | Query background job status |
    13	| GET    | `/health/live` | Liveness probe |
    14	| GET    | `/health/ready` | Readiness probe |
    15	
    16	Admin API (restricted):
    17	
    18	| Method | Path | Purpose |
    19	|--------|------|---------|
    20	| GET    | `/v1/admin/pending` | List pending memory candidates |
    21	| POST   | `/v1/admin/approvals/{id}/approve` | Approve a candidate |
    22	| POST   | `/v1/admin/approvals/{id}/reject` | Reject a candidate |
    23	| POST   | `/v1/admin/jobs/{id}/retry` | Retry a failed job |
    24	
    25	## Event Envelope
    26	
    27	```json
    28	{
    29	  "schema_version": "1.0",
    30	  "event_id": "evt-001",
    31	  "event_type": "run.settled",
    32	  "agent": "pi",
    33	  "session_id": "pi-session-001",
    34	  "run_id": "run-001",
    35	  "project_id": "website-audit-core",
    36	  "workspace_id": "workspace-001",
    37	  "task_id": "task-001",
    38	  "sequence_no": 12,
    39	  "occurred_at": "2026-11-16T09:00:00Z",
    40	  "payload": {
    41	    "outcome": "completed",
    42	    "extraction_status": "pending"
    43	  }
    44	}
    45	```
    46	
    47	## Event Types
    48	
    49	- `run.started` – Agent begins a run.
    50	- `run.settled` – Run finished normally (after retries/continuations).
    51	- `run.interrupted` – Run was aborted.
    52	- `checkpoint.created` – A recoverable checkpoint was saved.
    53	- `session.start` – Agent session opened.
    54	- `session.end` – Agent session closed.
    55	- `session.compacted` – Context compaction occurred.
    56	- `turn.end` – Model turn completed.
    57	- `memory.extraction_requested` – Adapter asked agent to produce memory.
    58	- `memory.extraction_completed` – Agent returned extraction payload.
    59	
    60	## Delivery Guarantees
    61	
    62	- **At-least-once** delivery: adapters may retry; the server deduplicates using `event_id` (idempotency key).
    63	- **Local spool**: when the server is unreachable, adapters persist events to a local spool directory and replay them on recovery.
    64	- **Sequence numbers**: adapters assign `sequence_no`; the server validates monotonicity per run.
    65	
    66	## Error Responses
    67	
    68	| Code | Meaning |
    69	|------|---------|
    70	| `202` | Event accepted (or already seen) |
    71	| `400` | Invalid schema / unknown event type |
    72	| `403` | Project access denied |
    73	| `404` | Unknown run/session |
    74	| `409` | Version conflict (stale sequence or revision) |
    75	| `503` | Embedding unavailable (event still persisted, retrieval degrades to lexical-only) |