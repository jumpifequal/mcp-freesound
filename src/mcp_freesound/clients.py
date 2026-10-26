"""Helpers producing MCP client configuration snippets (used by the GUI)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from mcp_freesound.config import Config

SERVER_KEY = "freesound"


# mcp-freesound.py launcher at the root of a source checkout (src/mcp_freesound/../../)
LAUNCHER = Path(__file__).resolve().parents[2] / "mcp-freesound.py"


def base_command() -> list[str]:
    """Command that runs the CLI: installed script, checkout launcher, or ``-m``."""
    exe = shutil.which("mcp-freesound")
    if exe:
        return [exe]
    if LAUNCHER.is_file():
        return [sys.executable, str(LAUNCHER)]
    return [sys.executable, "-m", "mcp_freesound"]


def server_command(config_path: Path | None = None, transport: str = "stdio") -> list[str]:
    """Command line that launches the server on this machine."""
    command = base_command()
    if config_path is not None:
        command += ["--config", str(config_path)]
    return command + ["serve", "--transport", transport]


def server_url(config: Config, host: str | None = None) -> str:
    scheme = "https" if config.tls_cert else "http"
    host = host or config.host
    if host in ("0.0.0.0", "::", ""):
        host = "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{scheme}://{host}:{config.port}{config.path}"


def stdio_entry(config_path: Path | None = None) -> dict[str, Any]:
    command = server_command(config_path)
    # The API key is read from the saved config file, so it is not embedded here.
    return {"command": command[0], "args": command[1:]}


def http_bridge_entry(config: Config) -> dict[str, Any]:
    """Claude Desktop entry reaching the HTTP server through the ``mcp-remote`` bridge."""
    return {
        "command": "npx",
        "args": [
            "-y",
            "mcp-remote",
            server_url(config),
            "--header",
            "Authorization:${MCP_FREESOUND_AUTH}",
        ],
        "env": {"MCP_FREESOUND_AUTH": f"Bearer {config.auth_token}"},
    }


def claude_desktop_snippet(config: Config, config_path: Path | None = None) -> str:
    entry = stdio_entry(config_path) if config.transport == "stdio" else http_bridge_entry(config)
    return json.dumps({"mcpServers": {SERVER_KEY: entry}}, indent=2)


def claude_code_command(config: Config, config_path: Path | None = None) -> str:
    if config.transport == "stdio":
        command = " ".join(_quote(part) for part in server_command(config_path))
        return f"claude mcp add {SERVER_KEY} -- {command}"
    return (
        f"claude mcp add --transport http {SERVER_KEY} {server_url(config)} "
        f'--header "Authorization: Bearer {config.auth_token}"'
    )


def generic_http_snippet(config: Config) -> str:
    return json.dumps(
        {
            "mcpServers": {
                SERVER_KEY: {
                    "type": "http",
                    "url": server_url(config),
                    "headers": {"Authorization": f"Bearer {config.auth_token}"},
                }
            }
        },
        indent=2,
    )


def _quote(part: str) -> str:
    return f'"{part}"' if any(c in part for c in " \t") else part


def claude_desktop_config_path() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def install_claude_desktop(config: Config, config_path: Path | None = None, target: Path | None = None) -> Path:
    """Add/replace the ``freesound`` server in Claude Desktop's config, keeping a backup."""
    target = target or claude_desktop_config_path()
    data: dict[str, Any] = {}
    if target.is_file():
        data = json.loads(target.read_text(encoding="utf-8") or "{}")
        backup = target.with_name(f"{target.name}.{time.strftime('%Y%m%d-%H%M%S')}.bak")
        shutil.copy2(target, backup)
    entry = json.loads(claude_desktop_snippet(config, config_path))["mcpServers"][SERVER_KEY]
    data.setdefault("mcpServers", {})[SERVER_KEY] = entry
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return target
