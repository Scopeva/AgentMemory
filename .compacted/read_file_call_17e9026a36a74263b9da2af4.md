     1	"""FastAPI application factory and ASGI entrypoint."""
     2	
     3	from __future__ import annotations
     4	
     5	from contextlib import asynccontextmanager
     6	from typing import AsyncGenerator, Optional
     7	
     8	from fastapi import FastAPI
     9	
    10	from agent_memory.config import AppConfig, load_config
    11	from agent_memory.logging import setup_logging
    12	from agent_memory.api import events as events_api
    13	from agent_memory.mcp.server import mcp as mcp_server, bind_database
    14	from agent_memory.storage.database import Database
    15	
    16	
    17	def create_app(config: Optional[AppConfig] = None) -> FastAPI:
    18	    """Build the FastAPI app and wire in the Database dependency."""
    19	    if config is None:
    20	        config = load_config()
    21	
    22	    setup_logging()
    23	    db = Database(config.database)
    24	
    25	    @asynccontextmanager
    26	    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    27	        await db.migrate()
    28	        bind_database(db)
    29	        app.state.db = db
    30	        yield
    31	
    32	    app = FastAPI(
    33	        title="Local Agent Memory & Handoff Service",
    34	        lifespan=lifespan,
    35	    )
    36	    app.state.config = config
    37	    app.state.db = db
    38	
    39	    # Mount HTTP event channel
    40	    app.include_router(events_api.router, tags=["events"])
    41	    app.include_router(events_api.admin_router, tags=["admin"])
    42	
    43	    # FastMCP is exposed separately (stdio or streamable-http transport).
    44	    # In this skeleton, the FastAPI app provides the HTTP channel; the MCP
    45	    # server can be run alongside or mounted via the MCP SDK transport.
    46	    # See main.py for how to combine both.
    47	
    48	    return app
    49	
    50	
    51	def get_mcp_server() -> mcp_server.FastMCP:
    52	    """Return the FastMCP instance for the MCP transport."""
    53	    return mcp_server