   325	    return {"created": created, "duplicates": duplicates, "total": len(events)}
   326	
   327	
   328	async def submit_checkpoint(db: Database, checkpoint: Checkpoint) -> Checkpoint:
   329	    """Persist a checkpoint."""
   330	    return await repo.checkpoints.create_checkpoint(db, checkpoint)
   331	
   332	
   333	# ---------------------------------------------------------------------------
   334	# Search (Phase 4 will upgrade to hybrid)
   335	# ---------------------------------------------------------------------------
   336	
   337	
   338	async def search_memory(
   339	    db: Database,
   340	    project_id: str,
   341	    query: str,
   342	    limit: int = 8,
   343	    filters: Optional[dict] = None,
   344	) -> dict:
   345	    """Phase 2: lexical search over knowledge titles/content.