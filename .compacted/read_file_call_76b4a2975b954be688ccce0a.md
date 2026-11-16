    55	        import asyncio
    56	
    57	        migrations = asyncio.run(_check_db())
    58	        print(f"[doctor] schema_migrations: {migrations}")
    59	    except Exception as e:
    60	        print(f"[doctor] ERROR reading DB: {e}")
    61	        return 1
    62	
    63	    # 2. BGE-M3 endpoint (best-effort)
    64	    if cfg.embedding.enabled:
    65	        import urllib.request
    66	
    67	        try:
    68	            req = urllib.request.Request(
    69	                f"{cfg.embedding.normalized_endpoint()}/health", method="GET"
    70	            )
    71	            with urllib.request.urlopen(req, timeout=3) as resp:
    72	                print(f"[doctor] embedding endpoint OK: {resp.status}")
    73	        except Exception as e:
    74	            print(f"[doctor] WARNING embedding endpoint unreachable: {e}")
    75	    else:
    76	        print("[doctor] embedding disabled")
    77	
    78	    return 0
    79	
    80	
    81	def cmd_status(args) -> int:
    82	    cfg = _load_cfg()
    83	    import aiosqlite
    84	    import asyncio
    85	
    86	    async def _counts():
    87	        conn = await aiosqlite.connect(str(cfg.database.resolved_path()))
    88	        conn.row_factory = aiosqlite.Row
    89	        counts = {}
    90	        for table in [
    91	            "projects",
    92	            "tasks",
    93	            "runs",
    94	            "events",
    95	            "knowledge",
    96	            "memory_candidates",
    97	        ]:
    98	            cur = await conn.execute(f"SELECT COUNT(*) FROM {table}")
    99	            row = await cur.fetchone()
   100	            counts[table] = row[0] if row else 0
   101	        await conn.close()
   102	        return counts
   103	
   104	    try:
   105	        c = asyncio.run(_counts())
   106	        print(json.dumps(c, indent=2))
   107	    except Exception as e:
   108	        print(f"error: {e}")
   109	        return 1
   110	    return 0
   111	
   112	
   113	def cmd_projects_register(args) -> int:
   114	    import aiosqlite
   115	    import asyncio
   116	    import uuid
   117	
   118	    cfg = _load_cfg()
   119	
   120	    async def _register():
   121	        conn = await aiosqlite.connect(str(cfg.database.resolved_path()))
   122	        project_id = args.project_id or str(uuid.uuid4())
   123	        await conn.execute(
   124	            "INSERT INTO projects (project_id, name, status, created_at, updated_at) "
   125	            "VALUES (?, ?, 'active', datetime('now'), datetime('now')) "
   126	            "ON CONFLICT(project_id) DO UPDATE SET name = excluded.name",
   127	            (project_id, args.name),
   128	        )
   129	        await conn.commit()
   130	        await conn.close()
   131	        return project_id
   132	
   133	    pid = asyncio.run(_register())
   134	    print(f"registered project {pid} ({args.name})")
   135	    return 0
   136	
   137	
   138	def cmd_projects_list(args) -> int:
   139	    import aiosqlite
   140	    import asyncio