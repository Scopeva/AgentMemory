async def approve_candidate(
    db: Database,
    candidate_id: str,
    decided_by: str,
    auto_accept: bool = False,
) -> Optional[str]:
    """Approve a candidate; optionally promote to accepted knowledge.

    Returns the new knowledge memory_id if auto_accept is True and promotion succeeded,
    otherwise None.
    """
    now = _utcnow()
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT candidate_id, project_id, run_id, memory_json, status "
            "FROM memory_candidates WHERE candidate_id = ?",
            (candidate_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        if row["status"] != "pending":
            return None

        try:
            memory = json.loads(row["memory_json"])
        except (TypeError, json.JSONDecodeError):
            memory = {}

        target_status = "approved"
        memory_id: Optional[str] = None

        if auto_accept:
            # Promote to knowledge table
            import uuid

            memory_id = str(uuid.uuid4())
            evidence_raw = memory.get("evidence_refs", [])
            evidence = [
                EvidenceRef(
                    kind=e.get("kind", "agent_statement"),
                    value=e.get("value", ""),
                )
                for e in evidence_raw
            ]
            k = Knowledge(
                memory_id=memory_id,
                project_id=row["project_id"],
                scope=KnowledgeScope(memory.get("scope", "project")),
                type=memory.get("type", "unknown"),
                status=KnowledgeStatus.ACCEPTED,
                title=memory.get("title", "Untitled"),
                content=memory.get("content", ""),
                evidence=evidence,
            )
            await conn.execute(
                "INSERT INTO knowledge ("
                "memory_id, project_id, scope, type, status, title, content, revision, "
                "current_source_revision, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
                (
                    memory_id,
                    row["project_id"],
                    k.scope.value,
                    k.type,
                    k.status.value,
                    k.title,
                    k.content,
                    row["run_id"],
                    now,
                    now,
                ),
            )
            await conn.execute(
                "INSERT INTO knowledge_revisions "
                "(memory_id, revision, title, content, status, changed_by, changed_at) "
                "VALUES (?, 1, ?, ?, ?, ?, ?)",
                (memory_id, k.title, k.content, k.status.value, "auto-promote", now),
            )
            for ev in evidence:
                await conn.execute(
                    "INSERT INTO knowledge_sources (source_id, memory_id, kind, value, created_at) "
                    "VALUES (uuidgen(), ?, ?, ?, ?)",
                    (memory_id, ev.kind.value, ev.value, now),
                )
            target_status = "approved"

        await conn.execute(
            "UPDATE memory_candidates SET status = ?, updated_at = ? WHERE candidate_id = ?",
            (target_status, now, candidate_id),
        )
        await conn.execute(
            "INSERT INTO approvals (approval_id, candidate_id, decision, decided_by, decided_at) "
            "VALUES (uuidgen(), ?, ?, ?, ?)",
            (candidate_id, "approved" if auto_accept else "reviewed", decided_by, now),
        )
        await conn.commit()
        return memory_id


async def reject_candidate(
    db: Database, candidate_id: str, decided_by: str, reason: Optional[str] = None
) -> bool:
    now = _utcnow()
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT candidate_id, status FROM memory_candidates WHERE candidate_id = ?",
            (candidate_id,),
        )
        row = await cursor.fetchone()
        if not row or row["status"] != "pending":
            return False
        await conn.execute(
            "UPDATE memory_candidates SET status = 'rejected', updated_at = ? WHERE candidate_id = ?",
            (now, candidate_id),
        )
        await conn.execute(
            "INSERT INTO approvals (approval_id, candidate_id, decision, decided_by, decided_at) "
            "VALUES (uuidgen(), ?, ?, ?, ?)",
            (candidate_id, "rejected", decided_by, now),
        )
        await conn.commit()
        return True