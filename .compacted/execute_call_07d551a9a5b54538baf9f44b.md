            resp = MagicMock()
            resp.status_code = 202
            resp.json.return_value = {"event_id": (json or {}).get("event_id"), "status": "created"}
            resp.raise_for_status.return_value = None
            return resp
    
>       with patch.object(httpx.Client, "post", autospec=True, side_effect=_mock_post):
                          ^^^^^
E       NameError: name 'httpx' is not defined

tests/test_pi_to_server.py:140: NameError
=========================== short test summary info ============================
FAILED tests/test_pi_to_server.py::TestPiToServerFlow::test_spooled_events_flush_to_server
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed, 44 passed in 1.07s