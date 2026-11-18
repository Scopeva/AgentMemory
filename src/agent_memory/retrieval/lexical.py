"""FTS5 lexical index maintenance for memory chunks."""

from __future__ import annotations

import sqlite3
from typing import Any


def fts5_query(query: str, fts_query: str | None = None) -> str:
    """Build a safe FTS5 query string.

    If ``fts_query`` is provided (user-supplied), it is used as-is.
    Otherwise we sanitize ``query`` to avoid FTS5 syntax errors by wrapping
    each token in double quotes.
    """
    if fts_query:
        return fts_query
    # Split on whitespace and quote each token to avoid FTS5 operator injection
    tokens = query.split()
    if not tokens:
        return ""
    # Quote each token: "word" OR "word" style
    return " ".join(f'"{t.replace(chr(34), chr(34) * 2)}"' for t in tokens if t.strip())


class LexicalIndex:
    """Manage the FTS5 ``chunks_fts`` virtual table.

    FTS5 is always available in SQLite builds; no import-time check needed.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @property
    def available(self) -> bool:
        return True

    def upsert_chunk(
        self,
        chunk_id: str,
        project_id: str,
        entity_id: str,
        document_type: str,
        text: str,
        title: str = "",
        summary: str = "",
    ) -> None:
        row = (
            chunk_id,
            project_id,
            entity_id,
            document_type,
            title,
            summary,
            text,
            1,
        )
        existing = self._conn.execute(
            "SELECT 1 FROM chunks_fts WHERE chunk_id = ? LIMIT 1", (chunk_id,)
        ).fetchone()
        if existing:
            self._conn.execute(
                "DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,)
            )
        self._conn.execute(
            "INSERT INTO chunks_fts (chunk_id, project_id, entity_id, document_type, "
            "title, summary, text, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )

    def delete_chunk(self, chunk_id: str) -> None:
        self._conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))

    def search(
        self,
        project_id: str,
        fts5_query: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT chunk_id, rank AS fts_rank FROM chunks_fts "
            "WHERE chunks_fts MATCH ? AND project_id = ? AND active = 1 "
            "ORDER BY rank LIMIT ?"
        )
        rows = self._conn.execute(sql, (fts5_query, project_id, limit)).fetchall()
        return [{"chunk_id": r[0], "rank": r[1]} for r in rows]
