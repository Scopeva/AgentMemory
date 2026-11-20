#!/usr/bin/env python3
"""Project-id alias resolution for packaged agent adapters.

When an agent is launched from a working directory whose name does not
match the stable project identifier you want to use (for example
several local checkouts of the same logical project), you can map
those directory names to a single stable project_id via a TOML file:

    ~/.config/agent-memory/aliases.toml

Format::

    [aliases]
    "~/code/proj-a" = "proj-a"      # absolute path or glob -> project_id
    "~/work/proj-a" = "proj-a"
    "~/projects/*/proj-a" = "proj-a"
    "proj-a" = "proj-a"             # bare name fallback

Resolution order in ``resolve_project_id()``:

  1. ``explicit`` value (caller-supplied)
  2. ``AGENT_MEMORY_PROJECT_ID`` env var
  3. Alias table: match CWD or any ancestor directory against keys
     (longest-prefix wins; ``*`` wildcards are allowed)
  4. Git repo basename (``git rev-parse --show-toplevel``)
  5. CWD basename

Set ``AGENT_MEMORY_ALIASES_PATH`` to override the default location, or
pass a custom path into ``load_alias_table()``.
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Optional

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


DEFAULT_ALIAS_FILE = "~/.config/agent-memory/aliases.toml"


# ---------------------------------------------------------------------------
# Alias table loading
# ---------------------------------------------------------------------------


def load_alias_table(path: Optional[str] = None) -> dict[str, str]:
    """Read the alias TOML file and return a ``{key: project_id}`` dict.

    Returns an empty dict when the file is missing or malformed so that
    callers can continue with the auto-detection fallback.
    """
    raw_path = path or os.environ.get(
        "AGENT_MEMORY_ALIASES_PATH", DEFAULT_ALIAS_FILE
    )
    p = Path(os.path.expanduser(raw_path))
    if not p.is_file():
        return {}

    if tomllib is not None:
        try:
            with open(p, "rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            return {}
    else:
        # Fallback for Python < 3.11: try tomli, else bail out.
        try:
            import tomli  # type: ignore[import-not-found]

            with open(p, "rb") as fh:
                data = tomli.load(fh)
        except (ImportError, OSError):
            return {}
        except Exception:
            return {}

    aliases = data.get("aliases", {})
    if not isinstance(aliases, dict):
        return {}
    return {str(k): str(v) for k, v in aliases.items()}


# ---------------------------------------------------------------------------
# Alias matching
# ---------------------------------------------------------------------------


def _key_sort_key(key: str) -> tuple[int, int, int]:
    """Sort keys so longer, more specific ones are tried first.

    - literal keys (no ``*``) win over wildcards
    - longer keys win over shorter ones within the same class
    """
    is_wild = int("*" in key)
    return (is_wild, -len(key), key)


def _expand_key(key: str) -> str:
    """Expand a user-supplied alias key: ``~`` and relative paths."""
    k = key.strip()
    if k.startswith("~/"):
        return str(Path.home() / k[2:])
    if k.startswith("~"):
        return str(Path.home() / k[1:])
    return os.path.abspath(k)


def _key_matches(key: str, target: Path, expanded_key: str) -> bool:
    """Return True when ``key`` matches the target directory.

    Supports three forms:
      - bare name (no path separator):  matches any directory with that name
      - absolute path / glob with ``*``:  matches that exact path or any
        sub-path under it (fnmatch)
      - relative path (with separator, no leading ``/``):  matched against
        the target's ancestor chain
    """
    if "*" in key:
        return fnmatch.fnmatchcase(str(target), expanded_key)
    if os.sep in key or (os.altsep and os.altsep in key):
        # Treat as a path prefix: the target is the key or lives under it.
        return str(target).startswith(expanded_key + os.sep) or str(target) == expanded_key
    # Bare name: match the basename of target or any ancestor.
    cur = target
    while cur != cur.parent:
        if cur.name == key:
            return True
        cur = cur.parent
    return cur.name == key


def find_alias(target_dir: Optional[Path] = None) -> Optional[str]:
    """Resolve a directory against the alias table.

    Returns the mapped ``project_id`` or ``None`` when no alias matches.
    ``target_dir`` defaults to the current working directory.
    """
    table = load_alias_table()
    if not table:
        return None

    target = target_dir or Path.cwd()
    target = target.resolve() if target.exists() else target

    # Sort keys most-specific-first; first hit wins.
    ordered = sorted(table.items(), key=lambda kv: _key_sort_key(kv[0]))
    for raw_key, project_id in ordered:
        expanded = _expand_key(raw_key)
        if _key_matches(raw_key, target, expanded):
            return project_id
    return None


# ---------------------------------------------------------------------------
# Top-level resolution
# ---------------------------------------------------------------------------


def resolve_project_id(
    explicit: Optional[str] = None,
    target_dir: Optional[Path] = None,
) -> Optional[str]:
    """Return the best-effort project_id, or ``None`` when undeterminable."""
    if explicit:
        return explicit
    env = os.environ.get("AGENT_MEMORY_PROJECT_ID", "").strip()
    if env:
        return env

    # 3. Alias table
    alias = find_alias(target_dir=target_dir or Path.cwd())
    if alias:
        return alias

    # 4. Git repo basename
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).name
    except Exception:
        pass

    # 5. CWD basename
    target = target_dir or Path.cwd()
    name = target.name
    return name if name not in ("", ".", "..") else None
