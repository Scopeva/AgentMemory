     1	"""FastAPI application factory and ASGI entrypoint."""
     2	
     3	from __future__ import annotations
     4	
     5	import logging
     6	import sqlite3
     7	from contextlib import asynccontextmanager
     8	from typing import AsyncGenerator, Optional
     9	
    10	from fastapi import FastAPI
    11	
    12	from agent_memory.config import AppConfig, load_config
    13	from agent_memory.logging import setup_logging
    14	from agent_memory.api import events as events_api
    15	from agent_memory.mcp.server import mcp as mcp_server, bind_database
    16	from agent_memory.storage.database import Database
    17	from agent_memory.retrieval.embedding import create_provider
    18	from agent_memory.retrieval.search import SearchService
    19	
    20	logger = logging.getLogger(__name__)
    21	
    22	
    23	def create_app(config: Optional[AppConfig] = None) -> FastAPI:
    24	    """Build the FastAPI app and wire in the Database + retrieval layer."""
    25	    if config is None:
    26	        config = load_config()
    27	
    28	    setup_logging()
    29	    db = Database(config.database)
    30	
    31	    @asynccontextmanager
    32	    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    33	        await db.migrate()
    34	        bind_database(db)
    35	        app.state.db = db
    36	
    37	        # Phase 4: build embedding provider + retrieval search service
    38	        embedder = None
    39	        if config.embedding.enabled:
    40	            try:
    41	                embedder = create_provider(config.embedding)
    42	            except Exception as exc:
    43	                logger.warning("Embedding provider unavailable: %s", exc)
    44	
    45	        sync_conn = sqlite3.connect(str(db.path), check_same_thread=False)
    46	        sync_conn.row_factory = sqlite3.Row
    47	        sync_conn.execute("PRAGMA journal_mode = WAL")
    48	        sync_conn.execute("PRAGMA foreign_keys = ON")
    49	
    50	        search_svc = SearchService(
    51	            db=db,
    52	            retrieval_config=config.retrieval,
    53	            embedding_provider=embedder,
    54	            synchronous_conn=sync_conn,
    55	        )
    56	        app.state.search_service = search_svc
    57	        app.state.embedding_provider = embedder
    58	
    59	        # Inject into service layer so MCP + HTTP share the same SearchService
    60	        from agent_memory.services.core import set_search_service
    61	        set_search_service(search_svc)
    62	
    63	        yield
    64	
    65	    app = FastAPI(
    66	        title="Local Agent Memory & Handoff Service",
    67	        lifespan=lifespan,
    68	    )
    69	    app.state.config = config
    70	    app.state.db = db
    71	
    72	    # Mount HTTP event channel
    73	    app.include_router(events_api.router, tags=["events"])
    74	    app.include_router(events_api.admin_router, tags=["admin"])
    75	
    76	    # FastMCP is exposed separately (stdio or streamable-http transport).
    77	    # In this skeleton, the FastAPI app provides the HTTP channel; the MCP
    78	    # server can be run alongside or mounted via the MCP SDK transport.
    79	
    80	    return app
    81	
    82	
    83	def get_mcp_server() -> mcp_server.FastMCP:
    84	    """Return the FastMCP instance for the MCP transport."""
    85	    return mcp_server