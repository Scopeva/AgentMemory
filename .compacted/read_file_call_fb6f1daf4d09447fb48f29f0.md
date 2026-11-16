    92	        await conn.commit()
    93	    return run
    94	
    95	
    96	async def end_run(
    97	    db: Database,
    98	    run_id: str,
    99	    status: RunStatus,
   100	    head_sha_end: Optional[str] = None,
   101	) -> Optional[Run]:
   102	    now = _utcnow()
   103	    await db.connection().execute(
   104	        "UPDATE runs SET status = ?, head_sha_end = ?, ended_at = ? WHERE run_id = ?",
   105	        (status.value, head_sha_end, now, run_id),
   106	    )
   107	    async with db.connection() as conn:
   108	        cursor = await conn.execute(
   109	            "SELECT run_id, task_id, session_id, status, head_sha_start, head_sha_end, started_at, ended_at "
   110	            "FROM runs WHERE run_id = ?",
   111	            (run_id,),
   112	        )
   113	        row = await cursor.fetchone()
   114	        if not row:
   115	            return None
   116	        return Run(
   117	            run_id=row["run_id"],
   118	            task_id=row["task_id"],
   119	            session_id=row["session_id"],
   120	            status=RunStatus(row["status"]),