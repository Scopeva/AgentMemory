"""Background indexing loop: periodically drain pending index jobs.

Runs as an asyncio task in the FastAPI lifespan. Each cycle calls
JobDispatcher.drain() with a configurable batch size. When no pending
jobs exist the loop sleeps between cycles; when work is available it
drains again immediately (bounded by a small backoff).

The loop is safe to stop at any time: an asyncio.Event is set on
shutdown, and any in-flight drain completes before the task exits.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class BackgroundIndexingLoop:
    """Drain pending index jobs on a fixed interval.

    Args:
        dispatcher: A JobDispatcher instance (Phase 4 retrieval).
        interval_seconds: Base sleep between drain cycles.
        batch_size: Max jobs per drain call; None uses dispatcher default.
        stop_on_empty: When True, sleep longer when no pending work.
        empty_backoff_seconds: Sleep duration when queue is empty.
    """

    def __init__(
        self,
        dispatcher,
        interval_seconds: float = 30.0,
        batch_size: Optional[int] = None,
        empty_backoff_seconds: float = 120.0,
    ):
        self._dispatcher = dispatcher
        self._interval = interval_seconds
        self._batch_size = batch_size
        self._empty_backoff = empty_backoff_seconds
        self._stop_event: Optional[asyncio.Event] = None
        self._task: Optional[asyncio.Task] = None
        self._last_result: dict = {}
        self._cycles = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background task. Must be called inside a running event loop."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="bg-indexing-loop")
        logger.info(
            "background indexing loop started (interval=%ss, empty_backoff=%ss)",
            self._interval,
            self._empty_backoff,
        )

    async def stop(self) -> None:
        """Signal stop and wait for the task to finish."""
        if self._stop_event is None:
            return
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.warning("background indexing loop did not stop cleanly; cancelling")
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    pass
            self._task = None
        logger.info("background indexing loop stopped (cycles=%d)", self._cycles)

    @property
    def last_result(self) -> dict:
        return dict(self._last_result)

    @property
    def cycles(self) -> int:
        return self._cycles

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            pending = self._dispatcher.pending_count()
            if pending > 0:
                try:
                    result = await self._dispatcher.drain(batch_size=self._batch_size)
                    self._last_result = result
                    self._cycles += 1
                    if result.get("failed"):
                        logger.warning(
                            "index drain: %d completed, %d failed",
                            result.get("completed", 0),
                            result.get("failed", 0),
                        )
                    else:
                        logger.debug(
                            "index drain: %d completed, %d skipped",
                            result.get("completed", 0),
                            result.get("skipped", 0),
                        )
                except Exception:
                    logger.exception("index drain cycle failed")
                sleep_seconds = self._interval
            else:
                sleep_seconds = self._empty_backoff
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_seconds)
            except asyncio.TimeoutError:
                pass
