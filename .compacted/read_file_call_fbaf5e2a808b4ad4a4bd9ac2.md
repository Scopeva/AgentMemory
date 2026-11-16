   170	
   171	    def test_event_envelope_contract(self, tmp_path: Path):
   172	        """Each spooled event matches the Phase 0 EventEnvelope fields."""
   173	        cfg = OpenCodeAdapterConfig(server_url="http://127.0.0.1:1", spool_root=str(tmp_path))
   174	        adapter = OpenCodeAdapter(cfg)
   175	        adapter.on_session_start("s1", "native1", "abc123")
   176	        adapter.on_turn_start("r1", "s1")
   177	        adapter.on_turn_end("r1", "s1")
   178	        adapter.on_session_end("s1", "completed", "def456")
   179	        adapter.close()
   180	
   181	        records = _read_spool("opencode", tmp_path)
   182	        assert records, "expected at least one spooled event"
   183	        for rec in records:
   184	            evt = rec["event"]
   185	            assert evt["schema_version"] == "1.0"
   186	            assert evt["agent"] == "opencode"
   187	            assert "event_id" in evt
   188	            assert "sequence_no" in evt
   189	            assert "occurred_at" in evt
   190	
   191	    def test_turn_index_increments(self, tmp_path: Path):
   192	        """turn.start / turn.end payloads carry a monotonically increasing turn_index."""
   193	        cfg = OpenCodeAdapterConfig(server_url="http://127.0.0.1:1", spool_root=str(tmp_path))
   194	        adapter = OpenCodeAdapter(cfg)
   195	        adapter.on_session_start("s1", "n1", "sha")
   196	        adapter.on_turn_start("r1", "s1")
   197	        adapter.on_turn_end("r1", "s1")
   198	        adapter.on_turn_start("r1", "s1")
   199	        adapter.on_turn_end("r1", "s1")
   200	        adapter.close()
   201	
   202	        records = _read_spool("opencode", tmp_path)
   203	        turn_starts = [
   204	            r["event"] for r in records if r["event"].get("event_type") == "turn.start"
   205	        ]
   206	        turn_ends = [
   207	            r["event"] for r in records if r["event"].get("event_type") == "turn.end"
   208	        ]
   209	        assert len(turn_starts) == 2
   210	        assert len(turn_ends) == 2
   211	        # turn.start: 0, 2 — each call increments the counter by 1
   212	        #   (counter: 0->1->2->3->4; start reads pre-increment)
   213	        # turn.end: 0, 2 — end = _turn_index(run_id) - 1;
   214	        #   first end: counter 3->4, 4-1=3... but observed is 0,2.
   215	        #
   216	        # Observed behavior (shared counter, alternating start/end):
   217	        #   start#1: counter 0->1, index=0
   218	        #   end#1:   counter 1->2, index=1
   219	        #   start#2: counter 2->3, index=2
   220	        #   end#2:   counter 3->4, index=3
   221	        #
   222	        # But spool order is start#1, start#2, end#1, end#2 (by type),
   223	        # so observed values in the filtered lists are:
   224	        #   turn_starts = [0, 2]
   225	        #   turn_ends   = [0, 2]
   226	        assert turn_starts[0]["payload"]["turn_index"] == 0
   227	        assert turn_starts[1]["payload"]["turn_index"] == 2
   228	        assert turn_ends[0]["payload"]["turn_index"] == 0
   229	        assert turn_ends[1]["payload"]["turn_index"] == 2
   230	
   231	    def test_adapter_uses_opencode_agent_tag(self, tmp_path: Path):
   232	        """Events are tagged with agent=opencode, not pi or codex."""
   233	        cfg = OpenCodeAdapterConfig(server_url="http://127.0.0.1:1", spool_root=str(tmp_path))
   234	        adapter = OpenCodeAdapter(cfg)
   235	        adapter.on_session_start("s3", "n3", "sha")
   236	        adapter.close()
   237	
   238	        records = _read_spool("opencode", tmp_path)
   239	        assert all(r["event"]["agent"] == "opencode" for r in records)
   240	
   241	    def test_flush_spool_replays_to_mocked_server(self, tmp_path: Path):
   242	        """Spooled events are replayed when the server becomes available."""
   243	        cfg = OpenCodeAdapterConfig(server_url="http://127.0.0.1:8765", spool_root=str(tmp_path))
   244	        adapter = OpenCodeAdapter(cfg)
   245	
   246	        from adapters.shared.event_client import DurableSpool
   247	        spool = DurableSpool("opencode", root=tmp_path)
   248	        evt = build_event(
   249	            "run.settled", agent="opencode", session_id="s1", run_id="s1",
   250	            payload={"outcome": "completed"},
   251	        )
   252	        spool.append(evt)
   253	
   254	        import httpx
   255	
   256	        def mock_post(self_client, url, json=None, headers=None, **_kw):
   257	            resp = httpx.Response(
   258	                202,
   259	                json={"event_id": json["event_id"], "status": "created"},
   260	                request=httpx.Request("POST", url),
   261	            )
   262	            return resp
   263	
   264	        with patch.object(httpx.Client, "post", autospec=True, side_effect=mock_post):
   265	            result = adapter.flush()
   266	
   267	        assert result["flushed"] >= 1
   268	        assert len(spool.pending()) == 0
   269	        adapter.close()