"""Deterministic chunking for documents and conversation turns.

Strategy (document type):
- Primary split on section headers (## / ### markdown or # / ## in plain text)
- Secondary split on paragraph boundaries
- Merge consecutive chunks until each reaches at least ~200 chars
- Cap at ``chunk_max_chars`` (default 800)

Strategy (message type):
- Group consecutive messages with the same author/role
- Emit one chunk per author-group
- Cap at ``chunk_max_chars``
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# markdown headers: # / ## / ###
_MD_HEADER = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_PLAIN_HEADER = re.compile(r"^={3,}\s*$|^-{3,}\s*$", re.MULTILINE)


@dataclass
class Chunk:
    text: str
    chunk_index: int = 0
    char_start: int = 0
    char_end: int = 0
    token_estimate: int = 0


@dataclass
class ChunkerConfig:
    max_chars: int = 800
    min_chars: int = 200
    overlap_sentences: int = 2  # kept for future sentence-window overlap
    split_on_headers: bool = True

    @classmethod
    def from_service_config(cls, retrieval: "object") -> "ChunkerConfig":
        """Accept a RetrievalConfig-like object with a chunk_max_chars field."""
        return cls(max_chars=getattr(retrieval, "chunk_max_chars", 800))


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English/code mixed text."""
    return max(1, len(text) // 4)


def _find_section_bounds(text: str, split_on_headers: bool) -> list[int]:
    """Return character offsets where new sections start (header lines)."""
    if not split_on_headers:
        return []
    bounds: list[int] = []
    for m in _MD_HEADER.finditer(text):
        # only top-level headers start new sections
        if len(m.group(1)) <= 3:
            bounds.append(m.start())
    # plain-text headers (===== / -----)
    for m in _PLAIN_HEADER.finditer(text):
        bounds.append(m.start())
    return sorted(set(bounds))


def _merge_to_size(
    sections: list[str], min_chars: int, max_chars: int
) -> list[str]:
    """Merge consecutive sections up to max_chars, keeping at least min_chars."""
    merged: list[str] = []
    current = ""
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        if current:
            candidate = current + "\n" + sec
            if len(candidate) <= max_chars:
                current = candidate
                continue
            # flush current
            merged.append(current)
            current = sec
        else:
            if len(sec) > max_chars:
                # hard-split very long section
                for i in range(0, len(sec), max_chars):
                    merged.append(sec[i : i + max_chars])
                current = ""
            else:
                current = sec
    if current:
        merged.append(current)
    return [m for m in merged if m.strip()]


def chunk_document(
    text: str,
    config: ChunkerConfig | None = None,
    document_type: str = "document",
) -> list[Chunk]:
    """Split document text into chunks suitable for indexing."""
    cfg = config or ChunkerConfig()
    if document_type == "message_group" or document_type == "message":
        return [
            Chunk(
                text=text.strip(),
                chunk_index=0,
                token_estimate=_estimate_tokens(text),
            )
            if text.strip()
            else Chunk(text="", chunk_index=0, token_estimate=0)
        ]

    # document type: section-aware split
    bounds = _find_section_bounds(text, cfg.split_on_headers)
    sections: list[str] = []
    prev = 0
    for b in bounds:
        if b > prev:
            sections.append(text[prev:b])
        prev = b
    if prev < len(text):
        sections.append(text[prev:])

    chunks = _merge_to_size(sections, cfg.min_chars, cfg.max_chars)

    # track char offsets
    result: list[Chunk] = []
    pos = 0
    for i, c in enumerate(chunks):
        c_stripped = c.strip()
        char_start = text.find(c_stripped, pos)
        if char_start < 0:
            char_start = pos
        result.append(
            Chunk(
                text=c_stripped,
                chunk_index=i,
                char_start=char_start,
                char_end=char_start + len(c_stripped),
                token_estimate=_estimate_tokens(c_stripped),
            )
        )
        pos = char_start + len(c_stripped)
    return result


def chunk_conversation_turns(
    turns: list[dict], config: ChunkerConfig | None = None
) -> list[Chunk]:
    """Group consecutive turns by author/role; one chunk per group.

    Each turn is a dict with at least ``author`` and ``content`` keys.
    """
    cfg = config or ChunkerConfig()
    chunks: list[Chunk] = []
    i = 0
    while i < len(turns):
        author = turns[i].get("author", "unknown")
        group: list[str] = [turns[i].get("content", "")]
        j = i + 1
        while j < len(turns) and turns[j].get("author", "unknown") == author:
            group.append(turns[j].get("content", ""))
            j += 1
        text = "\n".join(group).strip()
        if text:
            # cap very long groups
            for k in range(0, len(text), cfg.max_chars):
                part = text[k : k + cfg.max_chars]
                chunks.append(
                    Chunk(
                        text=part,
                        chunk_index=len(chunks),
                        token_estimate=_estimate_tokens(part),
                    )
                )
        i = j
    return chunks


def build_search_text(knowledge: dict) -> str:
    """Build the searchable text blob for a knowledge row."""
    parts = [
        knowledge.get("title", ""),
        knowledge.get("summary", ""),
        knowledge.get("content", ""),
    ]
    return "\n".join(p for p in parts if p)


def chunk_knowledge(knowledge: dict, config: ChunkerConfig | None = None) -> list[Chunk]:
    """Chunk a knowledge row (title + summary + content) for indexing."""
    cfg = config or ChunkerConfig()
    doc_text = build_search_text(knowledge)
    return chunk_document(doc_text, cfg, document_type="document")
