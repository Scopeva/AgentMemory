"""memoryctl: Local Agent Memory & Handoff Service CLI.

Subcommands:
  memoryctl doctor            Check DB, migrations, BGE-M3 endpoint
  memoryctl status            Show record counts
  memoryctl projects ...      Register / list projects
  memoryctl tasks ...         List tasks
  memoryctl handoffs ...      Show latest handoffs
  memoryctl memory ...        Search / inspect knowledge
  memoryctl pending ...       List / approve candidates
  memoryctl jobs retry        Retry failed background jobs
  memoryctl index ...         Index status / rebuild
  memoryctl backup ...        Create / verify

Implementation notes:
- All database access is synchronous via the standard sqlite3 module to
  keep the CLI dependency-free and robust under both plain ``python`` and
  ``pytest`` (where an event loop may already be running).
- Long-running background work should use the HTTP/API layer instead.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Optional

# Ensure the local src package is importable when running from a checkout.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from agent_memory.config import load_config


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _load_cfg():
    path = os.environ.get("AGENT_MEMORY_CONFIG_PATH", "")
    return load_config(path or None)


def _connect(cfg) -> sqlite3.Connection:
    conn = sqlite3.connect(str(cfg.database.resolved_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_doctor(args) -> int:
    cfg = _load_cfg()
    print(f"[doctor] config: {cfg.database.path}")

    # 1. DB reachable and schema migrated
    try:
        conn = _connect(cfg)
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        conn.close()
        migrations = row[0] if row and row[0] is not None else 0
        print(f"[doctor] schema_migrations: {migrations}")
    except Exception as e:
        print(f"[doctor] ERROR reading DB: {e}")
        return 1

    # 2. BGE-M3 endpoint (best-effort)
    if cfg.embedding.enabled:
        import urllib.request

        try:
            req = urllib.request.Request(
                f"{cfg.embedding.normalized_endpoint()}/health", method="GET"
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                print(f"[doctor] embedding endpoint OK: {resp.status}")
        except Exception as e:
            print(f"[doctor] WARNING embedding endpoint unreachable: {e}")
    else:
        print("[doctor] embedding disabled")

    return 0


def cmd_status(args) -> int:
    cfg = _load_cfg()
    try:
        conn = _connect(cfg)
        counts = {}
        for table in [
            "projects",
            "tasks",
            "runs",
            "events",
            "knowledge",
            "memory_candidates",
        ]:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[table] = row[0] if row else 0
        conn.close()
        print(json.dumps(counts, indent=2))
    except Exception as e:
        print(f"error: {e}")
        return 1
    return 0


def cmd_projects_register(args) -> int:
    import uuid

    cfg = _load_cfg()
    conn = _connect(cfg)
    project_id = args.project_id or str(uuid.uuid4())
    now = _utcnow()
    conn.execute(
        "INSERT INTO projects (project_id, name, status, created_at, updated_at) "
        "VALUES (?, ?, 'active', ?, ?) "
        "ON CONFLICT(project_id) DO UPDATE SET name = excluded.name, updated_at = ?",
        (project_id, args.name, now, now, now),
    )
    conn.commit()
    conn.close()
    print(f"registered project {project_id} ({args.name})")
    return 0


def cmd_projects_list(args) -> int:
    cfg = _load_cfg()
    conn = _connect(cfg)
    rows = conn.execute(
        "SELECT project_id, name, status FROM projects ORDER BY created_at DESC LIMIT ?",
        (args.limit,),
    ).fetchall()
    conn.close()
    for r in rows:
        print(f"{r['project_id']}\t{r['name']}\t{r['status']}")
    return 0


def cmd_projects_delete(args) -> int:
    """Cascade-delete a project and all of its data (FK-safe order).

    Mirrors DELETE /v1/projects/{id} server behavior, so it works even
    when the API is not running.
    """
    cfg = _load_cfg()
    conn = _connect(cfg)
    project_id = args.project_id

    # Confirm the project exists (clean error otherwise).
    row = conn.execute("SELECT 1 FROM projects WHERE project_id = ?", (project_id,)).fetchone()
    if not row:
        print(f"error: project {project_id!r} not found")
        conn.close()
        return 1

    deleted: dict[str, int] = {}

    # 1. events + checkpoints via this project's runs
    for table in ("events", "checkpoints"):
        cur = conn.execute(
            f"DELETE FROM {table} WHERE run_id IN "
            f"(SELECT run_id FROM runs WHERE project_id = ?)",
            (project_id,),
        )
        deleted[table] = cur.rowcount or 0

    cur = conn.execute("DELETE FROM runs WHERE project_id = ?", (project_id,))
    deleted["runs"] = cur.rowcount or 0

    for table in ("handoffs", "tasks"):
        cur = conn.execute(f"DELETE FROM {table} WHERE project_id = ?", (project_id,))
        deleted[table] = cur.rowcount or 0

    cur = conn.execute("DELETE FROM knowledge_revisions WHERE project_id = ?", (project_id,))
    deleted["knowledge_revisions"] = cur.rowcount or 0

    mem_ids = [
        r[0]
        for r in conn.execute(
            "SELECT memory_id FROM knowledge WHERE project_id = ?", (project_id,)
        ).fetchall()
    ]
    cur = conn.execute("DELETE FROM knowledge WHERE project_id = ?", (project_id,))
    deleted["knowledge"] = cur.rowcount or 0

    cur = conn.execute("DELETE FROM index_jobs WHERE project_id = ?", (project_id,))
    deleted["index_jobs"] = cur.rowcount or 0

    # FTS5 index — has its own project_id column.
    cur = conn.execute("DELETE FROM chunks_fts WHERE project_id = ?", (project_id,))
    deleted["fts_chunks"] = cur.rowcount or 0

    # vec virtual table only exists when sqlite-vec is loaded.
    try:
        probe = conn.execute("SELECT 1 FROM memory_vectors LIMIT 1").fetchone()
        if probe is not None:
            for mid in mem_ids:
                conn.execute("DELETE FROM memory_vectors WHERE memory_id = ?", (mid,))
            deleted["memory_vectors"] = len(mem_ids)
    except sqlite3.Error:
        pass  # vec not loaded — nothing to clean

    cur = conn.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
    deleted["projects"] = cur.rowcount or 0

    conn.commit()
    conn.close()

    for table, count in deleted.items():
        print(f"  {table:24s} {count}")
    print(f"deleted project {project_id!r} "
          f"({sum(deleted.values())} rows total)")
    return 0


def cmd_tasks_list(args) -> int:
    cfg = _load_cfg()
    conn = _connect(cfg)
    if args.project_id:
        rows = conn.execute(
            "SELECT task_id, title, status, revision, updated_at FROM tasks "
            "WHERE project_id = ? ORDER BY updated_at DESC LIMIT ?",
            (args.project_id, args.limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT task_id, title, status, revision, updated_at FROM tasks "
            "ORDER BY updated_at DESC LIMIT ?",
            (args.limit,),
        ).fetchall()
    conn.close()
    print(json.dumps([dict(r) for r in rows], indent=2))
    return 0


def cmd_handoffs_latest(args) -> int:
    cfg = _load_cfg()
    conn = _connect(cfg)
    if args.task_id:
        row = conn.execute(
            "SELECT * FROM handoffs WHERE task_id = ? AND is_stale = 0 "
            "ORDER BY revision DESC LIMIT 1",
            (args.task_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM handoffs WHERE source_workspace_id = ? AND is_stale = 0 "
            "ORDER BY created_at DESC LIMIT 1",
            (args.workspace_id or "",),
        ).fetchone()
    conn.close()
    if row is None:
        print("no handoff found")
        return 1
    print(json.dumps(dict(row), indent=2))
    return 0


def cmd_memory_search(args) -> int:
    cfg = _load_cfg()
    conn = _connect(cfg)
    q = f"%{args.query}%"
    rows = conn.execute(
        "SELECT memory_id, title, status, type FROM knowledge "
        "WHERE project_id = ? AND (title LIKE ? OR content LIKE ?) "
        "ORDER BY updated_at DESC LIMIT ?",
        (args.project_id, q, q, args.limit),
    ).fetchall()
    conn.close()
    print(json.dumps([dict(r) for r in rows], indent=2))
    return 0


def cmd_memory_inspect(args) -> int:
    cfg = _load_cfg()
    conn = _connect(cfg)
    k = conn.execute(
        "SELECT * FROM knowledge WHERE memory_id = ?", (args.memory_id,)
    ).fetchone()
    if not k:
        conn.close()
        print("memory not found")
        return 1
    k = dict(k)
    revs = conn.execute(
        "SELECT revision, title, status, changed_by, changed_at "
        "FROM knowledge_revisions WHERE memory_id = ? ORDER BY revision DESC",
        (args.memory_id,),
    ).fetchall()
    k["revisions"] = [dict(r) for r in revs]
    evs = conn.execute(
        "SELECT kind, value, verified_at FROM knowledge_sources WHERE memory_id = ?",
        (args.memory_id,),
    ).fetchall()
    k["evidence"] = [dict(r) for r in evs]
    conn.close()
    print(json.dumps(k, indent=2))
    return 0


def cmd_pending_list(args) -> int:
    cfg = _load_cfg()
    conn = _connect(cfg)
    if args.project_id:
        rows = conn.execute(
            "SELECT candidate_id, project_id, idempotency_key, status, created_at "
            "FROM memory_candidates WHERE project_id = ? AND status = 'pending' "
            "ORDER BY created_at DESC LIMIT ?",
            (args.project_id, args.limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT candidate_id, project_id, idempotency_key, status, created_at "
            "FROM memory_candidates WHERE status = 'pending' "
            "ORDER BY created_at DESC LIMIT ?",
            (args.limit,),
        ).fetchall()
    conn.close()
    print(json.dumps([dict(r) for r in rows], indent=2))
    return 0


def cmd_pending_approve(args) -> int:
    import uuid

    cfg = _load_cfg()
    conn = _connect(cfg)
    row = conn.execute(
        "SELECT candidate_id, project_id, run_id, memory_json, status "
        "FROM memory_candidates WHERE candidate_id = ?",
        (args.candidate_id,),
    ).fetchone()
    if not row or row["status"] != "pending":
        conn.close()
        print("error: candidate not found or already processed")
        return 1

    try:
        memory = json.loads(row["memory_json"])
    except (TypeError, json.JSONDecodeError):
        memory = {}

    memory_id = None
    if args.auto_accept:
        memory_id = str(uuid.uuid4())
        now = _utcnow()
        conn.execute(
            "INSERT INTO knowledge ("
            "memory_id, project_id, scope, type, status, title, content, revision, "
            "current_source_revision, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, 'accepted', ?, ?, 1, ?, ?, ?)",
            (
                memory_id,
                row["project_id"],
                memory.get("scope", "project"),
                memory.get("type", "unknown"),
                memory.get("title", "Untitled"),
                memory.get("content", ""),
                row["run_id"],
                now,
                now,
            ),
        )
        for ev in memory.get("evidence_refs", []):
            conn.execute(
                "INSERT INTO knowledge_sources "
                "(source_id, memory_id, kind, value, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    memory_id,
                    ev.get("kind", "agent_statement"),
                    ev.get("value", ""),
                    now,
                ),
            )

    conn.execute(
        "UPDATE memory_candidates SET status = ?, updated_at = ? "
        "WHERE candidate_id = ?",
        ("approved", _utcnow(), args.candidate_id),
    )
    conn.execute(
        "INSERT INTO approvals "
        "(approval_id, candidate_id, decision, decided_by, decided_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            args.candidate_id,
            "approved" if args.auto_accept else "reviewed",
            args.decided_by,
            _utcnow(),
        ),
    )
    conn.commit()
    conn.close()
    if memory_id:
        print(f"promoted to knowledge {memory_id}")
    else:
        print("candidate marked approved")
    return 0


def cmd_backup_create(args) -> int:
    cfg = _load_cfg()
    target = args.target or str(cfg.database.resolved_path()) + ".backup"
    src = sqlite3.connect(str(cfg.database.resolved_path()))
    dst = sqlite3.connect(target)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    print(f"backup written to {target}")
    return 0


def cmd_backup_verify(args) -> int:
    cfg = _load_cfg()
    target = args.target or str(cfg.database.resolved_path()) + ".backup"
    try:
        conn = sqlite3.connect(target)
        row = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if row and row[0] == "ok":
            print("integrity_check ok")
            return 0
        print(f"integrity_check failed: {row}")
        return 1
    except Exception as e:
        print(f"error: {e}")
        return 1


def _fts5_table(conn: sqlite3.Connection) -> str | None:
    """Return the FTS5 virtual table name if it exists (chunks_fts)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
    ).fetchone()
    return row[0] if row else None


def _vector_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='memory_vectors'"
    ).fetchone()
    return bool(row and row[0])


def cmd_index_status(args) -> int:
    """Show index table stats: FTS5 chunks, vector rows, pending jobs."""
    cfg = _load_cfg()
    conn = _connect(cfg)

    fts_table = _fts5_table(conn)
    fts_count = 0
    if fts_table:
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {fts_table}").fetchone()
            fts_count = row[0] if row else 0
        except sqlite3.Error:
            fts_count = -1

    vec_count = 0
    if _vector_table(conn):
        try:
            cnt = conn.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()
            vec_count = cnt[0] if cnt else 0
        except sqlite3.Error:
            vec_count = -1

    pending = 0
    failed = 0
    completed = 0
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) FROM index_jobs GROUP BY status"
        ).fetchall()
        for r in rows:
            if r["status"] == "pending":
                pending = r[0]
            elif r["status"] == "failed":
                failed = r[0]
            elif r["status"] == "completed":
                completed = r[0]
    except sqlite3.Error:
        pass

    conn.close()

    from agent_memory.retrieval.vector import vec_available

    status = {
        "fts_table": fts_table,
        "fts_chunks": fts_count,
        "vector_available": vec_available(),
        "vector_rows": vec_count,
        "index_jobs": {"pending": pending, "failed": failed, "completed": completed},
    }
    if getattr(args, "json", False):
        print(json.dumps(status))
    else:
        print(f"fts_table:        {fts_table}")
        print(f"fts_chunks:       {fts_count}")
        print(f"vector_available: {status['vector_available']}")
        print(f"vector_rows:      {vec_count}")
        print(f"index_jobs:       pending={pending} failed={failed} completed={completed}")
    return 0


def cmd_index_drain(args) -> int:
    """Manually drain pending index jobs (one-shot, no background loop needed)."""
    cfg = _load_cfg()
    conn = _connect(cfg)
    conn.execute("PRAGMA journal_mode = WAL")

    rows = conn.execute(
        "SELECT job_id, memory_id, project_id, job_type FROM index_jobs "
        "WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?",
        (args.batch_size,),
    ).fetchall()

    if not rows:
        conn.close()
        print(f"no pending index jobs (batch_size={args.batch_size})")
        return 0

    import asyncio
    from agent_memory.retrieval.indexing import IndexingWorker
    from agent_memory.retrieval.embedding import create_provider

    embedder = None
    if cfg.embedding.enabled:
        try:
            embedder = create_provider(cfg.embedding)
        except Exception as exc:
            print(f"warning: embedding provider unavailable, lexical-only: {exc}")

    worker = IndexingWorker(conn, cfg.retrieval, embedder)

    results = []
    for row in rows:
        conn.execute(
            "UPDATE index_jobs SET status='running', attempts=attempts+1, updated_at=? WHERE job_id=?",
            (_utcnow(), row["job_id"]),
        )
        conn.commit()
        try:
            if row["job_type"] == "delete":
                worker.delete_knowledge_index(row["memory_id"])
                conn.execute(
                    "UPDATE index_jobs SET status='skipped', updated_at=? WHERE job_id=?",
                    (_utcnow(), row["job_id"]),
                )
                results.append({"job_id": row["job_id"], "status": "skipped"})
            else:
                krow = conn.execute(
                    "SELECT memory_id, project_id, title, content, status "
                    "FROM knowledge WHERE memory_id=?",
                    (row["memory_id"],),
                ).fetchone()
                if krow is None:
                    conn.execute(
                        "UPDATE index_jobs SET status='skipped', updated_at=? WHERE job_id=?",
                        (_utcnow(), row["job_id"]),
                    )
                    results.append({"job_id": row["job_id"], "status": "skipped", "reason": "knowledge not found"})
                    conn.commit()
                    continue
                kdict = dict(krow)
                res = asyncio.get_event_loop().run_until_complete(
                    worker.index_knowledge(row["memory_id"], kdict)
                )
                conn.execute(
                    "UPDATE index_jobs SET status='completed', updated_at=? WHERE job_id=?",
                    (_utcnow(), row["job_id"]),
                )
                results.append({"job_id": row["job_id"], "status": "completed", **res})
        except Exception as exc:
            conn.execute(
                "UPDATE index_jobs SET status='failed', error=?, updated_at=? WHERE job_id=?",
                (str(exc), _utcnow(), row["job_id"]),
            )
            results.append({"job_id": row["job_id"], "status": "failed", "error": str(exc)})
        conn.commit()

    conn.close()
    print(json.dumps({"drained": len(results), "results": results}, indent=2))
    failed_n = sum(1 for r in results if r["status"] == "failed")
    return 0 if failed_n == 0 else 1


def cmd_index_rebuild(args) -> int:
    """Rebuild indexes from scratch.

    Without --project-id: wipes all FTS + vector entries and requeues every
    active knowledge row (full rebuild).

    With --project-id: only wipes index entries belonging to that project and
    requeues only its active knowledge rows.

    FTS5 (chunks_fts) cannot be filtered by project_id directly, so scoped
    deletes are done via memory_id (the chunk's entity_id). Full rebuilds
    delete the entire FTS + vector tables.
    """
    cfg = _load_cfg()
    conn = _connect(cfg)
    import uuid
    now = _utcnow()

    fts_table = _fts5_table(conn)
    vec_table = _vector_table(conn)

    if args.project_id:
        # Scoped rebuild: delete only this project's index data.
        # FTS5: delete chunks belonging to this project's memory rows.
        if fts_table:
            mem_ids = [
                r[0] for r in conn.execute(
                    "SELECT memory_id FROM knowledge WHERE project_id = ?",
                    (args.project_id,),
                ).fetchall()
            ]
            for mid in mem_ids:
                conn.execute(
                    f"DELETE FROM {fts_table} WHERE chunk_id LIKE ?",
                    (f"{mid}:%",),
                )
        if vec_table:
            for mid in mem_ids:
                conn.execute(
                    "DELETE FROM memory_vectors WHERE memory_id = ?", (mid,)
                )
        conn.execute(
            "DELETE FROM index_jobs WHERE project_id = ?", (args.project_id,)
        )
        active_rows = conn.execute(
            "SELECT memory_id, project_id FROM knowledge "
            "WHERE status != 'rejected' AND project_id = ?",
            (args.project_id,),
        ).fetchall()
    else:
        # Full rebuild: wipe all index data.
        if fts_table:
            conn.execute(f"DELETE FROM {fts_table}")
        if vec_table:
            conn.execute("DELETE FROM memory_vectors")
        conn.execute("DELETE FROM index_jobs")
        active_rows = conn.execute(
            "SELECT memory_id, project_id FROM knowledge WHERE status != 'rejected'"
        ).fetchall()

    for row in active_rows:
        conn.execute(
            "INSERT INTO index_jobs (job_id, memory_id, project_id, job_type, status, attempts, created_at, updated_at) "
            "VALUES (?, ?, ?, 'index', 'pending', 0, ?, ?)",
            (str(uuid.uuid4()), row["memory_id"], row["project_id"], now, now),
        )
    conn.commit()
    conn.close()
    scope = f" project {args.project_id}" if args.project_id else ""
    print(f"rebuild{scope}: queued {len(active_rows)} knowledge rows for reindexing")
    print("run 'memoryctl index drain' to process them")
    return 0


def cmd_jobs_retry(args) -> int:
    """Retry failed index jobs."""
    cfg = _load_cfg()
    conn = _connect(cfg)
    failed_rows = conn.execute(
        "SELECT job_id, memory_id, project_id, job_type, attempts, error FROM index_jobs WHERE status='failed'"
    ).fetchall()
    if not failed_rows:
        conn.close()
        print("no failed jobs to retry")
        return 0

    now = _utcnow()
    for row in failed_rows:
        conn.execute(
            "UPDATE index_jobs SET status='pending', attempts=attempts+1, error=NULL, updated_at=? WHERE job_id=?",
            (now, row["job_id"]),
        )
    conn.commit()
    conn.close()
    print(f"reset {len(failed_rows)} failed jobs to pending")
    print("run 'memoryctl index drain' to retry them")
    return 0


def cmd_knowledge_supersede(args) -> int:
    """Mark old memory superseded by new memory."""
    import uuid
    cfg = _load_cfg()
    conn = _connect(cfg)
    new_row = conn.execute(
        "SELECT memory_id, status, revision FROM knowledge WHERE memory_id = ?",
        (args.new_memory_id,),
    ).fetchone()
    old_row = conn.execute(
        "SELECT memory_id, status, revision FROM knowledge WHERE memory_id = ?",
        (args.old_memory_id,),
    ).fetchone()
    if not new_row or not old_row:
        conn.close()
        print("error: one or both memory items not found")
        return 1
    if new_row["status"] != "accepted" or old_row["status"] != "accepted":
        conn.close()
        print(f"error: new is '{new_row['status']}', old is '{old_row['status']}' (both must be 'accepted')")
        return 1

    now = _utcnow()
    conn.execute(
        "UPDATE knowledge SET status = 'superseded', revision = revision + 1, "
        "updated_at = ? WHERE memory_id = ?",
        (now, args.old_memory_id),
    )
    conn.execute(
        "INSERT INTO knowledge_revisions "
        "(memory_id, revision, title, content, status, changed_by, changed_at) "
        "SELECT memory_id, revision, title, content, status, ?, ? "
        "FROM knowledge WHERE memory_id = ?",
        ("memoryctl", now, args.old_memory_id),
    )
    conn.execute(
        "UPDATE knowledge SET revision = revision + 1, updated_at = ? "
        "WHERE memory_id = ?",
        (now, args.new_memory_id),
    )
    conn.commit()
    conn.close()
    print(f"superseded {args.old_memory_id} -> {args.new_memory_id}")
    return 0


def cmd_knowledge_archive(args) -> int:
    """Archive a knowledge item."""
    cfg = _load_cfg()
    conn = _connect(cfg)
    row = conn.execute(
        "SELECT memory_id, status, revision FROM knowledge WHERE memory_id = ?",
        (args.memory_id,),
    ).fetchone()
    if not row:
        conn.close()
        print("error: memory not found")
        return 1
    now = _utcnow()
    conn.execute(
        "UPDATE knowledge SET status = 'archived', revision = revision + 1, updated_at = ? "
        "WHERE memory_id = ? AND status != 'archived'",
        (now, args.memory_id),
    )
    conn.execute(
        "INSERT INTO knowledge_revisions "
        "(memory_id, revision, title, content, status, changed_by, changed_at) "
        "SELECT memory_id, revision, title, content, 'archived', ?, ? "
        "FROM knowledge WHERE memory_id = ?",
        ("memoryctl", now, args.memory_id),
    )
    conn.commit()
    conn.close()
    print(f"archived {args.memory_id}")
    return 0


def cmd_knowledge_reject(args) -> int:
    """Reject a knowledge item."""
    cfg = _load_cfg()
    conn = _connect(cfg)
    row = conn.execute(
        "SELECT memory_id, status, revision FROM knowledge WHERE memory_id = ?",
        (args.memory_id,),
    ).fetchone()
    if not row:
        conn.close()
        print("error: memory not found")
        return 1
    now = _utcnow()
    conn.execute(
        "UPDATE knowledge SET status = 'rejected', revision = revision + 1, updated_at = ? "
        "WHERE memory_id = ? AND status != 'rejected'",
        (now, args.memory_id),
    )
    conn.execute(
        "INSERT INTO knowledge_revisions "
        "(memory_id, revision, title, content, status, changed_by, changed_at) "
        "SELECT memory_id, revision, title, content, 'rejected', ?, ? "
        "FROM knowledge WHERE memory_id = ?",
        ("memoryctl", now, args.memory_id),
    )
    conn.commit()
    conn.close()
    print(f"rejected {args.memory_id}")
    return 0


def cmd_knowledge_governance(args) -> int:
    """Show governance summary for a project."""
    import difflib
    cfg = _load_cfg()
    conn = _connect(cfg)
    cutoff = (
        datetime.now(timezone.utc).replace(tzinfo=None) - __import__("datetime").timedelta(days=args.max_age_days)
    ).isoformat() + "Z"

    items = conn.execute(
        "SELECT memory_id, type, status, title, content, updated_at, revision "
        "FROM knowledge WHERE project_id = ? ORDER BY updated_at DESC LIMIT 1000",
        (args.project_id,),
    ).fetchall()
    conn.close()

    # Status counts
    counts: dict[str, int] = {}
    for r in items:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    # Superseded detection (same type, high content similarity)
    superseded_count = 0
    by_type: dict[str, list] = {}
    for r in items:
        if r["status"] == "accepted":
            by_type.setdefault(r["type"], []).append(r)
    for group in by_type.values():
        group.sort(key=lambda x: x["updated_at"])
        for i in range(len(group) - 1):
            a, b = group[i], group[i + 1]
            sim = difflib.SequenceMatcher(None, a["content"].lower(), b["content"].lower()).ratio()
            if sim >= 0.85:
                superseded_count += 1

    # Stale detection
    stale_count = sum(1 for r in items if r["status"] == "accepted" and r["updated_at"] < cutoff)

    summary = {
        "project_id": args.project_id,
        "total": len(items),
        "status_counts": counts,
        "potential_supersessions": superseded_count,
        "stale_items": stale_count,
        "max_age_days": args.max_age_days,
    }
    print(json.dumps(summary, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="memoryctl", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="Run diagnostics").set_defaults(func=cmd_doctor)
    sub.add_parser("status", help="Show record counts").set_defaults(func=cmd_status)

    pp = sub.add_parser("projects", help="Project management")
    psub = pp.add_subparsers(dest="projects_cmd", required=True)
    pr = psub.add_parser("register", help="Register a project")
    pr.add_argument("--name", required=True)
    pr.add_argument("--project-id", default=None)
    pr.set_defaults(func=cmd_projects_register)
    pl = psub.add_parser("list", help="List projects")
    pl.add_argument("--limit", type=int, default=20)
    pl.set_defaults(func=cmd_projects_list)
    pd = psub.add_parser("delete", help="Delete a project and all of its data")
    pd.add_argument("--project-id", required=True)
    pd.set_defaults(func=cmd_projects_delete)

    tp = sub.add_parser("tasks", help="Task inspection")
    tsub = tp.add_subparsers(dest="tasks_cmd", required=True)
    tl = tsub.add_parser("list", help="List tasks")
    tl.add_argument("--project-id", default=None)
    tl.add_argument("--limit", type=int, default=20)
    tl.set_defaults(func=cmd_tasks_list)

    hp = sub.add_parser("handoffs", help="Handoff inspection")
    hsub = hp.add_subparsers(dest="handoffs_cmd", required=True)
    hl = hsub.add_parser("latest", help="Show latest handoff")
    hl.add_argument("--task-id", default=None)
    hl.add_argument("--workspace-id", default=None)
    hl.set_defaults(func=cmd_handoffs_latest)

    mp = sub.add_parser("memory", help="Knowledge search / inspection")
    msub = mp.add_subparsers(dest="memory_cmd", required=True)
    ms = msub.add_parser("search", help="Search knowledge")
    ms.add_argument("--project-id", required=True)
    ms.add_argument("--query", required=True)
    ms.add_argument("--limit", type=int, default=10)
    ms.set_defaults(func=cmd_memory_search)
    mi = msub.add_parser("inspect", help="Inspect a knowledge item")
    mi.add_argument("--memory-id", required=True)
    mi.set_defaults(func=cmd_memory_inspect)

    np = sub.add_parser("pending", help="Memory candidate management")
    nsub = np.add_subparsers(dest="pending_cmd", required=True)
    nl = nsub.add_parser("list", help="List pending candidates")
    nl.add_argument("--project-id", default=None)
    nl.add_argument("--limit", type=int, default=20)
    nl.set_defaults(func=cmd_pending_list)
    na = nsub.add_parser("approve", help="Approve a candidate")
    na.add_argument("candidate_id")
    na.add_argument("--auto-accept", action="store_true")
    na.add_argument("--decided-by", default="memoryctl")
    na.set_defaults(func=cmd_pending_approve)

    bp = sub.add_parser("backup", help="Backup management")
    bsub = bp.add_subparsers(dest="backup_cmd", required=True)
    bc = bsub.add_parser("create", help="Create a backup")
    bc.add_argument("--target", default=None)
    bc.set_defaults(func=cmd_backup_create)
    bv = bsub.add_parser("verify", help="Verify a backup")
    bv.add_argument("--target", default=None)
    bv.set_defaults(func=cmd_backup_verify)

    ip = sub.add_parser("index", help="Index management")
    isub = ip.add_subparsers(dest="index_cmd", required=True)
    ist = isub.add_parser("status", help="Show index status")
    ist.add_argument("--json", action="store_true", help="output as JSON (for scripting)")
    ist.set_defaults(func=cmd_index_status)
    idp = isub.add_parser("drain", help="Drain pending index jobs")
    idp.add_argument("--batch-size", type=int, default=100)
    idp.set_defaults(func=cmd_index_drain)
    irb = isub.add_parser("rebuild", help="Rebuild indexes")
    irb.add_argument("--project-id", default=None, help="scope rebuild to a single project")
    irb.set_defaults(func=cmd_index_rebuild)

    jp = sub.add_parser("jobs", help="Background job management")
    jsub = jp.add_subparsers(dest="jobs_cmd", required=True)
    jsub.add_parser("retry", help="Retry a failed job").set_defaults(func=cmd_jobs_retry)

    kp = sub.add_parser("knowledge", help="Knowledge governance")
    ksub = kp.add_subparsers(dest="knowledge_cmd", required=True)
    ks = ksub.add_parser("supersede", help="Mark old memory superseded by new memory")
    ks.add_argument("old_memory_id")
    ks.add_argument("new_memory_id")
    ks.set_defaults(func=cmd_knowledge_supersede)
    ka = ksub.add_parser("archive", help="Archive a knowledge item")
    ka.add_argument("memory_id")
    ka.set_defaults(func=cmd_knowledge_archive)
    kr = ksub.add_parser("reject", help="Reject a knowledge item")
    kr.add_argument("memory_id")
    kr.set_defaults(func=cmd_knowledge_reject)
    kg = ksub.add_parser("governance", help="Show governance summary")
    kg.add_argument("--project-id", required=True)
    kg.add_argument("--max-age-days", type=int, default=30)
    kg.set_defaults(func=cmd_knowledge_governance)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
