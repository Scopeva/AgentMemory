     1	"""FastMCP tool definitions for the 9 agent-facing MCP operations.
     2	
     3	Uses the mcp 2.x SDK (MCPServer). Each tool is a function decorated with
     4	``@mcp.tool()`` that returns a JSON-serializable dict.
     5	"""
     6	
     7	from __future__ import annotations
     8	
     9	from typing import Optional
    10	
    11	from mcp.server.mcpserver import MCPServer
    12	
    13	from agent_memory.services import core
    14	from agent_memory.schemas import Handoff
    15	from agent_memory.storage.database import Database
    16	
    17	mcp = MCPServer("agent-memory")
    18	
    19	# The Database instance is injected at startup; tools access it via closure.
    20	_db: Optional[Database] = None
    21	
    22	
    23	def bind_database(db: Database) -> None:
    24	    global _db
    25	    _db = db
    26	
    27	
    28	def get_db() -> Database:
    29	    if _db is None:
    30	        raise RuntimeError("Database not initialized; call bind_database() first")
    31	    return _db
    32	
    33	
    34	# ---------------------------------------------------------------------------
    35	# 1. resolve_project
    36	# ---------------------------------------------------------------------------
    37	
    38	
    39	@mcp.tool()
    40	async def resolve_project(
    41	    workspace: Optional[str] = None,
    42	    project_id: Optional[str] = None,
    43	) -> dict:
    44	    """Identify project identity from a workspace path or explicit project ID.
    45	
    46	    Returns project, workspace, repository identity and resolution status.
    47	    """
    48	    db = get_db()
    49	    return await core.resolve_project(db, workspace_path=workspace, project_id=project_id)
    50	
    51	
    52	# ---------------------------------------------------------------------------
    53	# 2. get_project_context
    54	# ---------------------------------------------------------------------------
    55	
    56	
    57	@mcp.tool()
    58	async def get_project_context(
    59	    project_id: str,
    60	    task_id: Optional[str] = None,
    61	    include: Optional[list[str]] = None,
    62	    max_output_tokens: int = 2000,
    63	) -> dict:
    64	    """Return compact project background sections within a token budget.
    65	
    66	    Sections: project_summary, active_tasks, recent_handoffs,
    67	    accepted_constraints.
    68	    """
    69	    db = get_db()
    70	    return await core.get_project_context(
    71	        db,
    72	        project_id,
    73	        task_id=task_id,
    74	        include=include,
    75	        max_output_tokens=max_output_tokens,
    76	    )
    77	
    78	
    79	# ---------------------------------------------------------------------------
    80	# 3. search_memory
    81	# ---------------------------------------------------------------------------
    82	
    83	
    84	@mcp.tool()
    85	async def search_memory(
    86	    project_id: str,
    87	    query: str,
    88	    filters: Optional[dict] = None,
    89	    limit: int = 8,
    90	) -> dict:
    91	    """Search project knowledge. Phase 2 uses lexical matching;
    92	    Phase 4 upgrades to FTS5 + sqlite-vec hybrid RRF.
    93	    """
    94	    db = get_db()
    95	    return await core.search_memory(db, project_id, query, limit=limit, filters=filters)
    96	
    97	
    98	# ---------------------------------------------------------------------------
    99	# 4. get_memory
   100	# ---------------------------------------------------------------------------
   101	
   102	
   103	@mcp.tool()
   104	async def get_memory(memory_id: str) -> Optional[dict]:
   105	    """Fetch a specific knowledge item with its revision history and evidence."""
   106	    db = get_db()
   107	    return await core.get_memory(db, memory_id, include_revisions=True)
   108	
   109	
   110	# ---------------------------------------------------------------------------
   111	# 5. get_task_state
   112	# ---------------------------------------------------------------------------
   113	
   114	
   115	@mcp.tool()
   116	async def get_task_state(
   117	    task_id: Optional[str] = None,
   118	    project_id: Optional[str] = None,
   119	) -> dict:
   120	    """Get task status, latest handoff, and recent events.
   121	
   122	    Provide task_id for a specific task, or project_id to get the
   123	    most recently active task in that project.
   124	    """
   125	    db = get_db()
   126	    return await core.get_task_state(db, task_id=task_id, project_id=project_id)
   127	
   128	
   129	# ---------------------------------------------------------------------------
   130	# 6. get_latest_handoff
   131	# ---------------------------------------------------------------------------
   132	
   133	
   134	@mcp.tool()
   135	async def get_latest_handoff(
   136	    task_id: Optional[str] = None,
   137	    workspace_id: Optional[str] = None,
   138	) -> Optional[dict]:
   139	    """Get the most recent valid handoff for a task or workspace.
   140	
   141	    If HEAD SHA has advanced, the handoff may be stale; the caller should
   142	    verify compatibility before continuing.
   143	    """
   144	    db = get_db()
   145	    handoff = await core.get_latest_handoff(db, task_id=task_id, workspace_id=workspace_id)
   146	    if handoff is None:
   147	        return None
   148	    return {
   149	        "handoff": handoff.model_dump(),
   150	        "is_stale": False,
   151	        "needs_revalidation": bool(handoff.source_head_sha),
   152	    }
   153	
   154	
   155	# ---------------------------------------------------------------------------
   156	# 7. create_handoff
   157	# ---------------------------------------------------------------------------
   158	
   159	
   160	@mcp.tool()
   161	async def create_handoff(
   162	    task_id: str,
   163	    summary: str,
   164	    completed: Optional[list[str]] = None,
   165	    pending: Optional[list[str]] = None,
   166	    blockers: Optional[list[str]] = None,
   167	    decisions: Optional[list[str]] = None,
   168	    verification_refs: Optional[list[str]] = None,
   169	    next_actions: Optional[list[str]] = None,
   170	    source_agent: str = "unknown",
   171	    source_session_id: Optional[str] = None,
   172	    source_run_id: Optional[str] = None,
   173	    source_workspace_id: Optional[str] = None,
   174	    source_head_sha: Optional[str] = None,
   175	) -> dict:
   176	    """Submit a new handoff record for a task. Increments revision.
   177	
   178	    The receiving agent should read this before starting work.
   179	    """
   180	    db = get_db()
   181	    h = Handoff(
   182	        task_id=task_id,
   183	        source_agent=source_agent,
   184	        source_session_id=source_session_id,
   185	        source_run_id=source_run_id,
   186	        source_workspace_id=source_workspace_id,
   187	        source_head_sha=source_head_sha,
   188	        summary=summary,
   189	        completed=completed or [],
   190	        pending=pending or [],
   191	        blockers=blockers or [],
   192	        decisions=decisions or [],
   193	        verification_refs=verification_refs or [],
   194	        next_actions=next_actions or [],
   195	    )
   196	    result = await core.create_handoff(db, h)
   197	    return {
   198	        "handoff_id": result.handoff_id,
   199	        "revision": result.revision,
   200	        "task_id": task_id,

... [truncated, showing 200/256 lines, 7451/9318 chars]