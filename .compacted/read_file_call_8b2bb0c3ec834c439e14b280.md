    41	async def create_knowledge(db: Database, k: Knowledge) -> Knowledge:
    42	    now = _utcnow()
    43	    async with db.connection() as conn:
    44	        await conn.execute(
    45	            "INSERT INTO knowledge ("
    46	            "memory_id, project_id, scope, type, status, title, content, revision, "
    47	            "current_source_revision, supersedes_memory_id, created_at, updated_at"
    48	            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    49	            (
    50	                k.memory_id,
    51	                k.project_id,
    52	                k.scope.value,
    53	                k.type,
    54	                k.status.value,
    55	                k.title,
    56	                k.content,
    57	                k.revision,
    58	                k.current_source_revision,
    59	                k.supersedes_memory_id,
    60	                now,
    61	                now,
    62	            ),
    63	        )
    64	        # Initial revision record
    65	        await conn.execute(
    66	            "INSERT INTO knowledge_revisions "
    67	            "(memory_id, revision, title, content, status, changed_by, changed_at) "
    68	            "VALUES (?, ?, ?, ?, ?, ?, ?)",
    69	            (
    70	                k.memory_id,
    71	                k.revision,
    72	                k.title,
    73	                k.content,
    74	                k.status.value,
    75	                "system",
    76	                now,
    77	            ),
    78	        )
    79	        # Evidence sources
    80	        import uuid
    81	
    82	        for ev in k.evidence:
    83	            source_id = str(uuid.uuid4())
    84	            await conn.execute(
    85	                "INSERT INTO knowledge_sources "
    86	                "(source_id, memory_id, kind, value, created_at) "
    87	                "VALUES (?, ?, ?, ?, ?)",
    88	                (source_id, k.memory_id, ev.kind.value, ev.value, now),
    89	            )
    90	        await conn.commit()
    91	    return k
    92	
    93	