OK: fixed register_project
The event loop scope for asynchronous fixtures will default to the fixture scope. Future versions of pytest-asyncio will default the loop scope for asynchronous fixtures to "function" scope. Set the default fixture loop scope explicitly in order to avoid unexpected behavior in the future. Valid fixture loop scopes are: "function", "class", "module", "package", "session". Set it to "fixture-scope" to keep the current behavior.

  warnings.warn(PytestDeprecationWarning(_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET))
....F
=================================== FAILURES ===================================
____________ TestHybridSearchEndToEnd.test_search_service_injection ____________

self = <test_phase4_retrieval.TestHybridSearchEndToEnd object at 0xffff8ff40b90>
e2e_db = Database(config=DatabaseConfig(path='/tmp/pytest-of-root/pytest-4/test_search_service_injection0/e2e.db', journal_mode='wal', busy_timeout_ms=5000))
sync_conn = <sqlite3.Connection object at 0xffff8ff487c0>

    async def test_search_service_injection(self, e2e_db, sync_conn):
        search = SearchService(
            db=e2e_db,
            retrieval_config=RetrievalConfig(),
            embedding_provider=None,
            synchronous_conn=sync_conn,
        )
        set_search_service(search)
        try:
            result = await core.search_memory(e2e_db, "p1", "anything")
            # Fallback path (no FTS rows): retrieval_mode should be lexical_basic
>           assert result["retrieval_mode"] in {"lexical_basic", "lexical_only", "hybrid", "fallback_like"}
E           AssertionError: assert 'none' in {'fallback_like', 'hybrid', 'lexical_basic', 'lexical_only'}

tests/integration/test_phase4_retrieval.py:167: AssertionError
=========================== short test summary info ============================
FAILED tests/integration/test_phase4_retrieval.py::TestHybridSearchEndToEnd::test_search_service_injection
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed, 4 passed in 0.43s