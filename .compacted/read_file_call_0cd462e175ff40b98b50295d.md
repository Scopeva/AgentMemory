     1	"""Service-layer wrappers for knowledge governance operations.
     2	
     3	Both MCP tools and HTTP admin endpoints call these functions.
     4	"""
     5	
     6	from __future__ import annotations
     7	
     8	from typing import Optional
     9	
    10	from agent_memory.schemas import KnowledgeStatus
    11	from agent_memory.storage import repositories as repo
    12	from agent_memory.storage.database import Database
    13	from agent_memory.core.knowledge_governance import (
    14	    approve_and_supersede as _gov_approve_and_supersede,
    15	    archive_knowledge as _gov_archive,
    16	    reject_knowledge as _gov_reject,
    17	    find_superseded as _gov_find_superseded,
    18	    find_duplicates as _gov_find_duplicates,
    19	    list_stale_knowledge as _gov_list_stale,
    20	    governance_summary as _gov_summary,
    21	)
    22	
    23	
    24	async def governance_summary(
    25	    db: Database,
    26	    project_id: str,
    27	    max_age_days: int = 30,
    28	) -> dict:
    29	    """Aggregate governance metrics for a project."""
    30	    return await _gov_summary(db, project_id, max_age_days=max_age_days)
    31	
    32	
    33	async def find_superseded(
    34	    db: Database,
    35	    project_id: str,
    36	    content_threshold: float = 0.85,
    37	    limit: int = 50,
    38	) -> list[dict]:
    39	    """Find accepted knowledge items that may have been superseded."""
    40	    return await _gov_find_superseded(db, project_id, content_threshold, limit)
    41	
    42	
    43	async def find_duplicates(
    44	    db: Database,
    45	    project_id: str,
    46	    title_threshold: float = 0.90,
    47	    content_threshold: float = 0.80,
    48	    limit: int = 50,
    49	) -> list[dict]:
    50	    """Find duplicated knowledge items."""
    51	    return await _gov_find_duplicates(
    52	        db, project_id, title_threshold, content_threshold, limit
    53	    )
    54	
    55	
    56	async def list_stale_knowledge(
    57	    db: Database,
    58	    project_id: str,
    59	    max_age_days: int = 30,
    60	    limit: int = 50,
    61	) -> list[dict]:
    62	    """List accepted knowledge items not updated within max_age_days."""
    63	    return await _gov_list_stale(db, project_id, max_age_days, limit)
    64	
    65	
    66	async def approve_and_supersede(
    67	    db: Database,
    68	    new_memory_id: str,
    69	    old_memory_id: str,
    70	    decided_by: str = "agent",
    71	    reason: str = "",
    72	) -> dict:
    73	    """Mark old_memory_id superseded by new_memory_id."""
    74	    return await _gov_approve_and_supersede(db, new_memory_id, old_memory_id, decided_by, reason)
    75	
    76	
    77	async def archive_knowledge(
    78	    db: Database,
    79	    memory_id: str,
    80	    decided_by: str = "agent",
    81	    reason: str = "",
    82	) -> dict:
    83	    """Archive a knowledge item."""
    84	    return await _gov_archive(db, memory_id, decided_by, reason)
    85	
    86	
    87	async def reject_knowledge(
    88	    db: Database,
    89	    memory_id: str,
    90	    decided_by: str = "agent",
    91	    reason: str = "",
    92	) -> dict:
    93	    """Reject a knowledge item."""
    94	    return await _gov_reject(db, memory_id, decided_by, reason)