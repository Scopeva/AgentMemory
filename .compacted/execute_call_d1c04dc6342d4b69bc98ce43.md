/mnt/workspace/.venv/lib/python3.13/site-packages/pytest_asyncio/plugin.py:306: PytestDeprecationWarning: The configuration option "asyncio_default_fixture_loop_scope" is unset.
The event loop scope for asynchronous fixtures will default to the fixture scope. Future versions of pytest-asyncio will default the loop scope for asynchronous fixtures to "function" scope. Set the default fixture loop scope explicitly in order to avoid unexpected behavior in the future. Valid fixture loop scopes are: "function", "class", "module", "package", "session". Set it to "fixture-scope" to keep the current behavior.

  warnings.warn(PytestDeprecationWarning(_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET))
============================= test session starts ==============================
platform linux -- Python 3.13.18, pytest-9.2.0, pluggy-1.7.0 -- /mnt/workspace/.venv/bin/python
cachedir: .pytest_cache
rootdir: /mnt/workspace
configfile: pyproject.toml
plugins: anyio-4.16.0, asyncio-1.5.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 14 items

tests/test_pi_adapter.py::TestDurableSpool::test_append_and_pending PASSED [  7%]
tests/test_pi_adapter.py::TestDurableSpool::test_mark_acknowledged_removes_from_pending PASSED [ 14%]
tests/test_pi_adapter.py::TestDurableSpool::test_clear_acked PASSED      [ 21%]
tests/test_pi_adapter.py::TestDurableSpool::test_persistence_across_instances PASSED [ 28%]
tests/test_pi_adapter.py::TestEventClientSpoolFallback::test_submit_falls_back_to_spool_when_server_unreachable PASSED [ 35%]
tests/test_pi_adapter.py::TestEventClientSpoolFallback::test_flush_spool_replays_events PASSED [ 42%]
tests/test_pi_adapter.py::TestRunGuard::test_allows_one_extraction_per_run PASSED [ 50%]
tests/test_pi_adapter.py::TestRunGuard::test_blocks_when_origin_is_memory_extraction PASSED [ 57%]
tests/test_pi_adapter.py::TestRunGuard::test_different_runs_independent PASSED [ 64%]
tests/test_pi_adapter.py::TestRunGuard::test_reset_clears_guard PASSED   [ 71%]
tests/test_pi_adapter.py::TestPiAdapterLifecycle::test_full_lifecycle_spools_all_events PASSED [ 78%]
tests/test_pi_adapter.py::TestPiAdapterLifecycle::test_no_extraction_for_trivial_completed_run PASSED [ 85%]
tests/test_pi_adapter.py::TestPiAdapterLifecycle::test_recursion_guard_blocks_double_extraction PASSED [ 92%]
tests/test_pi_adapter.py::TestPiAdapterLifecycle::test_no_durable_memory_is_legal_empty_result PASSED [100%]

============================== 14 passed in 0.31s ==============================