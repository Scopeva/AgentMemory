            task_significant=task_significant,
        ):
            self.observer.on_extraction_requested(run_id, session_id)
            self.controller.mark_attempted(run_id)
            # The caller (Pi extension) is now expected to ask the model for
            # one structured extraction and call submit_extraction_result().

    def submit_extraction_result(self, run_id: str, session_id: str, result: ExtractionResult) -> None:
        self.observer.request_extraction(run_id, session_id, result)
        self.controller.on_run_end(run_id)

    def on_run_interrupted(self, run_id: str, session_id: str, reason: str = "") -> None:
        self.observer.on_run_interrupted(run_id, session_id, reason)

    def on_session_shutdown(self, session_id: str) -> None:
123:class AgentType(str, Enum):
124-    PI = "pi"
125-    CODEX = "codex"
126-    OPENCODE = "opencode"
127-    ORCA = "orca"
128-    UNKNOWN = "unknown"
129-
130-
131-class Session(SchemaModel):
132-    session_id: str = Field(default_factory=_new_uuid)
133-    agent_type: AgentType