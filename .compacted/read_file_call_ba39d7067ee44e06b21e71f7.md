   100	        dispatcher.enqueue_index(k.memory_id, project_id)
   101	    return {"memory_id": k.memory_id, "revision": k.revision, "action": "created"}
   102	
   103	
   104	@router.delete("/knowledge/{memory_id}")
   105	async def delete_knowledge(request: Request, memory_id: str) -> dict:
   106	    """Mark a knowledge row archived and enqueue its index delete job."""
   107	    db = request.app.state.db
   108	    from agent_memory.storage import repositories as repo
   109	
   110	    revision = int(request.query_params.get("revision", 1))
   111	    updated = await repo.knowledge.update_knowledge(
   112	        db,
   113	        memory_id,
   114	        expected_revision=revision,
   115	        status=KnowledgeStatus.ARCHIVED,
   116	        changed_by="admin",
   117	    )
   118	    if updated is None:
   119	        raise HTTPException(404, f"knowledge {memory_id} not found")
   120	
   121	    dispatcher = getattr(request.app.state, "job_dispatcher", None)
   122	    if dispatcher:
   123	        dispatcher.enqueue_delete(memory_id, "")
   124	    return {"memory_id": memory_id, "status": "archived"}
   125	
   126	
   127	def payload_revision(request: Request, memory_id: str, default: int) -> int:
   128	    """Read revision from query param (used by DELETE)."""
   129	    return int(request.query_params.get("revision", default))
   130	
   131	
   132	# ---------------------------------------------------------------------------
   133	# Admin: drain index jobs
   134	# ---------------------------------------------------------------------------
   135	
   136	
   137	@admin_router.post("/index/drain")
   138	async def drain_index(
   139	    request: Request,
   140	    batch_size: int = 100,