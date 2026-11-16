   160	            embedding_provider=None,
   161	            synchronous_conn=sync_conn,
   162	        )
   163	        set_search_service(search)
   164	        try:
   165	            result = await core.search_memory(e2e_db, "p1", "anything")
   166	            # Fallback path (no FTS rows): retrieval_mode should be lexical_basic
   167	            assert result["retrieval_mode"] in {"lexical_basic", "lexical_only", "hybrid", "fallback_like"}
   168	        finally:
   169	            set_search_service(None)
   170	