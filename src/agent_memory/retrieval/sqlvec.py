"""Loadable-extension loader for sqlite-vec.

This module centralises where the sqlite-vec shared object is searched for.
Deployments may set ``retrieval.sqlite_vec_path`` in ``config.toml`` to a
shared object or a directory that contains it.

If the extension is not found, ``load_sqlite_vec()`` returns False and the
caller must degrade to lexical-only retrieval (the ``VectorIndex.available``
flag already does this).

Search order (first hit wins):
  1. configured path — absolute path to the shared object, or a directory
     containing it (common names tried: vec0, sqlite_vec, vec; with and
     without a platform suffix such as ``.so`` / ``.dylib`` / ``.dll``).
  2. ``/usr/lib/sqlite-vec`` and ``/usr/local/lib/sqlite-vec``.
  3. Python extension dir (``sysconfig.get_paths()['platlib']``) — works when
     the ``sqlite-vec`` pip package is installed (not yet published for
     CPython 3.13; placeholder for future support).

Usage::

    import sqlite3
    from agent_memory.retrieval.sqlvec import load_sqlite_vec
    conn = sqlite3.connect(path)
    if load_sqlite_vec(conn):
        conn.execute("CREATE VIRTUAL TABLE ... USING vec0(...)")
"""

from __future__ import annotations

import logging
import sqlite3
import sysconfig
from pathlib import Path

logger = logging.getLogger(__name__)

_CANDIDATE_DIRS: list[str] = [
    "/usr/lib/sqlite-vec",
    "/usr/local/lib/sqlite-vec",
]
_CANDIDATE_BASENAMES: list[str] = [
    "vec0",
    "sqlite_vec",
    "vec",
]
_PLATFORM_SUFFIXES: list[str] = ["", ".so", ".dylib", ".dll"]


def _variants(base: Path) -> list[Path]:
    """All candidate spellings for a base path (bare name + platform suffixes)."""
    return [base if s == "" else Path(str(base) + s) for s in _PLATFORM_SUFFIXES]


def _dir_candidates(directory: Path) -> list[Path]:
    out: list[Path] = []
    if directory.is_dir():
        for name in _CANDIDATE_BASENAMES:
            out.extend(_variants(directory / name))
    return out


def _resolve_configured_path(raw: str | None) -> list[Path]:
    raw = (raw or "").strip()
    if not raw:
        return []
    p = Path(raw).expanduser()
    if p.is_file():
        return [p]
    if p.is_dir():
        return _dir_candidates(p)
    return []


def _candidate_paths(configured_path: str | None = None) -> list[Path]:
    paths: list[Path] = []
    paths.extend(_resolve_configured_path(configured_path))
    for d in _CANDIDATE_DIRS:
        paths.extend(_dir_candidates(Path(d)))
    # Python site-packages
    platlib = sysconfig.get_paths().get("platlib", "")
    if platlib:
        root = Path(platlib)
        for name in _CANDIDATE_BASENAMES:
            # flat layout:  <platlib>/vec0.so
            paths.extend(_variants(root / name))
            # sub-package layout:  <platlib>/sqlite_vec/vec0
            paths.extend(_variants(root / name / "vec0"))
    # De-duplicate, keep first occurrence
    seen: set[str] = set()
    unique: list[Path] = []
    for p in paths:
        key = str(p)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def load_sqlite_vec(conn: sqlite3.Connection, configured_path: str | None = None) -> bool:
    """Enable load-extension support and attempt to load the sqlite-vec module.

    Returns True on success, False if no shared object was found. The
    connection is left usable in either case (the flag is already set).
    """
    try:
        conn.enable_load_extension(True)
    except sqlite3.Error as exc:
        logger.debug("enable_load_extension failed: %s", exc)
        return False

    for path in _candidate_paths(configured_path):
        if not path.is_file():
            continue
        try:
            conn.load_extension(str(path))
            logger.info("sqlite-vec loaded from %s", path)
            return True
        except sqlite3.OperationalError as exc:
            logger.debug("load_extension(%s) failed: %s", path, exc)
            continue

    # Fallback: let sqlite search its default extension directory.
    try:
        conn.load_extension("vec0")
        logger.info("sqlite-vec loaded from default extension path")
        return True
    except sqlite3.OperationalError as exc:
        logger.debug("default 'vec0' load failed: %s", exc)
        return False
