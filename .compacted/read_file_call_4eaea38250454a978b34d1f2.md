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
    18	from agent_memory.retrieval.indexing import IndexingWorker
    19	from agent_memory.retrieval.dispatcher import JobDispatcher
    20	from agent_memory.retrieval.search import SearchService
    21	
    22	logger = logging.getLogger(__name__)
    23	
    24	
    25	def create_app(config: Optional[AppConfig] = None) -> FastAPI:
    26	    """Build the FastAPI app and wire in the Database + retrieval layer."""
    27	    if config is None:
    28	        config = load_config()
    29	
    30	    setup_logging()
    31	    db = Database(config.database)
    32	
    33	    @asynccontextmanager
    34	    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    35	        await db.migrate()
    36	        bind_database(db)
    37	        app.state.db = db
    38	
    39	        # Phase 4: build embedding provider + retrieval search service
    40	        embedder = None
    41	        if config.embedding.enabled:
    42	            try:
    43	                embedder = create_provider(config.embedding)
    44	            except Exception as exc:
    45	                logger.warning("Embedding provider unavailable: %s", exc)
    46	
    47	        sync_conn = sqlite3.connect(str(db.path), check_same_thread=False)
    48	        sync_conn.row_factory = sqlite3.Row
    49	        sync_conn.execute("PRAGMA journal_mode = WAL")
    50	        sync_conn.execute("PRAGMA foreign_keys = ON")
    51	
    52	        search_svc = SearchService(
    53	            db=db,
    54	            retrieval_config=config.retrieval,
    55	            embedding_provider=embedder,
    56	            synchronous_conn=sync_conn,
    57	        )
    58	        app.state.search_service = search_svc
    59	        app.state.embedding_provider = embedder
    60	
    61	        # Inject into service layer so MCP + HTTP share the same SearchService
    62	        from agent_memory.services.core import set_search_service
    63	        set_search_service(search_svc)
    64	
    65	        yield
    66	
    67	    app = FastAPI(
    68	        title="Local Agent Memory & Handoff Service",
    69	        lifespan=lifespan,
    70	    )
    71	    app.state.config = config
    72	    app.state.db = db
    73	
    74	    # Mount HTTP event channel
    75	    app.include_router(events_api.router, tags=["events"])
    76	    app.include_router(events_api.admin_router, tags=["admin"])
    77	
    78	    # FastMCP is exposed separately (stdio or streamable-http transport).
    79	    # In this skeleton, the FastAPI app provides the HTTP channel; the MCP
    80	    # server can be run alongside or mounted via the MCP SDK transport.
    81	
    82	    return app
    83	
    84	
    85	def get_mcp_server() -> mcp_server.FastMCP:
    86	    """Return the FastMCP instance for the MCP transport."""
    87	    return mcp_server