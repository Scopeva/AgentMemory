     1	"""Runtime configuration for the agent-memory service."""
     2	
     3	from __future__ import annotations
     4	
     5	import os
     6	from dataclasses import dataclass, field
     7	from pathlib import Path
     8	from typing import Any
     9	from urllib.parse import urlparse
    10	
    11	try:
    12	    import tomllib
    13	except ModuleNotFoundError:  # Python < 3.11
    14	    import tomli as tomllib  # type: ignore[no-redef]
    15	
    16	
    17	@dataclass
    18	class ServerConfig:
    19	    host: str = "127.0.0.1"
    20	    port: int = 8765
    21	    transport: str = "streamable-http"
    22	
    23	
    24	@dataclass
    25	class DatabaseConfig:
    26	    path: str = "~/.local/share/agent-memory/memory.db"
    27	    journal_mode: str = "wal"
    28	    busy_timeout_ms: int = 5000
    29	
    30	    def resolved_path(self) -> Path:
    31	        return Path(os.path.expanduser(self.path))
    32	
    33	
    34	@dataclass
    35	class EmbeddingConfig:
    36	    provider: str = "bge-m3-http"
    37	    endpoint: str = "http://127.0.0.1:8001"
    38	    model: str = "bge-m3"
    39	    dimension: int = 1024
    40	    enabled: bool = True
    41	
    42	    def normalized_endpoint(self) -> str:
    43	        """Return endpoint without trailing slash."""
    44	        return self.endpoint.rstrip("/")
    45	
    46	    def validate_endpoint(self) -> None:
    47	        parsed = urlparse(self.normalized_endpoint())
    48	        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
    49	            raise ValueError(f"Invalid BGE-M3 endpoint: {self.endpoint}")
    50	
    51	
    52	@dataclass
    53	class RetrievalConfig:
    54	    lexical_top_k: int = 20
    55	    vector_top_k: int = 20
    56	    final_top_k: int = 6
    57	    rrf_k: int = 60
    58	
    59	
    60	@dataclass
    61	class MemoryConfig:
    62	    auto_capture: bool = True
    63	    approval_required_for_adr: bool = True
    64	    max_context_tokens: int = 2000
    65	
    66	
    67	@dataclass
    68	class EventsConfig:
    69	    durable_spool: bool = True
    70	    retry_enabled: bool = True
    71	    max_extraction_attempts: int = 1
    72	
    73	
    74	@dataclass
    75	class SecurityConfig:
    76	    mcp_allowed_agents: list[str] = field(default_factory=lambda: ["pi", "codex", "opencode"])
    77	    admin_token_env: str = "AGENT_MEMORY_ADMIN_TOKEN"
    78	
    79	
    80	@dataclass
    81	class AppConfig:
    82	    server: ServerConfig = field(default_factory=ServerConfig)
    83	    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    84	    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    85	    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    86	    memory: MemoryConfig = field(default_factory=MemoryConfig)
    87	    events: EventsConfig = field(default_factory=EventsConfig)
    88	    security: SecurityConfig = field(default_factory=SecurityConfig)
    89	
    90	
    91	def _apply_env_overrides(config: AppConfig, env: dict[str, str]) -> AppConfig:
    92	    """Allow environment variables to override TOML values."""
    93	    if path := env.get("AGENT_MEMORY_DATABASE_PATH"):
    94	        config.database.path = path
    95	    if endpoint := env.get("AGENT_MEMORY_EMBEDDING_ENDPOINT"):
    96	        config.embedding.endpoint = endpoint
    97	    if provider := env.get("AGENT_MEMORY_EMBEDDING_PROVIDER"):
    98	        config.embedding.provider = provider
    99	    if enabled := env.get("AGENT_MEMORY_EMBEDDING_ENABLED"):
   100	        config.embedding.enabled = enabled.lower() in {"1", "true", "yes", "on"}
   101	    if token_env := env.get("AGENT_MEMORY_SECURITY_ADMIN_TOKEN_ENV"):
   102	        config.security.admin_token_env = token_env
   103	    return config
   104	
   105	
   106	def load_config(path: str | None = None) -> AppConfig:
   107	    """Load TOML config and apply environment variable overrides."""
   108	    config_path = Path(os.path.expanduser(path or os.environ.get("AGENT_MEMORY_CONFIG_PATH", "")))
   109	    data: dict[str, Any] = {}
   110	    if config_path.is_file():
   111	        with open(config_path, "rb") as f:
   112	            data = tomllib.load(f)
   113	
   114	    config = AppConfig(
   115	        server=ServerConfig(**data.get("server", {})),
   116	        database=DatabaseConfig(**data.get("database", {})),
   117	        embedding=EmbeddingConfig(**data.get("embedding", {})),
   118	        retrieval=RetrievalConfig(**data.get("retrieval", {})),
   119	        memory=MemoryConfig(**data.get("memory", {})),
   120	        events=EventsConfig(**data.get("events", {})),
   121	        security=SecurityConfig(**data.get("security", {})),
   122	    )
   123	    config = _apply_env_overrides(config, os.environ)
   124	    config.embedding.validate_endpoint()
   125	    return config