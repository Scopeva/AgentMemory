<error>
exit_code=1
stdout:
....FF..F.                                                               [100%]
=================================== FAILURES ===================================
_________________ TestEvents.test_event_idempotent_by_event_id _________________

self = <test_storage.TestEvents object at 0xffff8e81dbd0>
db = Database(config=DatabaseConfig(path='/tmp/tmpodilj_o3/test.db', journal_mode='wal', busy_timeout_ms=5000))

    @pytest.mark.asyncio
    async def test_event_idempotent_by_event_id(self, db):
        p = await register_project(db, Project(name="evt-project"))
        # Need a session and run first
        ws_id = "ws-1"
        s = Session(agent_type=AgentType.PI, workspace_id=ws_id)
>       await register_session(db, s)

tests/unit/test_storage.py:110: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
src/agent_memory/storage/repositories/sessions.py:19: in register_session
    await conn.execute(
.venv/lib/python3.13/site-packages/aiosqlite/core.py:223: in execute
    cursor = await self._execute(self._conn.execute, sql, parameters)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.venv/lib/python3.13/site-packages/aiosqlite/core.py:160: in _execute
    return await future
           ^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

tx = <_queue.SimpleQueue object at 0xffff8e881660>

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
_________________ TestEvents.test_event_idempotent_by_sequence _________________

self = <test_storage.TestEvents object at 0xffff8e81dd10>
db = Database(config=DatabaseConfig(path='/tmp/tmpbcdiqtbq/test.db', journal_mode='wal', busy_timeout_ms=5000))

    @pytest.mark.asyncio
    async def test_event_idempotent_by_sequence(self, db):
        p = await register_project(db, Project(name="seq-project"))
        s = Session(agent_type=AgentType.CODEX, workspace_id="ws-x")
>       await register_session(db, s)

tests/unit/test_storage.py:131: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
src/agent_memory/storage/repositories/sessions.py:19: in register_session
    await conn.execute(
.venv/lib/python3.13/site-packages/aiosqlite/core.py:223: in execute
    cursor = await self._execute(self._conn.execute, sql, parameters)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.venv/lib/python3.13/site-packages/aiosqlite/core.py:160: in _execute
    return await future
           ^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

tx = <_queue.SimpleQueue object at 0xffff8e8ebf40>

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
_______________ TestKnowledge.test_memory_candidate_idempotency ________________

self = <test_storage.TestKnowledge object at 0xffff8e844770>
db = Database(config=DatabaseConfig(path='/tmp/tmpnwiqcy0b/test.db', journal_mode='wal', busy_timeout_ms=5000))

    @pytest.mark.asyncio
    async def test_memory_candidate_idempotency(self, db):
        p = await register_project(db, Project(name="mc-project"))
        memory = {"type": "adr", "title": "X", "content": "Y", "scope": "project"}
>       assert await insert_memory_candidate(db, p.project_id, None, "key-1", memory) is True
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/unit/test_storage.py:208: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
src/agent_memory/storage/repositories/knowledge.py:249: in insert_memory_candidate
    await conn.execute(
.venv/lib/python3.13/site-packages/aiosqlite/core.py:223: in execute
    cursor = await self._execute(self._conn.execute, sql, parameters)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.venv/lib/python3.13/site-packages/aiosqlite/core.py:160: in _execute
    return await future
           ^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

tx = <_queue.SimpleQueue object at 0xffff8d73a140>

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
E               sqlite3.OperationalError: no such function: uuidgen

.venv/lib/python3.13/site-packages/aiosqlite/core.py:63: OperationalError
=========================== short test summary info ============================
FAILED tests/unit/test_storage.py::TestEvents::test_event_idempotent_by_event_id
FAILED tests/unit/test_storage.py::TestEvents::test_event_idempotent_by_sequence
FAILED tests/unit/test_storage.py::TestKnowledge::test_memory_candidate_idempotency
3 failed, 7 passed in 0.42s
stderr:
/mnt/workspace/.venv/lib/python3.13/site-packages/pytest_asyncio/plugin.py:306: PytestDeprecationWarning: The configuration option "asyncio_default_fixture_loop_scope" is unset.
The event loop scope for asynchronous fixtures will default to the fixture scope. Future versions of pytest-asyncio will default the loop scope for asynchronous fixtures to "function" scope. Set the default fixture loop scope explicitly in order to avoid unexpected behavior in the future. Valid fixture loop scopes are: "function", "class", "module", "package", "session". Set it to "fixture-scope" to keep the current behavior.

  warnings.warn(PytestDeprecationWarning(_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET))
</error>