    18	    await db.connection().execute(
    19	        "INSERT INTO sessions (session_id, agent_type, native_session_id, workspace_id, created_at) "
    20	        "VALUES (?, ?, ?, ?, ?)",
    21	        (
    22	            session.session_id,
    23	            session.agent_type.value,
    24	            session.native_session_id,
    25	            session.workspace_id,
    26	            now,
    27	        ),
    28	    )
    29	    return session
    30	
    31	
    32	async def get_session(db: Database, session_id: str) -> Optional[Session]:
    33	    async with db.connection() as conn:
    34	        cursor = await conn.execute(
    35	            "SELECT session_id, agent_type, native_session_id, workspace_id, created_at "
    36	            "FROM sessions WHERE session_id = ?",
    37	            (session_id,),
    38	        )
    39	        row = await cursor.fetchone()
    40	        if not row:
    41	            return None
    42	        return Session(
    43	            session_id=row["session_id"],
    44	            agent_type=AgentType(row["agent_type"]),
    45	            native_session_id=row["native_session_id"],
    46	            workspace_id=row["workspace_id"],
    47	            created_at=row["created_at"],
    48	        )
    49	
    50	
    51	async def list_sessions_by_workspace(
    52	    db: Database, workspace_id: str, limit: int = 50
    53	) -> list[Session]:
    54	    async with db.connection() as conn:
    55	        cursor = await conn.execute(
    56	            "SELECT session_id, agent_type, native_session_id, workspace_id, created_at "
    57	            "FROM sessions WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?",
    58	            (workspace_id, limit),
    59	        )
    60	        rows = await cursor.fetchall()
    61	        return [
    62	            Session(
    63	                session_id=r["session_id"],
    64	                agent_type=AgentType(r["agent_type"]),
    65	                native_session_id=r["native_session_id"],
    66	                workspace_id=r["workspace_id"],
    67	                created_at=r["created_at"],
    68	            )
    69	            for r in rows
    70	        ]
    71	
    72	
    73	async def start_run(db: Database, run: Run) -> Run:
    74	    now = _utcnow()
    75	    await db.connection().execute(
    76	        "INSERT INTO runs (run_id, task_id, session_id, status, head_sha_start, head_sha_end, started_at, ended_at) "
    77	        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    78	        (
    79	            run.run_id,
    80	            run.task_id,
    81	            run.session_id,
    82	            run.status.value,
    83	            run.head_sha_start,
    84	            run.head_sha_end,
    85	            now,
    86	            None,
    87	        ),
    88	    )
    89	    return run
    90	
    91	
    92	async def end_run(
    93	    db: Database,
    94	    run_id: str,
    95	    status: RunStatus,
    96	    head_sha_end: Optional[str] = None,
    97	) -> Optional[Run]:
    98	    now = _utcnow()
    99	    await db.connection().execute(
   100	        "UPDATE runs SET status = ?, head_sha_end = ?, ended_at = ? WHERE run_id = ?",