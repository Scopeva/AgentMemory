"""Shared application service and dependency injection primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class DatabaseProtocol(Protocol):
    """Protocol implemented by the SQLite storage layer."""

    async def execute(self, sql: str, params: tuple = ()) -> None: ...
    async def query(self, sql: str, params: tuple = ()) -> list[dict]: ...


@dataclass
class ServiceContext:
    """Holds shared services for request handlers."""

    db: DatabaseProtocol
