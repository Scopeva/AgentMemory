"""Install source-independent host integrations from the packaged runtime."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Any


_MCP_URL = "http://127.0.0.1:8765/mcp/"
_CODEX_HOOKS = {
    "SessionStart": ("session-start", 5, None),
    "PreCompact": ("pre-compact", 5, "Capturing pre-compact context"),
    "Stop": ("stop", 30, "Recording run result"),
    "SessionEnd": ("session-end", 3, None),
}


def _mcp_url() -> str:
    return os.environ.get("AGENT_MEMORY_MCP_URL", _MCP_URL)


def _register_mcp(agent: str, args: list[str]) -> None:
    if os.environ.get("AGENT_MEMORY_SKIP_MCP_REGISTRATION") == "1":
        return
    binary = os.environ.get(f"{agent.upper()}_BIN", agent)
    if shutil.which(binary) is None:
        print(f"{binary} not found; register {_mcp_url()} manually.", file=sys.stderr)
        return
    try:
        subprocess.run([binary, *args], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Could not register Agent Memory MCP: {exc}", file=sys.stderr)


def _is_agent_memory_hook(group: object) -> bool:
    if not isinstance(group, dict):
        return False
    for hook in group.get("hooks", []):
        if not isinstance(hook, dict):
            continue
        command = str(hook.get("command", ""))
        if "agent_memory.integrations.codex" in command or "agent-memory" in command:
            return True
    return False


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def install_codex() -> Path:
    codex_root = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    hooks_path = codex_root / "hooks.json"
    backup_path = hooks_path.with_name(f"{hooks_path.name}.agent-memory.bak")
    if hooks_path.exists() and not backup_path.exists():
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(hooks_path, backup_path)
    try:
        config = json.loads(hooks_path.read_text()) if hooks_path.exists() else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Cannot merge invalid {hooks_path}: {exc}") from exc
    if not isinstance(config, dict):
        raise RuntimeError(f"Cannot merge invalid {hooks_path}: root must be an object")

    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise RuntimeError(f"Cannot merge invalid {hooks_path}: hooks must be an object")

    interpreter = shlex.quote(os.path.abspath(sys.executable))
    for event, (lifecycle, timeout, status_message) in _CODEX_HOOKS.items():
        existing = hooks.get(event, [])
        if not isinstance(existing, list):
            raise RuntimeError(f"Cannot merge invalid {hooks_path}: hooks.{event} must be a list")
        command = f"{interpreter} -m agent_memory.integrations.codex {lifecycle}"
        hook: dict[str, Any] = {"type": "command", "command": command, "timeout": timeout}
        if status_message:
            hook["statusMessage"] = status_message
        hooks[event] = [group for group in existing if not _is_agent_memory_hook(group)] + [{"hooks": [hook]}]

    _write_json(hooks_path, config)
    _register_mcp("codex", ["mcp", "add", "agent-memory", "--url", _mcp_url()])
    return hooks_path


def _copy_asset(asset: str, target: Path) -> Path:
    payload = files("agent_memory.integrations.assets").joinpath(asset).read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f"{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return target


def install_opencode() -> Path:
    directory = Path(os.environ.get("OPENCODE_PLUGIN_DIR", Path.home() / ".config/opencode/plugins"))
    target = _copy_asset("opencode/agent-memory.ts", directory / "agent-memory.ts")
    _register_mcp("opencode", ["mcp", "add", "--global", "agent-memory", "--url", _mcp_url()])
    return target


def install_pi() -> Path:
    directory = Path(os.environ.get("PI_EXTENSIONS_DIR", Path.home() / ".pi/agent/extensions"))
    target = _copy_asset("pi/agent-memory.ts", directory / "agent-memory-pi.ts")
    _register_mcp("pi", ["mcp", "add", "agent-memory", "--url", _mcp_url()])
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent", choices=("codex", "opencode", "pi"))
    args = parser.parse_args(argv)
    installers = {"codex": install_codex, "opencode": install_opencode, "pi": install_pi}
    try:
        target = installers[args.agent]()
    except RuntimeError as exc:
        parser.error(str(exc))
    print(f"Installed Agent Memory for {args.agent}: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
