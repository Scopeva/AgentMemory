    async def test_enqueue_and_drain(self, e2e_db, sync_conn):
        # Insert project + knowledge row into the e2e (async) db
>       await _seed_project_and_knowledge(e2e_db)

tests/integration/test_phase4_retrieval.py:84: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

db = Database(config=DatabaseConfig(path='/tmp/pytest-of-root/pytest-3/test_enqueue_and_drain0/e2e.db', journal_mode='wal', busy_timeout_ms=5000))

    async def _seed_project_and_knowledge(db: Database) -> None:
        """Insert a project and knowledge row into the e2e database."""
        import uuid
        from agent_memory.schemas import Project, Knowledge, KnowledgeStatus
    
        from agent_memory.storage import repositories as repo
    
        pid = "p1"
>       await repo.projects.create_project(
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
            db,
            Project(project_id=pid, name="Test Project", created_at="2026-01-01", updated_at="2026-01-01"),
        )
E       AttributeError: module 'agent_memory.storage.repositories.projects' has no attribute 'create_project'. Did you mean: 'get_project'?

tests/integration/test_phase4_retrieval.py:180: AttributeError
=========================== short test summary info ============================
FAILED tests/integration/test_phase4_retrieval.py::TestDispatcherDrain::test_enqueue_and_drain
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.34s