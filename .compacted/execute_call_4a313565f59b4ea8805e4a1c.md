<error>
exit_code=1
stderr:
Traceback (most recent call last):
  File "<string>", line 2, in <module>
    from agent_memory.main import create_app
  File "/mnt/workspace/src/agent_memory/main.py", line 12, in <module>
    from agent_memory.api import events as events_api
  File "/mnt/workspace/src/agent_memory/api/events.py", line 15, in <module>
    from agent_memory.services import core
  File "/mnt/workspace/src/agent_memory/services/__init__.py", line 7, in <module>
    from agent_memory.services.core import (  # noqa: F401
    ...<15 lines>...
    )
ImportError: cannot import name 'list_pending_candidates' from 'agent_memory.services.core' (/mnt/workspace/src/agent_memory/services/core.py)
</error>