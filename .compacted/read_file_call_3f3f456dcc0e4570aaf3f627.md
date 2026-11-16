     1	"""Codex adapter: official Hooks-based session lifecycle observer.
     2	
     3	Codex (OpenAI's CLI agent) supports session hooks:
     4	- SessionStart: agent begins a conversation
     5	- Stop: agent finishes a run (outcome: completed/failed/interrupted)
     6	- PreCompact: context window compaction warning
     7	- SessionEnd: session teardown / shutdown
     8	
     9	The adapter reuses the shared EventClient + DurableSpool for at-least-once
    10	delivery and builds EventEnvelope payloads matching the Phase 0 contract.
    11	Codex has no controlled_continuation capability (per agent_capabilities),
    12	so the adapter is observe-only: it persists events but does not trigger
    13	extraction.
    14	"""
    15	
    16	from __future__ import annotations
    17	
    18	import os
    19	from dataclasses import dataclass, field
    20	from typing import Optional
    21	
    22	from adapters.shared.event_client import DurableSpool, EventClient, build_event
    23	
    24	
    25	# ---------------------------------------------------------------------------
    26	# Adapter config
    27	# ---------------------------------------------------------------------------
    28	
    29	
    30	@dataclass
    31	class CodexAdapterConfig:
    32	    agent: str = "codex"
    33	    server_url: str = field(
    34	        default_factory=lambda: os.environ.get("AGENT_MEMORY_SERVER_URL", "http://127.0.0.1:8765")
    35	    )
    36	    spool_root: Optional[str] = None
    37	    project_id: Optional[str] = None
    38	    workspace_id: Optional[str] = None
    39	    task_id: Optional[str] = None
    40	
    41	
    42	# ---------------------------------------------------------------------------
    43	# Hook observer (passive, synchronous)
    44	# ---------------------------------------------------------------------------
    45	
    46	
    47	class CodexHookObserver:
    48	    """Records Codex hook events to the EventClient + spool.
    49	
    50	    All methods are synchronous for easy integration with Codex's hook
    51	    callbacks (SessionStart / Stop / PreCompact / SessionEnd).
    52	    """
    53	
    54	    def __init__(self, client: EventClient, config: CodexAdapterConfig):
    55	        self._client = client
    56	        self._config = config
    57	        self._seq = 0
    58	
    59	    def _next_seq(self) -> int:
    60	        self._seq += 1
    61	        return self._seq
    62	
    63	    def _cfg_kwargs(self) -> dict:
    64	        return {
    65	            "project_id": self._config.project_id,
    66	            "workspace_id": self._config.workspace_id,
    67	            "task_id": self._config.task_id,
    68	        }
    69	
    70	    # -- SessionStart -------------------------------------------------------
    71	
    72	    def on_session_start(
    73	        self, session_id: str, native_session_id: str = "", head_sha: str = ""
    74	    ) -> None:
    75	        """Codex SessionStart hook: emit session.start + run.started."""
    76	        start_evt = build_event(
    77	            "session.start",
    78	            agent=self._config.agent,
    79	            session_id=session_id,
    80	            run_id=session_id,
    81	            sequence_no=self._next_seq(),
    82	            payload={"native_session_id": native_session_id},
    83	            **self._cfg_kwargs(),
    84	        )
    85	        self._client.submit(start_evt)
    86	
    87	        if head_sha:
    88	            run_evt = build_event(
    89	                "run.started",
    90	                agent=self._config.agent,
    91	                session_id=session_id,
    92	                run_id=session_id,
    93	                sequence_no=self._next_seq(),
    94	                payload={"head_sha_start": head_sha},
    95	                **self._cfg_kwargs(),
    96	            )
    97	            self._client.submit(run_evt)
    98	
    99	    # -- Stop ---------------------------------------------------------------
   100	
   101	    def on_stop(self, session_id: str, outcome: str, head_sha_end: str = "") -> None:
   102	        """Codex Stop hook: emit run.settled with the run outcome.
   103	
   104	        outcome: "completed" | "failed" | "interrupted"
   105	        """
   106	        evt = build_event(
   107	            "run.settled",
   108	            agent=self._config.agent,
   109	            session_id=session_id,
   110	            run_id=session_id,
   111	            sequence_no=self._next_seq(),
   112	            payload={"outcome": outcome, "head_sha_end": head_sha_end},
   113	            **self._cfg_kwargs(),
   114	        )
   115	        self._client.submit(evt)
   116	
   117	    # -- PreCompact ---------------------------------------------------------
   118	
   119	    def on_pre_compact(self, session_id: str, summary: str = "") -> None:
   120	        """Codex PreCompact hook: emit session.compacted before context loss."""
   121	        evt = build_event(
   122	            "session.compacted",
   123	            agent=self._config.agent,
   124	            session_id=session_id,
   125	            run_id=session_id,
   126	            sequence_no=self._next_seq(),
   127	            payload={"pre_compact_summary": summary},
   128	            **self._cfg_kwargs(),
   129	        )
   130	        self._client.submit(evt)
   131	
   132	    # -- SessionEnd ---------------------------------------------------------
   133	
   134	    def on_session_end(self, session_id: str) -> None:
   135	        """Codex SessionEnd hook: flush spool before process exits."""
   136	        try:
   137	            self._client.flush_spool()
   138	        except RuntimeError:
   139	            pass
   140	
   141	
   142	# ---------------------------------------------------------------------------
   143	# Top-level adapter
   144	# ---------------------------------------------------------------------------
   145	
   146	
   147	class CodexAdapter:
   148	    """Façade for Codex hook integration.
   149	
   150	    Usage (inside a Codex hook script):
   151	        adapter = CodexAdapter(CodexAdapterConfig(project_id="..."))
   152	        adapter.on_session_start(session_id, native_id, head_sha)
   153	        adapter.on_pre_compact(session_id, summary)
   154	        adapter.on_stop(session_id, "completed", head_sha_end)
   155	        adapter.on_session_end(session_id)
   156	    """
   157	
   158	    def __init__(self, config: Optional[CodexAdapterConfig] = None):
   159	        self.config = config or CodexAdapterConfig()
   160	        spool = DurableSpool(self.config.agent, root=self.config.spool_root)
   161	        self.client = EventClient(self.config.server_url, self.config.agent, spool=spool)
   162	        self.observer = CodexHookObserver(self.client, self.config)
   163	
   164	    # Convenience re-exports
   165	    def on_session_start(self, session_id: str, native_session_id: str = "", head_sha: str = "") -> None:
   166	        self.observer.on_session_start(session_id, native_session_id, head_sha)
   167	
   168	    def on_stop(self, session_id: str, outcome: str, head_sha_end: str = "") -> None:
   169	        self.observer.on_stop(session_id, outcome, head_sha_end)
   170	
   171	    def on_pre_compact(self, session_id: str, summary: str = "") -> None:
   172	        self.observer.on_pre_compact(session_id, summary)
   173	
   174	    def on_session_end(self, session_id: str) -> None:
   175	        self.observer.on_session_end(session_id)
   176	
   177	    def flush(self) -> dict:
   178	        return self.client.flush_spool()
   179	
   180	    def close(self) -> None:
   181	        self.client.close()