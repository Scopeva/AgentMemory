tests/test_pi_to_server.py:146: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
adapters/shared/event_client.py:226: in flush_spool
    result = self.submit(event)
             ^^^^^^^^^^^^^^^^^^
adapters/shared/event_client.py:182: in submit
    resp = self._client.post(
/usr/local/lib/python3.13/unittest/mock.py:1169: in __call__
    return self._mock_call(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/usr/local/lib/python3.13/unittest/mock.py:1173: in _mock_call
    return self._execute_mock_call(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/usr/local/lib/python3.13/unittest/mock.py:1240: in _execute_mock_call
    result = effect(*args, **kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

a = ('http://127.0.0.1:8765/v1/events',)
kw = {'json': {'schema_version': '1.0', 'event_id': '7cdc7a38-d8f0-4e20-9bd0-b74f90148dbe', 'event_type': 'session.start', 'agent': 'pi', ...}, 'headers': {'X-Agent': 'pi'}}

>   with patch("httpx.Client.post", side_effect=lambda *a, **kw: _mock_post(*a, **kw)):
                                                                 ^^^^^^^^^^^^^^^^^^^^
E   TypeError: TestPiToServerFlow.test_spooled_events_flush_to_server.<locals>._mock_post() got an unexpected keyword argument 'json'

tests/test_pi_to_server.py:140: TypeError
=========================== short test summary info ============================
FAILED tests/test_pi_to_server.py::TestPiToServerFlow::test_spooled_events_flush_to_server
========================= 1 failed, 1 passed in 0.49s ==========================