"""Runtime configuration for the agent-memory service."""

from __future__ import annotations

import os
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
        return Path(os.path.expanduser(self.path))


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
    mcp_allowed_agents: list[str] = field(default_factory=lambda: ["pi", "codex", "opencode"])
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


def _apply_env_overrides(config: AppConfig, env: dict[str, str]) -> AppConfig:
    """Allow environment variables to override TOML values."""
    if path := env.get("AGENT_MEMORY_DATABASE_PATH"):
        config.database.path = path
    if endpoint := env.get("AGENT_MEMORY_EMBEDDING_ENDPOINT"):
        config.embedding.endpoint = endpoint
    if provider := env.get("AGENT_MEMORY_EMBEDDING_PROVIDER"):
        config.embedding.provider = provider
    if enabled := env.get("AGENT_MEMORY_EMBEDDING_ENABLED"):
        config.embedding.enabled = enabled.lower() in {"1", "true", "yes", "on"}
    if token_env := env.get("AGENT_MEMORY_SECURITY_ADMIN_TOKEN_ENV"):
        config.security.admin_token_env = token_env
    if interval := env.get("AGENT_MEMORY_WORKERS_INTERVAL_SECONDS"):
        try:
            config.workers.interval_seconds = float(interval)
        except ValueError:
            pass
    if backoff := env.get("AGENT_MEMORY_WORKERS_EMPTY_BACKOFF_SECONDS"):
        try:
            config.workers.empty_backoff_seconds = float(backoff)
        except ValueError:
            pass
    if origins := env.get("AGENT_MEMORY_CORS_ORIGINS"):
        config.server.cors_origins = [o.strip() for o in origins.split(",") if o.strip()]
    return config


def load_config(path: str | None = None) -> AppConfig:
    """Load TOML config and apply environment variable overrides."""
    config_path = Path(os.path.expanduser(path or os.environ.get("AGENT_MEMORY_CONFIG_PATH", "")))
    data: dict[str, Any] = {}
    if config_path.is_file():
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

    config = AppConfig(
        server=ServerConfig(**data.get("server", {})),
        database=DatabaseConfig(**data.get("database", {})),
        embedding=EmbeddingConfig(**data.get("embedding", {})),
        retrieval=RetrievalConfig(**data.get("retrieval", {})),
        memory=MemoryConfig(**data.get("memory", {})),
        events=EventsConfig(**data.get("events", {})),
        security=SecurityConfig(**data.get("security", {})),
        workers=WorkersConfig(**data.get("workers", {})),
    )
    config = _apply_env_overrides(config, os.environ)
    config.embedding.validate_endpoint()
    return config
