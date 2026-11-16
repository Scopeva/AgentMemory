   200	    conn.close()
   201	    print(json.dumps([dict(r) for r in rows], indent=2))
   202	    return 0
   203	
   204	
   205	def cmd_memory_inspect(args) -> int:
   206	    cfg = _load_cfg()
   207	    conn = _connect(cfg)
   208	    k = conn.execute(
   209	        "SELECT * FROM knowledge WHERE memory_id = ?", (args.memory_id,)
   210	    ).fetchone()
   211	    if not k:
   212	        conn.close()
   213	        print("memory not found")
   214	        return 1
   215	    k = dict(k)
   216	    revs = conn.execute(
   217	        "SELECT revision, title, status, changed_by, changed_at "
   218	        "FROM knowledge_revisions WHERE memory_id = ? ORDER BY revision DESC",
   219	        (args.memory_id,),
   220	    ).fetchall()
   221	    k["revisions"] = [dict(r) for r in revs]
   222	    evs = conn.execute(
   223	        "SELECT kind, value, verified_at FROM knowledge_sources WHERE memory_id = ?",
   224	        (args.memory_id,),
   225	    ).fetchall()
   226	    k["evidence"] = [dict(r) for r in evs]
   227	    conn.close()
   228	    print(json.dumps(k, indent=2))
   229	    return 0
   230	
   231	
   232	def cmd_pending_list(args) -> int:
   233	    cfg = _load_cfg()
   234	    conn = _connect(cfg)
   235	    if args.project_id:
   236	        rows = conn.execute(
   237	            "SELECT candidate_id, project_id, idempotency_key, status, created_at "
   238	            "FROM memory_candidates WHERE project_id = ? AND status = 'pending' "
   239	            "ORDER BY created_at DESC LIMIT ?",
   240	            (args.project_id, args.limit),
   241	        ).fetchall()
   242	    else:
   243	        rows = conn.execute(
   244	            "SELECT candidate_id, project_id, idempotency_key, status, created_at "
   245	            "FROM memory_candidates WHERE status = 'pending' "
   246	            "ORDER BY created_at DESC LIMIT ?",
   247	            (args.limit,),
   248	        ).fetchall()
   249	    conn.close()
   250	    print(json.dumps([dict(r) for r in rows], indent=2))
   251	    return 0
   252	
   253	
   254	def cmd_pending_approve(args) -> int:
   255	    import uuid
   256	
   257	    cfg = _load_cfg()
   258	    conn = _connect(cfg)
   259	    row = conn.execute(
   260	        "SELECT candidate_id, project_id, run_id, memory_json, status "
   261	        "FROM memory_candidates WHERE candidate_id = ?",
   262	        (args.candidate_id,),
   263	    ).fetchone()
   264	    if not row or row["status"] != "pending":
   265	        conn.close()
   266	        print("error: candidate not found or already processed")
   267	        return 1
   268	
   269	    try:
   270	        memory = json.loads(row["memory_json"])
   271	    except (TypeError, json.JSONDecodeError):
   272	        memory = {}
   273	
   274	    memory_id = None
   275	    if args.auto_accept:
   276	        memory_id = str(uuid.uuid4())
   277	        now = _utcnow()
   278	        conn.execute(
   279	            "INSERT INTO knowledge ("
   280	            "memory_id, project_id, scope, type, status, title, content, revision, "
   281	            "current_source_revision, created_at, updated_at"
   282	            ") VALUES (?, ?, ?, ?, 'accepted', ?, ?, 1, ?, ?, ?)",
   283	            (
   284	                memory_id,
   285	                row["project_id"],
   286	                memory.get("scope", "project"),
   287	                memory.get("type", "unknown"),
   288	                memory.get("title", "Untitled"),
   289	                memory.get("content", ""),
   290	                row["run_id"],
   291	                now,
   292	                now,
   293	            ),
   294	        )
   295	        for ev in memory.get("evidence_refs", []):
   296	            conn.execute(
   297	                "INSERT INTO knowledge_sources "
   298	                "(source_id, memory_id, kind, value, created_at) "
   299	                "VALUES (?, ?, ?, ?, ?)",
   300	                (
   301	                    str(uuid.uuid4()),
   302	                    memory_id,
   303	                    ev.get("kind", "agent_statement"),
   304	                    ev.get("value", ""),
   305	                    now,
   306	                ),
   307	            )
   308	
   309	    conn.execute(
   310	        "UPDATE memory_candidates SET status = ?, updated_at = ? "
   311	        "WHERE candidate_id = ?",
   312	        ("approved", _utcnow(), args.candidate_id),
   313	    )
   314	    conn.execute(
   315	        "INSERT INTO approvals "
   316	        "(approval_id, candidate_id, decision, decided_by, decided_at) "
   317	        "VALUES (?, ?, ?, ?, ?)",
   318	        (
   319	            str(uuid.uuid4()),
   320	            args.candidate_id,
   321	            "approved" if args.auto_accept else "reviewed",
   322	            args.decided_by,
   323	            _utcnow(),
   324	        ),
   325	    )
   326	    conn.commit()
   327	    conn.close()
   328	    if memory_id:
   329	        print(f"promoted to knowledge {memory_id}")
   330	    else:
   331	        print("candidate marked approved")
   332	    return 0
   333	
   334	
   335	def cmd_backup_create(args) -> int:
   336	    cfg = _load_cfg()
   337	    target = args.target or str(cfg.database.resolved_path()) + ".backup"
   338	    src = sqlite3.connect(str(cfg.database.resolved_path()))
   339	    dst = sqlite3.connect(target)
   340	    with dst:
   341	        src.backup(dst)
   342	    dst.close()
   343	    src.close()
   344	    print(f"backup written to {target}")
   345	    return 0
   346	
   347	
   348	def cmd_backup_verify(args) -> int:
   349	    cfg = _load_cfg()
   350	    target = args.target or str(cfg.database.resolved_path()) + ".backup"
   351	    try:
   352	        conn = sqlite3.connect(target)
   353	        row = conn.execute("PRAGMA integrity_check").fetchone()
   354	        conn.close()
   355	        if row and row[0] == "ok":
   356	            print("integrity_check ok")
   357	            return 0
   358	        print(f"integrity_check failed: {row}")
   359	        return 1
   360	    except Exception as e:
   361	        print(f"error: {e}")
   362	        return 1
   363	
   364	
   365	def cmd_index_status(args) -> int:
   366	    print("index status: FTS5 available; sqlite-vec not yet enabled (Phase 4)")
   367	    return 0
   368	
   369	
   370	def cmd_index_rebuild(args) -> int:
   371	    print("index rebuild not yet implemented (Phase 4)")
   372	    return 1
   373	
   374	
   375	def cmd_jobs_retry(args) -> int:
   376	    print("jobs retry not yet implemented (Phase 4)")
   377	    return 1
   378	
   379	
   380	# ---------------------------------------------------------------------------
   381	# Argument parser
   382	# ---------------------------------------------------------------------------
   383	
   384	
   385	def build_parser() -> argparse.ArgumentParser:
   386	    p = argparse.ArgumentParser(prog="memoryctl", description=__doc__.split("\n")[0])
   387	    sub = p.add_subparsers(dest="cmd", required=True)
   388	
   389	    sub.add_parser("doctor", help="Run diagnostics").set_defaults(func=cmd_doctor)
   390	    sub.add_parser("status", help="Show record counts").set_defaults(func=cmd_status)
   391	
   392	    pp = sub.add_parser("projects", help="Project management")
   393	    psub = pp.add_subparsers(dest="projects_cmd", required=True)
   394	    pr = psub.add_parser("register", help="Register a project")
   395	    pr.add_argument("--name", required=True)
   396	    pr.add_argument("--project-id", default=None)
   397	    pr.set_defaults(func=cmd_projects_register)
   398	    pl = psub.add_parser("list", help="List projects")
   399	    pl.add_argument("--limit", type=int, default=20)

... [truncated, showing 200/268 lines, 7770/11265 chars]