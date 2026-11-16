     1	"""memoryctl: Local Agent Memory & Handoff Service CLI.
     2	
     3	Subcommands:
     4	  memoryctl doctor            Check service, DB, migrations, BGE-M3, spool, backups
     5	  memoryctl status            Show running service and counts
     6	  memoryctl projects ...      Register / list projects
     7	  memoryctl tasks ...         List tasks, show state
     8	  memoryctl handoffs ...      Show latest handoffs
     9	  memoryctl memory ...        Search / inspect knowledge
    10	  memoryctl pending ...       List / approve / reject candidates
    11	  memoryctl jobs retry        Retry failed background jobs
    12	  memoryctl index ...         Index status / rebuild
    13	  memoryctl backup ...        Create / verify / restore
    14	"""
    15	
    16	from __future__ import annotations
    17	
    18	import argparse
    19	import json
    20	import os
    21	import sys
    22	from typing import Optional
    23	
    24	from datetime import datetime, timezone
    25	
    26	# Ensure the local src package is importable when running from a checkout.
    27	sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
    28	
    29	from agent_memory.config import load_config
    30	
    31	
    32	def _utcnow() -> str:
    33	    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    34	
    35	
    36	def _load_cfg() -> "AppConfig":
    37	    path = os.environ.get("AGENT_MEMORY_CONFIG_PATH", "")
    38	    return load_config(path or None)
    39	
    40	
    41	# ---------------------------------------------------------------------------
    42	# Subcommand handlers (synchronous wrappers around async service layer)
    43	# ---------------------------------------------------------------------------
    44	
    45	
    46	def cmd_doctor(args) -> int:
    47	    cfg = _load_cfg()
    48	    print(f"[doctor] config: {cfg.database.path}")
    49	
    50	    # 1. DB reachable
    51	    import aiosqlite
    52	
    53	    async def _check_db():
    54	        conn = await aiosqlite.connect(str(cfg.database.resolved_path()))
    55	        cur = await conn.execute("SELECT MAX(version) FROM schema_migrations")
    56	        row = await cur.fetchone()
    57	        await conn.close()
    58	        return row[0] if row else 0
    59	
    60	    try:
    61	        import asyncio
    62	
    63	        migrations = asyncio.run(_check_db())
    64	        print(f"[doctor] schema_migrations: {migrations}")
    65	    except Exception as e:
    66	        print(f"[doctor] ERROR reading DB: {e}")
    67	        return 1
    68	
    69	    # 2. BGE-M3 endpoint (best-effort)
    70	    if cfg.embedding.enabled:
    71	        import urllib.request
    72	
    73	        try:
    74	            req = urllib.request.Request(
    75	                f"{cfg.embedding.normalized_endpoint()}/health", method="GET"
    76	            )
    77	            with urllib.request.urlopen(req, timeout=3) as resp:
    78	                print(f"[doctor] embedding endpoint OK: {resp.status}")
    79	        except Exception as e:
    80	            print(f"[doctor] WARNING embedding endpoint unreachable: {e}")
    81	    else:
    82	        print("[doctor] embedding disabled")
    83	
    84	    return 0
    85	
    86	
    87	def cmd_status(args) -> int:
    88	    cfg = _load_cfg()
    89	    import aiosqlite
    90	    import asyncio
    91	
    92	    async def _counts():
    93	        conn = await aiosqlite.connect(str(cfg.database.resolved_path()))
    94	        conn.row_factory = aiosqlite.Row
    95	        counts = {}
    96	        for table in [
    97	            "projects",
    98	            "tasks",
    99	            "runs",
   100	            "events",
   101	            "knowledge",
   102	            "memory_candidates",
   103	        ]:
   104	            cur = await conn.execute(f"SELECT COUNT(*) FROM {table}")
   105	            row = await cur.fetchone()
   106	            counts[table] = row[0] if row else 0
   107	        await conn.close()
   108	        return counts
   109	
   110	    try:
   111	        c = asyncio.run(_counts())
   112	        print(json.dumps(c, indent=2))
   113	    except Exception as e:
   114	        print(f"error: {e}")
   115	        return 1
   116	    return 0
   117	
   118	
   119	def cmd_projects_register(args) -> int:
   120	    import aiosqlite
   121	    import asyncio
   122	    import uuid
   123	
   124	    cfg = _load_cfg()
   125	
   126	    async def _register():
   127	        conn = await aiosqlite.connect(str(cfg.database.resolved_path()))
   128	        project_id = args.project_id or str(uuid.uuid4())
   129	        now = _utcnow()
   130	        await conn.execute(
   131	            "INSERT INTO projects (project_id, name, status, created_at, updated_at) "
   132	            "VALUES (?, ?, 'active', ?, ?) "
   133	            "ON CONFLICT(project_id) DO UPDATE SET name = excluded.name, updated_at = ?",
   134	            (project_id, args.name, now, now, now),
   135	        )
   136	        await conn.commit()
   137	        await conn.close()
   138	        return project_id
   139	
   140	    pid = asyncio.run(_register())
   141	    print(f"registered project {pid} ({args.name})")
   142	    return 0
   143	
   144	
   145	def cmd_projects_list(args) -> int:
   146	    import aiosqlite
   147	    import asyncio
   148	
   149	    cfg = _load_cfg()
   150	
   151	    async def _list():
   152	        conn = await aiosqlite.connect(str(cfg.database.resolved_path()))
   153	        conn.row_factory = aiosqlite.Row
   154	        cur = await conn.execute(
   155	            "SELECT project_id, name, status FROM projects ORDER BY created_at DESC LIMIT ?",
   156	            (args.limit,),
   157	        )
   158	        rows = await cur.fetchall()
   159	        await conn.close()
   160	        return [dict(r) for r in rows]
   161	
   162	    rows = asyncio.run(_list())
   163	    for r in rows:
   164	        print(f"{r['project_id']}\t{r['name']}\t{r['status']}")
   165	    return 0
   166	
   167	
   168	def cmd_handoffs_latest(args) -> int:
   169	    import aiosqlite
   170	    import asyncio
   171	
   172	    cfg = _load_cfg()
   173	
   174	    async def _latest(task_id: Optional[str], workspace_id: Optional[str]):
   175	        conn = await aiosqlite.connect(str(cfg.database.resolved_path()))
   176	        conn.row_factory = aiosqlite.Row
   177	        if task_id:
   178	            cur = await conn.execute(
   179	                "SELECT * FROM handoffs WHERE task_id = ? AND is_stale = 0 "
   180	                "ORDER BY revision DESC LIMIT 1",
   181	                (task_id,),
   182	            )
   183	        else:
   184	            cur = await conn.execute(
   185	                "SELECT * FROM handoffs WHERE source_workspace_id = ? AND is_stale = 0 "
   186	                "ORDER BY created_at DESC LIMIT 1",
   187	                (workspace_id or "",),
   188	            )
   189	        row = await cur.fetchone()
   190	        await conn.close()
   191	        return dict(row) if row else None
   192	
   193	    h = asyncio.run(_latest(args.task_id, args.workspace_id))
   194	    if h is None:
   195	        print("no handoff found")
   196	        return 1
   197	    print(json.dumps(h, indent=2))
   198	    return 0
   199	
   200	

... [truncated, showing 200/540 lines, 7402/21545 chars]