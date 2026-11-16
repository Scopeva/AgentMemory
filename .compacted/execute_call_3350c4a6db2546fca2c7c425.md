1:"""End-to-end test: Pi adapter spools events → flush to a live server.
5:2. Server comes "online" (mocked) and spool is flushed
54:class TestPiToServerFlow:
55:    def test_spooled_events_flush_to_server(
128:        #    (mock httpx so we can capture the payloads and forward to server_db)
131:        def _mock_post(self_client, url, json=None, headers=None, **_kw):
140:        with patch.object(httpx.Client, "post", autospec=True, side_effect=_mock_post):
141:            # Re-create a client pointed at the "now online" server and flush
147:            flush_result = new_client.flush_spool()
150:        assert flush_result["flushed"] >= 7, f"expected >=7 flushed, got {flush_result}"