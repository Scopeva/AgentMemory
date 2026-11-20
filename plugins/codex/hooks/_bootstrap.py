"""Deprecated compatibility shim; package hooks no longer need a checkout."""

from agent_memory.adapters.codex import CodexAdapterConfig


def _bootstrap() -> None:
    """Kept for source-template compatibility; the packaged runtime is ready."""


def make_config() -> CodexAdapterConfig:
    return CodexAdapterConfig()
