/src/agent_memory/services/core.py:31:class ProjectUnresolvedError(Exception):
/src/agent_memory/services/core.py:35:class TaskConflictServiceError(Exception):
/src/agent_memory/services/core.py:39:class VersionConflictServiceError(Exception):
/src/agent_memory/services/core.py:48:async def resolve_project(
/src/agent_memory/services/core.py:117:async def get_project_context(
/src/agent_memory/services/core.py:196:async def get_task_state(
/src/agent_memory/services/core.py:228:async def create_handoff(db: Database, handoff: Handoff) -> Handoff:
/src/agent_memory/services/core.py:233:async def get_latest_handoff(
/src/agent_memory/services/core.py:242:async def update_task_state(
/src/agent_memory/services/core.py:267:async def submit_memory_candidate(
/src/agent_memory/services/core.py:293:async def get_memory(db: Database, memory_id: str, include_revisions: bool = True) -> Optional[dict]:
/src/agent_memory/services/core.py:303:async def submit_event(db: Database, event: EventEnvelope) -> dict:
/src/agent_memory/services/core.py:315:async def submit_events_batch(db: Database, events: list[EventEnvelope]) -> dict:
/src/agent_memory/services/core.py:328:async def submit_checkpoint(db: Database, checkpoint: Checkpoint) -> Checkpoint:
/src/agent_memory/services/core.py:338:async def search_memory(