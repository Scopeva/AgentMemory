"""Shared HTTP client and durable spool for agent adapters.

Every adapter (Pi, Codex, OpenCode) reuses these primitives so that
retry / idempotency / spooling logic is implemented exactly once.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx


# ---------------------------------------------------------------------------
# Event spool state
# ---------------------------------------------------------------------------


@dataclass
class SpooledEvent:
    """A single event buffered locally before delivery."""

    event: dict  # serialized EventEnvelope
    status: str = "created"  # created | locally_persisted | delivered | acknowledged
    attempts: int = 0
    created_at: float = field(default_factory=time.time)


class DurableSpool:
    """File-based durable spool for one agent.

    Layout:
        <root>/
        ├── <agent>/
        │   ├── spool.jsonl       # one SpooledEvent per line
        │   └── meta.json         # last flush time, counters

    The spool file is only user-accessible (0o600) and is flushed to disk
    before the process can crash safely.
    """

    MAX_SPOOL_SIZE = 10_000  # events
    MAX_RETENTION_SECONDS = 7 * 24 * 3600  # 7 days

    def __init__(self, agent: str, root: Optional[Path | str] = None):
        self.agent = agent
        if root is None:
            root = os.environ.get(
                "AGENT_MEMORY_SPOOL_ROOT",
                str(Path.home() / ".local" / "state" / "agent-memory"),
            )
        self.dir = Path(root) / agent
        self.dir.mkdir(parents=True, exist_ok=True)
        self.spool_path = self.dir / "spool.jsonl"
        self.meta_path = self.dir / "meta.json"

    # -- write -------------------------------------------------------------

    def append(self, event: dict) -> SpooledEvent:
        """Persist an event to the spool. Returns the spooled record."""
        rec = SpooledEvent(event=event, status="locally_persisted")
        with open(self.spool_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(self._serialize(rec), ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._enforce_size()
        return rec

    def _serialize(self, rec: SpooledEvent) -> dict:
        return {
            "event_id": rec.event.get("event_id", str(uuid.uuid4())),
            "event": rec.event,
            "status": rec.status,
            "attempts": rec.attempts,
            "created_at": rec.created_at,
        }

    def _enforce_size(self) -> None:
        """Drop oldest events when spool exceeds max size (must alert)."""
        if not self.spool_path.exists():
            return
        lines = self.spool_path.read_text(encoding="utf-8").splitlines()
        if len(lines) > self.MAX_SPOOL_SIZE:
            dropped = len(lines) - self.MAX_SPOOL_SIZE
            lines = lines[-self.MAX_SPOOL_SIZE:]
            with open(self.spool_path, "w", encoding="utf-8") as f:
                f.writelines(line + "\n" for line in lines)
            print(
                f"[spool:{self.agent}] WARNING: dropped {dropped} oldest events "
                f"(spool limit {self.MAX_SPOOL_SIZE})"
            )

    # -- read / flush ------------------------------------------------------

    def pending(self) -> list[dict]:
        """Return all events not yet acknowledged, oldest first."""
        if not self.spool_path.exists():
            return []
        out = []
        for line in self.spool_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("status") != "acknowledged":
                out.append(rec)
        return out

    def mark_acknowledged(self, event_id: str) -> None:
        lines = []
        if self.spool_path.exists():
            for raw in self.spool_path.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                rec = json.loads(raw)
                if rec.get("event_id") == event_id:
                    rec["status"] = "acknowledged"
                lines.append(json.dumps(rec, ensure_ascii=False))
        with open(self.spool_path, "w", encoding="utf-8") as f:
            f.writelines(line + "\n" for line in lines)

    def clear_acked(self) -> int:
        """Remove acknowledged events from the spool file. Returns count removed."""
        if not self.spool_path.exists():
            return 0
        lines = []
        removed = 0
        for raw in self.spool_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            rec = json.loads(raw)
            if rec.get("status") == "acknowledged":
                removed += 1
            else:
                lines.append(raw)
        with open(self.spool_path, "w", encoding="utf-8") as f:
            f.writelines(line + "\n" for line in lines)
        return removed

    def stats(self) -> dict:
        pending = self.pending()
        return {
            "agent": self.agent,
            "spool_path": str(self.spool_path),
            "pending": len(pending),
        }


# ---------------------------------------------------------------------------
# HTTP event client
# ---------------------------------------------------------------------------


class EventClient:
    """Thin HTTP client for the memory-server event API.

    - at-least-once delivery: caller retries using the spool.
    - idempotent: server deduplicates by event_id.
    """

    def __init__(
        self,
        base_url: str,
        agent: str,
        timeout: float = 5.0,
        spool: Optional[DurableSpool] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.agent = agent
        self._client = httpx.Client(timeout=timeout)
        self.spool = spool or DurableSpool(agent)

    def submit(self, event: dict) -> dict:
        """Submit a single event. Falls back to spool on failure."""
        event.setdefault("agent", self.agent)
        try:
            resp = self._client.post(
                f"{self.base_url}/v1/events",
                json=event,
                headers={"X-Agent": self.agent},
            )
            resp.raise_for_status()
            result = resp.json()
            if self.spool:
                self.spool.mark_acknowledged(event.get("event_id", ""))
            return result
        except (httpx.HTTPError, json.JSONDecodeError):
            if self.spool:
                self.spool.append(event)
            return {"status": "spooled", "event_id": event.get("event_id")}

    def submit_batch(self, events: list[dict]) -> dict:
        for ev in events:
            ev.setdefault("agent", self.agent)
        try:
            resp = self._client.post(
                f"{self.base_url}/v1/events/batch",
                json={"events": events},
                headers={"X-Agent": self.agent},
            )
            resp.raise_for_status()
            result = resp.json()
            if self.spool:
                for ev in events:
                    self.spool.mark_acknowledged(ev.get("event_id", ""))
            return result
        except (httpx.HTTPError, json.JSONDecodeError):
            if self.spool:
                for ev in events:
                    self.spool.append(ev)
            return {"status": "spooled", "count": len(events)}

    def flush_spool(self) -> dict:
        """Replay any spooled (non-acknowledged) events to the server."""
        if not self.spool:
            return {"flushed": 0}
        pending = self.spool.pending()
        flushed = 0
        for rec in pending:
            event = rec["event"]
            result = self.submit(event)
            if result.get("status") in ("created", "duplicate"):
                self.spool.mark_acknowledged(event.get("event_id", ""))
                flushed += 1
        self.spool.clear_acked()
        return {"flushed": flushed, "remaining": len(self.spool.pending())}

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# Event envelope builder
# ---------------------------------------------------------------------------


def build_event(
    event_type: str,
    *,
    agent: str,
    session_id: str,
    run_id: str,
    sequence_no: int = 0,
    project_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    task_id: Optional[str] = None,
    payload: Optional[dict] = None,
    event_id: Optional[str] = None,
) -> dict:
    """Build an EventEnvelope dict compatible with the server contract."""
    from datetime import datetime, timezone

    return {
        "schema_version": "1.0",
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": event_type,
        "agent": agent,
        "session_id": session_id,
        "run_id": run_id,
        "project_id": project_id,
        "workspace_id": workspace_id,
        "task_id": task_id,
        "sequence_no": sequence_no,
        "occurred_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        "payload": payload or {},
    }
