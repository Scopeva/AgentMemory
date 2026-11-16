tx = <_queue.SimpleQueue object at 0xffffb5fb8a00>

    def _connection_worker_thread(tx: _TxQueue):
        """
        Execute function calls on a separate thread.
    
        :meta private:
        """
        while True:
            # Continues running until all queue items are processed,
            # even after connection is closed (so we can finalize all
            # futures)
    
            future, function = tx.get()
    
            try:
                LOG.debug("executing %s", function)
>               result = function()
                         ^^^^^^^^^^
E               sqlite3.IntegrityError: FOREIGN KEY constraint failed

.venv/lib/python3.13/site-packages/aiosqlite/core.py:63: IntegrityError
=========================== short test summary info ============================
FAILED tests/integration/test_phase4_retrieval_api.py::TestRetrievalRoutes::test_create_knowledge_enqueues_index
1 failed, 3 passed in 1.35s