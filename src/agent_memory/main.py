"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI

from agent_memory.config import AppConfig, load_config
from agent_memory.logging import setup_logging
from agent_memory.api import events as events_api
from agent_memory.api import retrieval as retrieval_api
from agent_memory.mcp.server import mcp as mcp_server, bind_database
from agent_memory.storage.database import Database
from agent_memory.retrieval.embedding import create_provider
from agent_memory.retrieval.indexing import IndexingWorker
from agent_memory.retrieval.dispatcher import JobDispatcher
from agent_memory.retrieval.search import SearchService
from agent_memory.workers import BackgroundIndexingLoop

logger = logging.getLogger(__name__)


def create_app(config: Optional[AppConfig] = None) -> FastAPI:
    """Build the FastAPI app and wire in the Database + retrieval layer."""
    if config is None:
        config = load_config()

    setup_logging()
    db = Database(config.database)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        await db.migrate()
        bind_database(db)
        app.state.db = db

        # Phase 4: build embedding provider + retrieval search service
        embedder = None
        if config.embedding.enabled:
            try:
                embedder = create_provider(config.embedding)
            except Exception as exc:
                logger.warning("Embedding provider unavailable: %s", exc)

        sync_conn = sqlite3.connect(str(db.path), check_same_thread=False)
        sync_conn.row_factory = sqlite3.Row
        sync_conn.execute("PRAGMA journal_mode = WAL")
        sync_conn.execute("PRAGMA foreign_keys = ON")

        # Phase 4: indexing worker + job dispatcher
        worker = IndexingWorker(sync_conn, config.retrieval, embedder)
        dispatcher = JobDispatcher(db, worker, config.retrieval, sync_conn)
        app.state.indexing_worker = worker
        app.state.job_dispatcher = dispatcher

        search_svc = SearchService(
            db=db,
            retrieval_config=config.retrieval,
            embedding_provider=embedder,
            synchronous_conn=sync_conn,
        )
        app.state.search_service = search_svc
        app.state.embedding_provider = embedder

        # Inject into service layer so MCP + HTTP share the same services
        from agent_memory.services.core import set_search_service, set_job_dispatcher
        set_search_service(search_svc)
        set_job_dispatcher(dispatcher)

        # Start background indexing loop (drains pending jobs periodically)
        bg_loop = BackgroundIndexingLoop(
            dispatcher=dispatcher,
            interval_seconds=config.workers.interval_seconds,
            empty_backoff_seconds=config.workers.empty_backoff_seconds,
        )
        bg_loop.start()
        app.state.bg_indexing_loop = bg_loop

        yield

        # Stop the background loop cleanly on shutdown
        await bg_loop.stop()
        sync_conn.close()

    app = FastAPI(
        title="Local Agent Memory & Handoff Service",
        lifespan=lifespan,
    )
    app.state.config = config
    app.state.db = db

    # Mount HTTP event channel
    app.include_router(events_api.router, tags=["events"])
    app.include_router(events_api.admin_router, tags=["admin"])
    # Phase 4: retrieval search + knowledge index admin ops
    app.include_router(retrieval_api.router, tags=["retrieval"])
    app.include_router(retrieval_api.admin_router, tags=["retrieval-admin"])

    # FastMCP is exposed separately (stdio or streamable-http transport).
    # In this skeleton, the FastAPI app provides the HTTP channel; the MCP
    # server can be run alongside or mounted via the MCP SDK transport.

    return app


def get_mcp_server() -> mcp_server.FastMCP:
    """Return the FastMCP instance for the MCP transport."""
    return mcp_server
