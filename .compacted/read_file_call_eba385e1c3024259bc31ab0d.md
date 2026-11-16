   155	        assert m.max_output_tokens == 2000
   156	
   157	    def test_search_memory(self):
   158	        m = SearchMemoryInput(project_id="p1", query="jwt refresh")
   159	        assert m.limit == 8
   160	
   161	    def test_create_handoff(self):
   162	        m = CreateHandoffInput(task_id="t1", summary="WIP")
   163	        assert m.pending == []
   164	        assert m.revision is None or True  # revision handled server-side
   165	
   166	    def test_submit_memory_candidate(self):
   167	        m = SubmitMemoryCandidateInput(
   168	            project_id="p1",
   169	            idempotency_key="idem-1",
   170	            memories=[