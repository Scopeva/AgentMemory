"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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

# Path to the bundled web dashboard (web/ directory in the repo).
_WEB_DIR = Path(__file__).parent.parent.parent / "web"


def _mount_web_ui(app: FastAPI) -> None:
    """Serve the web dashboard at / and /assets/.

    The dashboard is a single-page app built with Vite. index.html is
    served at /; /assets/* is mounted as static files.
    """
    if not _WEB_DIR.is_dir():
        logger.info("web/ directory not found — dashboard disabled")
        return

    # Serve hashed asset files (JS, CSS)
    assets_dir = _WEB_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # Serve index.html at /
    index_path = _WEB_DIR / "index.html"
    if index_path.is_file():

        @app.get("/", include_in_schema=False)
        async def serve_index() -> FileResponse:
            return FileResponse(str(index_path))

# Fallback CORS origins when config.server.cors_origins is empty.
_DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://uevfsysi2ejhbbsjqwegilhsmm0vbqzf.lambda-url.ap-southeast-1.on.aws",
]


def _resolve_cors_origins(config: AppConfig) -> list[str]:
    """Prefer config value (TOML + env); fall back to defaults."""
    if config.server.cors_origins:
        return config.server.cors_origins
    return _DEFAULT_CORS_ORIGINS


def create_app(config: Optional[AppConfig] = None) -> FastAPI:
    """Build the FastAPI app and wire in the Database + retrieval layer."""
    if config is None:
        config = load_config()

    setup_logging()
    db = Database(config.database)
    mcp_app = mcp_server.streamable_http_app(streamable_http_path="/")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # Mounted Starlette applications do not run their own lifespans.
        # The MCP transport needs its task group before it accepts requests.
        async with mcp_app.router.lifespan_context(mcp_app):
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
            # shortcut: assumes one service process; use leased jobs before adding workers.
            recovered = dispatcher.recover_interrupted_jobs()
            if recovered:
                logger.warning("requeued %d interrupted indexing job(s)", recovered)
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

            # Start background indexing loop (drains pending index jobs periodically)
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
            # Close the embedding provider's HTTP client (if any) to avoid leaks
            if embedder is not None and hasattr(embedder, "close"):
                await embedder.close()

    app = FastAPI(
        title="Local Agent Memory & Handoff Service",
        lifespan=lifespan,
    )

    # CORS: allow the web dashboard and local dev server
    cors_origins = _resolve_cors_origins(config)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    app.state.config = config
    app.state.db = db

    # Mount HTTP event channel
    app.include_router(events_api.router, tags=["events"])
    app.include_router(events_api.admin_router, tags=["admin"])
    # Phase 4: retrieval search + knowledge index admin ops
    app.include_router(retrieval_api.router, tags=["retrieval"])
    app.include_router(retrieval_api.admin_router, tags=["retrieval-admin"])
    # Expose the agent-facing tool server through the same loopback-bound
    # process so all supported clients can use one remote MCP configuration.
    app.mount("/mcp", mcp_app, name="agent-memory-mcp")
    # Browser-facing list endpoints for the web dashboard
    from agent_memory.api import browsing as browsing_api

    app.include_router(browsing_api.router, tags=["browsing"])

    # Serve the web dashboard at / (no-op if web/ dir is missing)
    _mount_web_ui(app)

    # The FastAPI and MCP transports share one database and lifecycle.

    return app


def get_mcp_server() -> mcp_server.FastMCP:
    """Return the FastMCP instance for the MCP transport."""
    return mcp_server


def run() -> None:
    """Run the service under uvicorn (used by ``python -m agent_memory.main``)."""
    import uvicorn

    config = load_config()
    app = create_app(config)
    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        log_level="info",
    )


if __name__ == "__main__":
    run()
