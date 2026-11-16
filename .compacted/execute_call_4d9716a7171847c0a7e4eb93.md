============================= test session starts ==============================
platform linux -- Python 3.13.18, pytest-9.2.0, pluggy-1.7.0 -- /mnt/workspace/.venv/bin/python
cachedir: .pytest_cache
rootdir: /mnt/workspace
configfile: pyproject.toml
plugins: anyio-4.16.0, asyncio-1.5.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 6 items

tests/integration/test_phase2_handoff.py::TestPhase2HandoffFlow::test_pi_creates_handoff_and_codex_resumes PASSED [ 16%]
tests/integration/test_phase2_handoff.py::TestPhase2HandoffFlow::test_handoff_revision_increments_monotonically PASSED [ 33%]
tests/integration/test_phase2_handoff.py::TestPhase2HandoffFlow::test_task_state_reflects_handoff_activity PASSED [ 50%]
tests/integration/test_phase2_handoff.py::TestPhase2HandoffFlow::test_stale_handoff_detection_via_head_sha PASSED [ 66%]
tests/integration/test_phase2_handoff.py::TestPhase2HandoffFlow::test_project_context_includes_recent_handoffs PASSED [ 83%]
tests/integration/test_phase2_handoff.py::TestPhase2HandoffFlow::test_two_agents_cannot_overwrite_newer_handoff PASSED [100%]

============================== 6 passed in 0.34s ===============================
stderr:
/mnt/workspace/.venv/lib/python3.13/site-packages/pytest_asyncio/plugin.py:306: PytestDeprecationWarning: The configuration option "asyncio_default_fixture_loop_scope" is unset.
The event loop scope for asynchronous fixtures will default to the fixture scope. Future versions of pytest-asyncio will default the loop scope for asynchronous fixtures to "function" scope. Set the default fixture loop scope explicitly in order to avoid unexpected behavior in the future. Valid fixture loop scopes are: "function", "class", "module", "package", "session". Set it to "fixture-scope" to keep the current behavior.

  warnings.warn(PytestDeprecationWarning(_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET))