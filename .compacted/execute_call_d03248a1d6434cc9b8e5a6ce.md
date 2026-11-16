215:    def on_run_settled(
216-        self,
217-        run_id: str,
218-        session_id: str,
219-        outcome: str,
220-        *,
221-        head_sha_end: str = "",
222-        payload_extra: Optional[dict] = None,
223-    ) -> None:
224-        payload = {"outcome": outcome, "head_sha_end": head_sha_end}
225-        if payload_extra:
226-            payload.update(payload_extra)
227-        evt = build_event(
228-            "run.settled",
229-            agent=self._config.agent,
230-            session_id=session_id,
--
238:    def on_run_interrupted(self, run_id: str, session_id: str, reason: str = "") -> None:
239-        evt = build_event(
240-            "run.interrupted",
241-            agent=self._config.agent,
242-            session_id=session_id,
243-            run_id=run_id,
244-            sequence_no=self._next_seq(),
245-            payload={"reason": reason},
246-            **self._cfg_kwargs(),
247-        )
248-        self._client.submit(evt)
249-
250:    def on_session_shutdown(self, session_id: str) -> None:
251-        # Flush spool before process exit; tolerate already-closed client.
252-        try:
253-            self._client.flush_spool()
254-        except RuntimeError:
255-            pass
256-
257-    # -- memory extraction --------------------------------------------------
258-
259:    def request_extraction(
260-        self,
261-        run_id: str,
262-        session_id: str,
263-        result: ExtractionResult,
264-    ) -> None:
265-        """Persist the extraction result as an event.
266-
267-        If result.capture_result == "captured", also create a handoff and
268-        submit memory candidates.
269-        """
270-        payload = {
271-            "capture_result": result.capture_result,
272-        }
273-        if result.handoff:
274-            payload["handoff"] = result.handoff
--
291:    def on_extraction_requested(self, run_id: str, session_id: str) -> None:
292-        evt = build_event(
293-            "memory.extraction_requested",
294-            agent=self._config.agent,
295-            session_id=session_id,