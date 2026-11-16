tests/test_memoryctl.py::TestMemoryctlCLI::test_status
  /mnt/workspace/cli/memoryctl/memoryctl.py:115: RuntimeWarning: coroutine 'cmd_status.<locals>._counts' was never awaited
    return 1
  Enable tracemalloc to get traceback where the object was allocated.
  See https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings for more info.

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_memoryctl.py::TestMemoryctlCLI::test_doctor - assert 1 == 0
FAILED tests/test_memoryctl.py::TestMemoryctlCLI::test_status - assert 1 == 0
FAILED tests/test_memoryctl.py::TestMemoryctlCLI::test_projects_register_and_list
FAILED tests/test_memoryctl.py::TestMemoryctlCLI::test_tasks_list_empty - Run...
FAILED tests/test_memoryctl.py::TestMemoryctlCLI::test_pending_list_empty - R...
FAILED tests/test_memoryctl.py::TestMemoryctlCLI::test_handoffs_latest_not_found
FAILED tests/test_memoryctl.py::TestMemoryctlCLI::test_backup_create_and_verify
=================== 7 failed, 3 passed, 2 warnings in 0.32s ====================
/mnt/workspace/.venv/lib/python3.13/site-packages/_pytest/unraisableexception.py:29: RuntimeWarning: coroutine 'cmd_projects_register.<locals>._register' was never awaited
  gc.collect()
RuntimeWarning: Enable tracemalloc to get the object allocation traceback
/mnt/workspace/.venv/lib/python3.13/site-packages/_pytest/unraisableexception.py:29: RuntimeWarning: coroutine 'cmd_tasks_list.<locals>._tasks' was never awaited
  gc.collect()
RuntimeWarning: Enable tracemalloc to get the object allocation traceback
/mnt/workspace/.venv/lib/python3.13/site-packages/_pytest/unraisableexception.py:29: RuntimeWarning: coroutine 'cmd_pending_list.<locals>._pending' was never awaited
  gc.collect()
RuntimeWarning: Enable tracemalloc to get the object allocation traceback
/mnt/workspace/.venv/lib/python3.13/site-packages/_pytest/unraisableexception.py:29: RuntimeWarning: coroutine 'cmd_handoffs_latest.<locals>._latest' was never awaited
  gc.collect()
RuntimeWarning: Enable tracemalloc to get the object allocation traceback
<sys>:0: RuntimeWarning: coroutine 'cmd_backup_create.<locals>._create' was never awaited