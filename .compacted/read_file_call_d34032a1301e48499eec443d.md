   320	        was_new = await repo.events.insert_event(db, evt)
   321	        if was_new:
   322	            created += 1
   323	        else:
   324	            duplicates += 1
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
   346	
   347	    Phase 4 replaces this with FTS5 + sqlite-vec hybrid RRF.
   348	    """
   349	    status_filter = None
   350	    if filters and "status" in filters:
   351	        try:
   352	            status_filter = KnowledgeStatus(filters["status"])
   353	        except ValueError:
   354	            status_filter = None
   355	
   356	    results = await repo.knowledge.list_knowledge_by_project(
   357	        db,
   358	        project_id,
   359	        status=status_filter,
   360	        limit=limit,
   361	    )
   362	    # Simple keyword filter on title/content
   363	    lower_query = query.lower()
   364	    matched = [
   365	        k for k in results
   366	        if lower_query in k.title.lower() or lower_query in k.content.lower()
   367	    ]
   368	    return {
   369	        "results": [k.model_dump() for k in matched[:limit]],
   370	        "retrieval_mode": "lexical_basic",
   371	    }
   372	
   373	
   374	# ---------------------------------------------------------------------------
   375	# Admin / candidates
   376	# ---------------------------------------------------------------------------
   377	
   378	
   379	async def list_pending_candidates(
   380	    db: Database, project_id: Optional[str] = None, limit: int = 50
   381	) -> list[dict]:
   382	    """List pending memory candidates (admin channel)."""
   383	    return await repo.knowledge.list_pending_candidates(
   384	        db, project_id=project_id, limit=limit
   385	    )
   386	
   387	
   388	async def approve_candidate(
   389	    db: Database,
   390	    candidate_id: str,