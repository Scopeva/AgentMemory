"""Embedding provider abstraction and BGE-M3 HTTP implementation.

The server depends only on this protocol so that the concrete BGE-M3 API
shape (llama service, Ollama, FlagEmbedding, OpenAI-compatible) is not
hard-coded into business logic.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Protocol

import httpx

from agent_memory.config import EmbeddingConfig


class EmbeddingProvider(Protocol):
    """Protocol for embedding text into dense vectors."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, all the same dimension."""
        ...

    async def health(self) -> bool:
        """Return True if the embedding backend is reachable."""
        ...

    @property
    def dimension(self) -> int:
        ...

    @property
    def model_name(self) -> str:
        ...


def _validate_vector(vec: list[float], expected_dim: int, index: int) -> list[float]:
    if len(vec) != expected_dim:
        raise ValueError(
            f"Embedding dimension mismatch: expected {expected_dim}, got {len(vec)} "
            f"(text index {index})"
        )
    for i, v in enumerate(vec):
        if math.isnan(v) or math.isinf(v):
            raise ValueError(f"Embedding contains NaN/Inf at dim {i} (text index {index})")
    return vec


class BgeM3HttpProvider:
    """Dense embedding provider backed by a local BGE-M3 HTTP service.

    Compatible with llama.cpp server, Ollama, and OpenAI-compatible /embeddings
    endpoints. The request/response shape is auto-detected on first use and
    cached so that the business layer never depends on a specific API dialect.

    Supported endpoint shapes (auto-detect):
      - OpenAI-style:  POST {endpoint}/embeddings  {"model":..., "input": [...]}
                       -> {"data": [{"embedding": [...]}]}
      - Ollama:        POST {endpoint}/api/embed   {"model":..., "input": [...]}
                       -> {"embeddings": [[...]]}
      - llama.cpp:     POST {endpoint}/embedding   {"prompt": "..."}
                       -> {"embedding": [...]}
    """

    def __init__(self, config: EmbeddingConfig, timeout: float = 30.0):
        self._config = config
        self._client = httpx.AsyncClient(timeout=timeout)
        # (shape, response_extractor) — shape is set after first successful call
        self._shape: str | None = None
        self._dim = config.dimension

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._config.model

    async def health(self) -> bool:
        base = self._config.normalized_endpoint()
        candidates = [f"{base}/health", f"{base}/api/tags", f"{base}/v1/models"]
        for url in candidates:
            try:
                resp = await self._client.get(url, timeout=5)
                if resp.status_code < 400:
                    return True
            except httpx.HTTPError:
                continue
        # llama.cpp server may not expose /health; treat base reachability as ok
        try:
            resp = await self._client.get(base, timeout=5)
            return resp.status_code < 500
        except httpx.HTTPError:
            return False

    # -- request dispatch --------------------------------------------------

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        base = self._config.normalized_endpoint()

        # Ollama-style: /api/embed
        if self._shape is None or self._shape == "ollama":
            try:
                resp = await self._client.post(
                    f"{base}/api/embed",
                    json={"model": self._config.model, "input": texts},
                    timeout=self._config.endpoint and 30 or 30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    vecs = data.get("embeddings")
                    if vecs is not None and len(vecs) == len(texts):
                        self._shape = "ollama"
                        self._dim = len(vecs[0])
                        return [
                            _validate_vector(v, self._dim, i) for i, v in enumerate(vecs)
                        ]
            except httpx.HTTPError:
                pass

        # OpenAI-style: /embeddings
        if self._shape is None or self._shape == "openai":
            try:
                resp = await self._client.post(
                    f"{base}/embeddings",
                    json={"model": self._config.model, "input": texts},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("data")
                    if items and "embedding" in items[0]:
                        self._shape = "openai"
                        vecs = [it["embedding"] for it in items]
                        self._dim = len(vecs[0])
                        return [
                            _validate_vector(v, self._dim, i) for i, v in enumerate(vecs)
                        ]
            except httpx.HTTPError:
                pass

        # llama.cpp: /embedding (one prompt at a time)
        if self._shape is None or self._shape == "llama":
            results = []
            for text in texts:
                resp = await self._client.post(
                    f"{base}/embedding", json={"prompt": text}
                )
                if resp.status_code == 200:
                    vec = resp.json().get("embedding")
                    if vec is not None:
                        self._shape = "llama"
                        self._dim = len(vec)
                        results.append(_validate_vector(vec, self._dim, len(results)))
                        continue
            if len(results) == len(texts):
                return results

        raise RuntimeError(
            f"BGE-M3 endpoint at {base} did not respond with a recognized "
            f"embedding API shape (tried ollama, openai, llama)."
        )

    async def close(self) -> None:
        await self._client.aclose()


def create_provider(config: EmbeddingConfig) -> EmbeddingProvider:
    """Factory: build the configured embedding provider."""
    if config.provider == "bge-m3-http":
        return BgeM3HttpProvider(config)
    raise ValueError(f"Unknown embedding provider: {config.provider}")
