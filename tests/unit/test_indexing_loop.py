"""Unit tests for BackgroundIndexingLoop."""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import pytest

from agent_memory.workers import BackgroundIndexingLoop


class _StubDispatcher:
    """Minimal dispatcher stub with controllable pending/drain behavior."""

    def __init__(self):
        self.pending = 0
        self.drained: list[dict] = []
        self.drain_sleep: float = 0.0
        self._stop_wait: Optional[asyncio.Event] = None

    def pending_count(self) -> int:
        return self.pending

    async def drain(self, batch_size: Optional[int] = None) -> dict:
        if self.drain_sleep:
            await asyncio.sleep(self.drain_sleep)
        result = {"completed": self.pending, "failed": 0, "skipped": 0, "total": self.pending}
        self.drained.append(result)
        self.pending = 0
        return result

    def reset(self):
        self.pending = 0
        self.drained.clear()


@pytest.mark.asyncio
async def test_loop_stops_cleanly_with_no_work():
    stub = _StubDispatcher()
    loop = BackgroundIndexingLoop(stub, interval_seconds=0.05, empty_backoff_seconds=0.1)
    loop.start()
    await asyncio.sleep(0.15)
    await loop.stop()
    assert loop.cycles == 0
    assert not loop._task  # task cleared


@pytest.mark.asyncio
async def test_loop_drains_pending_jobs():
    stub = _StubDispatcher()
    stub.pending = 3
    loop = BackgroundIndexingLoop(stub, interval_seconds=0.05, empty_backoff_seconds=0.1)
    loop.start()
    await asyncio.sleep(0.15)
    await loop.stop()
    assert len(stub.drained) >= 1
    total_completed = sum(r["completed"] for r in stub.drained)
    assert total_completed == 3


@pytest.mark.asyncio
async def test_loop_processes_multiple_cycles():
    stub = _StubDispatcher()
    loop = BackgroundIndexingLoop(stub, interval_seconds=0.05, empty_backoff_seconds=0.1)
    loop.start()

    # Feed one batch; the first loop cycle drains it.
    stub.pending = 2
    await asyncio.sleep(0.1)

    # By now the queue is empty (drain resets pending). The next cycle
    # after empty backoff picks up a second batch.
    stub.pending = 3
    await asyncio.sleep(0.25)

    await loop.stop()
    assert loop.cycles >= 2
    total_completed = sum(r["completed"] for r in stub.drained)
    assert total_completed == 5  # 2 + 3


@pytest.mark.asyncio
async def test_stop_is_idempotent():
    stub = _StubDispatcher()
    loop = BackgroundIndexingLoop(stub, interval_seconds=0.05)
    loop.start()
    await loop.stop()
    # Second stop should be a no-op, not raise
    await loop.stop()
    assert loop._task is None


@pytest.mark.asyncio
async def test_last_result_reflects_most_recent_drain():
    stub = _StubDispatcher()
    stub.pending = 5
    loop = BackgroundIndexingLoop(stub, interval_seconds=0.05)
    loop.start()
    await asyncio.sleep(0.12)
    await loop.stop()
    assert loop.last_result.get("completed") == 5
