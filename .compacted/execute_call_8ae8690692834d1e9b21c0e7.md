<error>
exit_code=1
stderr:
Traceback (most recent call last):
  File "<string>", line 23, in <module>
    asyncio.run(test())
    ~~~~~~~~~~~^^^^^^^^
  File "/usr/local/lib/python3.13/asyncio/runners.py", line 196, in run
    return runner.run(main)
           ~~~~~~~~~~^^^^^^
  File "/usr/local/lib/python3.13/asyncio/runners.py", line 119, in run
    return self._loop.run_until_complete(task)
           ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^
  File "/usr/local/lib/python3.13/asyncio/base_events.py", line 726, in run_until_complete
    return future.result()
           ~~~~~~~~~~~~~^^
  File "<string>", line 17, in test
    p = await repo.projects.register_project(db, Project(name='mcp-test'))
              ^^^^^^^^^^^^^
AttributeError: module 'agent_memory.storage.repositories' has no attribute 'projects'
</error>