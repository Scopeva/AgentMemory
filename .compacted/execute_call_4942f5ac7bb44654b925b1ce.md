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
---PI ADAPTER REST---
    memories: list[dict] = field(default_factory=list)


class MemoryCaptureController:
    """Decides when Pi may be asked to produce one structured extraction."""

    def __init__(self, guard: RunGuard):
        self._guard = guard

    def should_request_extraction(
        self,
        run_id: str,
        outcome: str,
        *,
        had_code_changes: bool = False,
        task_significant: bool = False,
    ) -> bool:
        """Return True only if:
        - the guard allows it (no recursion, not already attempted)
        - the outcome warrants it (completed/failed with code changes or task significance)
        """
        if not self._guard.allow_extraction(run_id):
            return False
        if outcome not in ("completed", "failed", "interrupted"):
            return False
        # Skip trivial runs with no code changes and no task significance
        if outcome == "completed" and not had_code_changes and not task_significant:
            return False
        return True

    def mark_attempted(self, run_id: str) -> None:
        self._guard.mark_extraction_attempted(run_id)
        self._guard.mark_extraction_origin(run_id)

    def on_run_end(self, run_id: str) -> None:
        self._guard.reset(run_id)


# ---------------------------------------------------------------------------
# Session observer (passive event recorder)
# ---------------------------------------------------------------------------


class SessionObserver:
    """Records Pi lifecycle events to the EventClient + spool.

    All methods are synchronous for easy integration with Pi's CLI hooks.
    """

    def __init__(self, client: EventClient, config: PiAdapterConfig):
        self._client = client
        self._config = config
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _cfg_kwargs(self) -> dict:
        return {
            "project_id": self._config.project_id,
            "workspace_id": self._config.workspace_id,
            "task_id": self._config.task_id,
        }

    # -- lifecycle hooks ----------------------------------------------------

    def on_session_start(self, session_id: str, native_session_id: str = "") -> None:
        evt = build_event(
            "session.start",
            agent=self._config.agent,
            session_id=session_id,
            run_id=session_id,  # session.start has no run yet
            sequence_no=self._next_seq(),
            payload={"native_session_id": native_session_id},
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    def on_run_started(self, run_id: str, session_id: str, head_sha: str = "") -> None:
        evt = build_event(
            "run.started",
            agent=self._config.agent,
            session_id=session_id,
            run_id=run_id,
            sequence_no=self._next_seq(),
            payload={"head_sha_start": head_sha},
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    def on_turn_end(self, run_id: str, session_id: str, turn_index: int) -> None:
        evt = build_event(
            "turn.end",
            agent=self._config.agent,
            session_id=session_id,
            run_id=run_id,
            sequence_no=self._next_seq(),
            payload={"turn_index": turn_index},
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    def on_session_before_compact(self, run_id: str, session_id: str, summary: str = "") -> None:
        evt = build_event(
            "session.compacted",
            agent=self._config.agent,
            session_id=session_id,
            run_id=run_id,
            sequence_no=self._next_seq(),
            payload={"pre_compact_summary": summary},
            **self._cfg_kwargs(),
        )
        self._client.submit(evt)

    def on_run_settled(
        self,
        run_id: str,
        session_id: str,
        outcome: str,
        *,
        head_sha_end: str = "",
        payload_extra: Optional[dict] = None,
    ) -> None:
        payload = {"outcome": outcome, "head_sha_end": head_sha_end}
        if payload_extra:
            payload.update(payload_extra)

... [truncated, showing 200/274 lines, 6654/9012 chars]