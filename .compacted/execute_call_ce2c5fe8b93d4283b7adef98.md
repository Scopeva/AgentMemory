/mnt/workspace/.venv/lib/python3.13/site-packages/pytest_asyncio/plugin.py:306: PytestDeprecationWarning: The configuration option "asyncio_default_fixture_loop_scope" is unset.
The event loop scope for asynchronous fixtures will default to the fixture scope. Future versions of pytest-asyncio will default the loop scope for asynchronous fixtures to "function" scope. Set the default fixture loop scope explicitly in order to avoid unexpected behavior in the future. Valid fixture loop scopes are: "function", "class", "module", "package", "session". Set it to "fixture-scope" to keep the current behavior.

  warnings.warn(PytestDeprecationWarning(_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET))
..............E
==================================== ERRORS ====================================
__________ ERROR at setup of TestLexicalIndex.test_upsert_and_search ___________

    @pytest.fixture
    def sync_conn():
        import sqlite3
    
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
>       conn.execute(
            "CREATE TABLE chunks_fts (chunk_id, project_id, entity_id, document_type, "
            "title, summary, text, active) USING fts5("
            "chunk_id UNINDEXED, project_id UNINDEXED, entity_id UNINDEXED, "
            "document_type UNINDEXED, title, summary, text, active UNINDEXED, "
            "tokenize = 'unicode61')"
        )
E       sqlite3.OperationalError: near "USING": syntax error

tests/unit/test_retrieval.py:189: OperationalError
=========================== short test summary info ============================
ERROR tests/unit/test_retrieval.py::TestLexicalIndex::test_upsert_and_search
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
14 passed, 1 error in 0.30s