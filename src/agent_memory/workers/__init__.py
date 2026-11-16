"""Background worker loops for the agent-memory service.

Currently provides:
- BackgroundIndexingLoop: periodic JobDispatcher drain
"""

from agent_memory.workers.indexing_loop import BackgroundIndexingLoop

__all__ = ["BackgroundIndexingLoop"]
