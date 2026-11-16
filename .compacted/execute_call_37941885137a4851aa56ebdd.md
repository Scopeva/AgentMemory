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