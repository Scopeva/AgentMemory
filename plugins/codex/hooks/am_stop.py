#!/usr/bin/env python3
"""Deprecated wrapper for the packaged Codex Stop hook."""

from agent_memory.integrations.codex import main


if __name__ == "__main__":
    raise SystemExit(main(["stop"]))
