     1	"""memoryctl CLI tests: run subcommands against a fresh DB."""
     2	
     3	from __future__ import annotations
     4	
     5	import importlib.util
     6	import os
     7	import sys
     8	import tempfile
     9	from pathlib import Path
    10	
    11	import pytest
    12	import pytest_asyncio
    13	
    14	# Load memoryctl module directly from the file path (avoids package name issues).
    15	_CLI_DIR = Path(__file__).parent.parent / "cli"
    16	_spec = importlib.util.spec_from_file_location(
    17	    "memoryctl", _CLI_DIR / "memoryctl" / "memoryctl.py"
    18	)
    19	_memoryctl = importlib.util.module_from_spec(_spec)
    20	_spec.loader.exec_module(_memoryctl)
    21	main = _memoryctl.main
    22	
    23	
    24	@pytest_asyncio.fixture
    25	async def db_env(tmp_path: Path):
    26	    """Set up a migrated DB and env vars pointing at it."""
    27	    from agent_memory.config import DatabaseConfig
    28	    from agent_memory.storage.database import Database
    29	
    30	    db_path = tmp_path / "memory.db"
    31	    db = Database(DatabaseConfig(path=str(db_path)))
    32	    await db.migrate()
    33	    os.environ["AGENT_MEMORY_DATABASE_PATH"] = str(db_path)
    34	    os.environ["AGENT_MEMORY_CONFIG_PATH"] = ""
    35	    return str(db_path)
    36	
    37	
    38	class TestMemoryctlCLI:
    39	    @pytest.mark.asyncio
    40	    async def test_doctor(self, db_env: str):
    41	        rc = main(["doctor"])
    42	        assert rc == 0
    43	
    44	    @pytest.mark.asyncio
    45	    async def test_status(self, db_env: str):
    46	        rc = main(["status"])
    47	        assert rc == 0
    48	
    49	    @pytest.mark.asyncio
    50	    async def test_projects_register_and_list(self, db_env: str):
    51	        rc = main(["projects", "register", "--name", "cli-test-proj"])
    52	        assert rc == 0
    53	        rc = main(["projects", "list"])
    54	        assert rc == 0
    55	
    56	    @pytest.mark.asyncio
    57	    async def test_tasks_list_empty(self, db_env: str):
    58	        rc = main(["tasks", "list"])
    59	        assert rc == 0
    60	
    61	    @pytest.mark.asyncio
    62	    async def test_pending_list_empty(self, db_env: str):
    63	        rc = main(["pending", "list"])
    64	        assert rc == 0
    65	
    66	    @pytest.mark.asyncio
    67	    async def test_handoffs_latest_not_found(self, db_env: str):
    68	        rc = main(["handoffs", "latest"])
    69	        assert rc == 1  # not found
    70	
    71	    @pytest.mark.asyncio
    72	    async def test_index_status(self, db_env: str):
    73	        rc = main(["index", "status"])
    74	        assert rc == 0
    75	
    76	    @pytest.mark.asyncio
    77	    async def test_index_rebuild_not_implemented(self, db_env: str):
    78	        rc = main(["index", "rebuild"])
    79	        assert rc == 1
    80	
    81	    @pytest.mark.asyncio
    82	    async def test_jobs_retry_not_implemented(self, db_env: str):
    83	        rc = main(["jobs", "retry"])
    84	        assert rc == 1
    85	
    86	    @pytest.mark.asyncio
    87	    async def test_backup_create_and_verify(self, db_env: str, tmp_path: Path):
    88	        backup = str(tmp_path / "backup.db")
    89	        rc = main(["backup", "create", "--target", backup])
    90	        assert rc == 0
    91	        assert Path(backup).exists()
    92	        rc = main(["backup", "verify", "--target", backup])
    93	        assert rc == 0