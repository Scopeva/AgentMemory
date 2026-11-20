"""Runtime configuration for the agent-memory service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    transport: str = "streamable-http"
    cors_origins: list[str] = field(default_factory=list)


@dataclass
class DatabaseConfig:
    path: str = "~/.local/share/agent-memory/memory.db"
    journal_mode: str = "wal"
    busy_timeout_ms: int = 5000

    def resolved_path(self) -> Path:
        return Path(self.path).expanduser()


@dataclass
class EmbeddingConfig:
    provider: str = "bge-m3-http"
    endpoint: str = "http://127.0.0.1:8001"
    model: str = "bge-m3"
    dimension: int = 1024
    enabled: bool = True

    def normalized_endpoint(self) -> str:
        """Return endpoint without trailing slash."""
        return self.endpoint.rstrip("/")

    def validate_endpoint(self) -> None:
        parsed = urlparse(self.normalized_endpoint())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Invalid BGE-M3 endpoint: {self.endpoint}")


@dataclass
class RetrievalConfig:
    lexical_top_k: int = 20
    vector_top_k: int = 20
    final_top_k: int = 6
    rrf_k: int = 60
    chunk_max_chars: int = 800
    chunk_min_chars: int = 200
    batch_index_max_docs: int = 100
    sqlite_vec_path: str = ""


@dataclass
class MemoryConfig:
    auto_capture: bool = True
    approval_required_for_adr: bool = True
    max_context_tokens: int = 2000


@dataclass
class EventsConfig:
    durable_spool: bool = True
    retry_enabled: bool = True
    max_extraction_attempts: int = 1


@dataclass
class SecurityConfig:
    admin_token_env: str = "AGENT_MEMORY_ADMIN_TOKEN"


@dataclass
class WorkersConfig:
    interval_seconds: float = 30.0
    empty_backoff_seconds: float = 120.0


@dataclass
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    events: EventsConfig = field(default_factory=EventsConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    workers: WorkersConfig = field(default_factory=WorkersConfig)


def load_config(path: str | None = None) -> AppConfig:
    """Load service settings from the canonical TOML file."""
    config_path = Path(path).expanduser() if path else Path("config.toml")
    data: dict[str, Any] = {}
    if config_path.is_file():
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

    security_data = dict(data.get("security", {}))
    # The legacy list was never enforced; accept it so upgrades do not fail.
    security_data.pop("mcp_allowed_agents", None)

    config = AppConfig(
        server=ServerConfig(**data.get("server", {})),
        database=DatabaseConfig(**data.get("database", {})),
        embedding=EmbeddingConfig(**data.get("embedding", {})),
        retrieval=RetrievalConfig(**data.get("retrieval", {})),
        memory=MemoryConfig(**data.get("memory", {})),
        events=EventsConfig(**data.get("events", {})),
        security=SecurityConfig(**security_data),
        workers=WorkersConfig(**data.get("workers", {})),
    )
    config.embedding.validate_endpoint()
    return config
