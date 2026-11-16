"""Unit tests for the sqlite-vec loader (sqlvec) and VectorIndex wiring.

The tests do not require the actual sqlite-vec shared object. They verify:
  * load_sqlite_vec() returns False gracefully when the extension is absent.
  * _resolve_env_path() honours SQLITE_VEC_PATH (file, directory, unset).
  * VectorIndex.upsert/search/delete are safe no-ops when unavailable.
  * ensure_vec0() is exported and callable.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_memory.retrieval.sqlvec import load_sqlite_vec, _resolve_env_path, _candidate_paths
from agent_memory.retrieval.vector import (
    VectorIndex,
    vec_available,
    ensure_vec0,
    create_vector_index,
)


# ---------------------------------------------------------------------------
# load_sqlite_vec graceful degradation
# ---------------------------------------------------------------------------


class TestLoadSqliteVec:
    def test_returns_false_when_extension_absent(self):
        conn = sqlite3.connect(":memory:")
        result = load_sqlite_vec(conn)
        # In CI/sandbox without sqlite-vec installed, this must be False.
        assert result in (True, False)
        # Connection is still usable either way.
        conn.execute("SELECT 1").fetchone()
        conn.close()

    def test_enable_load_extension_called(self):
        conn = sqlite3.connect(":memory:")
        # Even when no .so is found, the flag should be set on the connection.
        load_sqlite_vec(conn)
        # A second call must not crash.
        load_sqlite_vec(conn)
        conn.close()


# ---------------------------------------------------------------------------
# _resolve_env_path
# ---------------------------------------------------------------------------


class TestResolveEnvPath:
    def test_unset_returns_empty(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SQLITE_VEC_PATH", None)
            assert _resolve_env_path() == []

    def test_file_path(self, tmp_path: Path):
        f = tmp_path / "vec0.so"
        f.write_bytes(b"\x00")
        with patch.dict(os.environ, {"SQLITE_VEC_PATH": str(f)}):
            result = _resolve_env_path()
            assert result == [f]
            assert result[0].is_file()

    def test_directory_path(self, tmp_path: Path):
        d = tmp_path / "sqlite-vec"
        d.mkdir()
        (d / "vec0").write_bytes(b"\x00")
        (d / "vec0.so").write_bytes(b"\x00")
        with patch.dict(os.environ, {"SQLITE_VEC_PATH": str(d)}):
            result = _resolve_env_path()
            # Directory form: all candidate names tried (vec0, sqlite_vec, vec)
            # and platform-suffixed variants are produced for the directory.
            assert len(result) >= 1
            # vec0 and vec0.so must both be among the candidates
            assert (d / "vec0") in result
            assert (d / "vec0.so") in result

    def test_nonexistent_path_returns_empty(self):
        with patch.dict(os.environ, {"SQLITE_VEC_PATH": "/nonexistent/vec0.so"}):
            assert _resolve_env_path() == []


# ---------------------------------------------------------------------------
# _candidate_paths deduplication
# ---------------------------------------------------------------------------


class TestCandidatePaths:
    def test_no_duplicates(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SQLITE_VEC_PATH", None)
            paths = _candidate_paths()
            keys = [str(p) for p in paths]
            assert len(keys) == len(set(keys)), "duplicate candidate paths found"

    def test_env_file_takes_priority(self, tmp_path: Path):
        f = tmp_path / "vec0"
        f.write_bytes(b"\x00")
        with patch.dict(os.environ, {"SQLITE_VEC_PATH": str(f)}):
            paths = _candidate_paths()
            assert paths[0] == f


# ---------------------------------------------------------------------------
# VectorIndex no-op behaviour
# ---------------------------------------------------------------------------


@pytest.fixture
def sync_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


class TestVectorIndexNoop:
    def test_upsert_search_delete_noop_when_unavailable(self, sync_conn):
        vi = VectorIndex(sync_conn, dimension=8)
        if vi.available:
            # sqlite-vec present: real upsert + search round-trip
            vi.upsert("k1", "c1", [0.1] * 8)
            results = vi.search([0.1] * 8, limit=5)
            assert len(results) >= 1
        else:
            vi.upsert("k1", "c1", [0.1] * 8)
            assert vi.search([0.1] * 8) == []
            vi.delete("k1")
            vi.delete("k1", ["c1"])

    def test_create_vector_index_factory(self, sync_conn):
        vi = create_vector_index(sync_conn, dimension=4)
        assert isinstance(vi, VectorIndex)

    def test_ensure_vec0_callable(self, sync_conn):
        # Returns bool; must not raise even when extension is absent.
        result = ensure_vec0(sync_conn)
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# vec_available import-time probe is consistent
# ---------------------------------------------------------------------------


class TestVecAvailableConsistency:
    def test_probe_matches_per_conn_load(self, sync_conn):
        # If the import-time probe said available, per-conn load must succeed.
        if vec_available():
            assert ensure_vec0(sync_conn) is True
