<error>
exit_code=1
stdout:
F.F.FFFFFF                                                               [100%]
=================================== FAILURES ===================================
__________________ TestProjects.test_register_and_get_project __________________

self = <test_storage.TestProjects object at 0xffff8f189310>
db = Database(config=DatabaseConfig(path='/tmp/tmptwgfwuj1/test.db', journal_mode='wal', busy_timeout_ms=5000))

    @pytest.mark.asyncio
    async def test_register_and_get_project(self, db):
>       p = await register_project(db, Project(name="demo-project"))
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/unit/test_storage.py:59: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

db = Database(config=DatabaseConfig(path='/tmp/tmptwgfwuj1/test.db', journal_mode='wal', busy_timeout_ms=5000))
project = Project(schema_version='1.0', project_id='ca381837-e370-412d-8e37-eecdcc87a63c', name='demo-project', status=<ProjectStatus.ACTIVE: 'active'>, created_at='2026-11-16T10:10:45.034939Z', updated_at='2026-11-16T10:10:45.034955Z')

    async def register_project(db: Database, project: Project) -> Project:
        now = _utcnow()
>       await db.connection().execute(
              ^^^^^^^^^^^^^^^^^^^^^^^
            "INSERT INTO projects (project_id, name, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (project.project_id, project.name, project.status.value, now, now),
        )
E       AttributeError: '_AsyncGeneratorContextManager' object has no attribute 'execute'

src/agent_memory/storage/repositories/projects.py:18: AttributeError
_________________ TestTasks.test_create_and_optimistic_update __________________

self = <test_storage.TestTasks object at 0xffff8f189a90>
db = Database(config=DatabaseConfig(path='/tmp/tmp22qskm0d/test.db', journal_mode='wal', busy_timeout_ms=5000))

    @pytest.mark.asyncio
    async def test_create_and_optimistic_update(self, db):
>       p = await register_project(db, Project(name="t-project"))
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/unit/test_storage.py:73: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

db = Database(config=DatabaseConfig(path='/tmp/tmp22qskm0d/test.db', journal_mode='wal', busy_timeout_ms=5000))
project = Project(schema_version='1.0', project_id='4e5b0149-e0c8-4ef6-be10-6d9c66e6eb6b', name='t-project', status=<ProjectStatus.ACTIVE: 'active'>, created_at='2026-11-16T10:10:45.083128Z', updated_at='2026-11-16T10:10:45.083138Z')

    async def register_project(db: Database, project: Project) -> Project:
        now = _utcnow()
>       await db.connection().execute(
              ^^^^^^^^^^^^^^^^^^^^^^^
            "INSERT INTO projects (project_id, name, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (project.project_id, project.name, project.status.value, now, now),
        )
E       AttributeError: '_AsyncGeneratorContextManager' object has no attribute 'execute'

src/agent_memory/storage/repositories/projects.py:18: AttributeError
_________________ TestEvents.test_event_idempotent_by_event_id _________________

self = <test_storage.TestEvents object at 0xffff8f189bd0>
db = Database(config=DatabaseConfig(path='/tmp/tmpc_1o6jm8/test.db', journal_mode='wal', busy_timeout_ms=5000))

    @pytest.mark.asyncio
    async def test_event_idempotent_by_event_id(self, db):
>       p = await register_project(db, Project(name="evt-project"))
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/unit/test_storage.py:106: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

db = Database(config=DatabaseConfig(path='/tmp/tmpc_1o6jm8/test.db', journal_mode='wal', busy_timeout_ms=5000))
project = Project(schema_version='1.0', project_id='4bb5f101-0bf5-40fa-8431-e2ca6c5cbeeb', name='evt-project', status=<ProjectStatus.ACTIVE: 'active'>, created_at='2026-11-16T10:10:45.125805Z', updated_at='2026-11-16T10:10:45.125814Z')

    async def register_project(db: Database, project: Project) -> Project:
        now = _utcnow()
>       await db.connection().execute(
              ^^^^^^^^^^^^^^^^^^^^^^^
            "INSERT INTO projects (project_id, name, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (project.project_id, project.name, project.status.value, now, now),
        )
E       AttributeError: '_AsyncGeneratorContextManager' object has no attribute 'execute'

src/agent_memory/storage/repositories/projects.py:18: AttributeError
_________________ TestEvents.test_event_idempotent_by_sequence _________________

self = <test_storage.TestEvents object at 0xffff8f189d10>
db = Database(config=DatabaseConfig(path='/tmp/tmppkhlq46z/test.db', journal_mode='wal', busy_timeout_ms=5000))

    @pytest.mark.asyncio
    async def test_event_idempotent_by_sequence(self, db):
>       p = await register_project(db, Project(name="seq-project"))
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/unit/test_storage.py:129: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

db = Database(config=DatabaseConfig(path='/tmp/tmppkhlq46z/test.db', journal_mode='wal', busy_timeout_ms=5000))
project = Project(schema_version='1.0', project_id='0371f03c-f309-4e79-a847-19b612a41597', name='seq-project', status=<ProjectStatus.ACTIVE: 'active'>, created_at='2026-11-16T10:10:45.145991Z', updated_at='2026-11-16T10:10:45.145999Z')

    async def register_project(db: Database, project: Project) -> Project:
        now = _utcnow()
>       await db.connection().execute(
              ^^^^^^^^^^^^^^^^^^^^^^^
            "INSERT INTO projects (project_id, name, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (project.project_id, project.name, project.status.value, now, now),
        )
E       AttributeError: '_AsyncGeneratorContextManager' object has no attribute 'execute'

src/agent_memory/storage/repositories/projects.py:18: AttributeError
______________________ TestKnowledge.test_create_and_read ______________________

self = <test_storage.TestKnowledge object at 0xffff8f189e50>
db = Database(config=DatabaseConfig(path='/tmp/tmp3m7sts29/test.db', journal_mode='wal', busy_timeout_ms=5000))

    @pytest.mark.asyncio
    async def test_create_and_read(self, db):
>       p = await register_project(db, Project(name="k-project"))
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/unit/test_storage.py:164: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

db = Database(config=DatabaseConfig(path='/tmp/tmp3m7sts29/test.db', journal_mode='wal', busy_timeout_ms=5000))
project = Project(schema_version='1.0', project_id='61384c38-1655-4749-af0f-95cb4bd32385', name='k-project', status=<ProjectStatus.ACTIVE: 'active'>, created_at='2026-11-16T10:10:45.165011Z', updated_at='2026-11-16T10:10:45.165019Z')

    async def register_project(db: Database, project: Project) -> Project:
        now = _utcnow()
>       await db.connection().execute(
              ^^^^^^^^^^^^^^^^^^^^^^^
            "INSERT INTO projects (project_id, name, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (project.project_id, project.name, project.status.value, now, now),
        )
E       AttributeError: '_AsyncGeneratorContextManager' object has no attribute 'execute'

src/agent_memory/storage/repositories/projects.py:18: AttributeError
_____________________ TestKnowledge.test_optimistic_update _____________________

self = <test_storage.TestKnowledge object at 0xffff8f189f90>
db = Database(config=DatabaseConfig(path='/tmp/tmpkrp7uy80/test.db', journal_mode='wal', busy_timeout_ms=5000))

    @pytest.mark.asyncio
    async def test_optimistic_update(self, db):
>       p =

... [truncated, showing 200/236 lines, 7997/13597 chars]
</error>