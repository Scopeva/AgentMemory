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
   400	    pl.set_defaults(func=cmd_projects_list)
   401	
   402	    tp = sub.add_parser("tasks", help="Task inspection")
   403	    tsub = tp.add_subparsers(dest="tasks_cmd", required=True)
   404	    tl = tsub.add_parser("list", help="List tasks")
   405	    tl.add_argument("--project-id", default=None)
   406	    tl.add_argument("--limit", type=int, default=20)
   407	    tl.set_defaults(func=cmd_tasks_list)
   408	
   409	    hp = sub.add_parser("handoffs", help="Handoff inspection")
   410	    hsub = hp.add_subparsers(dest="handoffs_cmd", required=True)
   411	    hl = hsub.add_parser("latest", help="Show latest handoff")
   412	    hl.add_argument("--task-id", default=None)
   413	    hl.add_argument("--workspace-id", default=None)
   414	    hl.set_defaults(func=cmd_handoffs_latest)
   415	
   416	    mp = sub.add_parser("memory", help="Knowledge search / inspection")
   417	    msub = mp.add_subparsers(dest="memory_cmd", required=True)
   418	    ms = msub.add_parser("search", help="Search knowledge")
   419	    ms.add_argument("--project-id", required=True)
   420	    ms.add_argument("--query", required=True)
   421	    ms.add_argument("--limit", type=int, default=10)
   422	    ms.set_defaults(func=cmd_memory_search)
   423	    mi = msub.add_parser("inspect", help="Inspect a knowledge item")
   424	    mi.add_argument("--memory-id", required=True)
   425	    mi.set_defaults(func=cmd_memory_inspect)
   426	
   427	    np = sub.add_parser("pending", help="Memory candidate management")
   428	    nsub = np.add_subparsers(dest="pending_cmd", required=True)
   429	    nl = nsub.add_parser("list", help="List pending candidates")
   430	    nl.add_argument("--project-id", default=None)
   431	    nl.add_argument("--limit", type=int, default=20)
   432	    nl.set_defaults(func=cmd_pending_list)
   433	    na = nsub.add_parser("approve", help="Approve a candidate")
   434	    na.add_argument("candidate_id")
   435	    na.add_argument("--auto-accept", action="store_true")
   436	    na.add_argument("--decided-by", default="memoryctl")
   437	    na.set_defaults(func=cmd_pending_approve)
   438	
   439	    bp = sub.add_parser("backup", help="Backup management")
   440	    bsub = bp.add_subparsers(dest="backup_cmd", required=True)
   441	    bc = bsub.add_parser("create", help="Create a backup")
   442	    bc.add_argument("--target", default=None)
   443	    bc.set_defaults(func=cmd_backup_create)
   444	    bv = bsub.add_parser("verify", help="Verify a backup")
   445	    bv.add_argument("--target", default=None)
   446	    bv.set_defaults(func=cmd_backup_verify)
   447	
   448	    ip = sub.add_parser("index", help="Index management")
   449	    isub = ip.add_subparsers(dest="index_cmd", required=True)
   450	    isub.add_parser("status", help="Show index status").set_defaults(func=cmd_index_status)
   451	    isub.add_parser("rebuild", help="Rebuild indexes").set_defaults(func=cmd_index_rebuild)
   452	
   453	    jp = sub.add_parser("jobs", help="Background job management")
   454	    jsub = jp.add_subparsers(dest="jobs_cmd", required=True)
   455	    jsub.add_parser("retry", help="Retry a failed job").set_defaults(func=cmd_jobs_retry)
   456	
   457	    return p
   458	
   459	
   460	def main(argv: Optional[list[str]] = None) -> int:
   461	    parser = build_parser()
   462	    args = parser.parse_args(argv)
   463	    return args.func(args)
   464	
   465	
   466	if __name__ == "__main__":
   467	    raise SystemExit(main())