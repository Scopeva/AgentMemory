# Event Contract

## HTTP Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST   | `/v1/events` | Submit a single lifecycle event |
| POST   | `/v1/events/batch` | Submit multiple events in one request |
| POST   | `/v1/checkpoints` | Persist a checkpoint |
| POST   | `/v1/extractions` | Record memory extraction outcome |
| GET    | `/v1/runs/{run_id}` | Query run state and pending work |
| GET    | `/v1/jobs/{job_id}` | Query background job status |
| GET    | `/health/live` | Liveness probe |
| GET    | `/health/ready` | Readiness probe |

Admin API (restricted):

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/v1/admin/pending` | List pending memory candidates |
| POST   | `/v1/admin/approvals/{id}/approve` | Approve a candidate |
| POST   | `/v1/admin/approvals/{id}/reject` | Reject a candidate |
| POST   | `/v1/admin/jobs/{id}/retry` | Retry a failed job |

## Event Envelope

```json
{
  "schema_version": "1.0",
  "event_id": "evt-001",
  "event_type": "run.settled",
  "agent": "pi",
  "session_id": "pi-session-001",
  "run_id": "run-001",
  "project_id": "website-audit-core",
  "workspace_id": "workspace-001",
  "task_id": "task-001",
  "sequence_no": 12,
  "occurred_at": "2026-11-16T09:00:00Z",
  "payload": {
    "outcome": "completed",
    "extraction_status": "pending"
  }
}
```

## Event Types

- `run.started` – Agent begins a run.
- `run.settled` – Run finished normally (after retries/continuations).
- `run.interrupted` – Run was aborted.
- `checkpoint.created` – A recoverable checkpoint was saved.
- `session.start` – Agent session opened.
- `session.end` – Agent session closed.
- `session.compacted` – Context compaction occurred.
- `turn.end` – Model turn completed.
- `memory.extraction_requested` – Adapter asked agent to produce memory.
- `memory.extraction_completed` – Agent returned extraction payload. When
  `payload.memories` is a list of structured memory objects and `project_id`
  is present, the server creates idempotent reviewable candidates (one per
  title); it does not auto-accept them.

## Delivery Guarantees

- **At-least-once** delivery: adapters may retry; the server deduplicates using `event_id` (idempotency key).
- **Local spool**: when the server is unreachable, adapters persist events to a local spool directory and replay them on recovery.
- **Sequence numbers**: adapters assign `sequence_no`; the server validates monotonicity per run.

## Error Responses

| Code | Meaning |
|------|---------|
| `202` | Event accepted (or already seen) |
| `400` | Invalid schema / unknown event type |
| `403` | Project access denied |
| `404` | Unknown run/session |
| `409` | Version conflict (stale sequence or revision) |
| `503` | Embedding unavailable (event still persisted, retrieval degrades to lexical-only) |


## Phase 4–6 Extensions

### Retrieval HTTP Endpoints (Phase 4)

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/v1/search?project_id=&query=` | Hybrid search over chunk index |
| POST   | `/v1/knowledge` | Create or update knowledge + enqueue index job |
| DELETE | `/v1/knowledge/{memory_id}?revision=` | Archive knowledge + enqueue delete |

### Admin Retrieval Endpoints (Phase 4)

| Method | Path | Purpose |
|--------|------|---------|
| POST   | `/v1/admin/index/drain` | Drain pending index jobs |
| GET    | `/v1/admin/index/status` | Index job queue status + vector availability |

### Governance Functions (Phase 6)

Available via `agent_memory.services.core` and `agent_memory.services.governance`:

- `governance_summary(db, project_id, max_age_days)` – aggregate metrics
- `find_superseded(db, project_id, content_threshold, limit)` – similarity-based
- `find_duplicates(db, project_id, title_threshold, content_threshold, limit)`
- `list_stale_knowledge(db, project_id, max_age_days, limit)`
- `approve_and_supersede(db, new_id, old_id, decided_by, reason)`
- `archive_knowledge(db, memory_id, decided_by, reason)`
- `reject_knowledge(db, memory_id, decided_by, reason)`

### CLI Subcommands (Phase 6)

```
memoryctl knowledge supersede <old_id> <new_id>
memoryctl knowledge archive <memory_id>
memoryctl knowledge reject <memory_id>
memoryctl knowledge governance --project-id <id> [--max-age-days N]
```
