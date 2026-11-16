"""Package marker for the services subpackage.

The root `agent_memory.services` module previously exposed `ServiceContext`;
the service layer implementations now live in `agent_memory.services.core`.
"""

from agent_memory.services.core import (  # noqa: F401
    get_latest_handoff,
    get_memory,
    get_project_context,
    get_task_state,
    list_pending_candidates,
    create_handoff,
    reject_candidate,
    resolve_project,
    approve_candidate,
    search_memory,
    submit_checkpoint,
    submit_event,
    submit_events_batch,
    submit_memory_candidate,
    update_task_state,
)
