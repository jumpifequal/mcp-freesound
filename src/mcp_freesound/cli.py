"""Command line interface.

mcp-freesound [serve] [--transport stdio|http] [...]   run the MCP server (default)
mcp-freesound gui                                       open the configuration GUI
mcp-freesound token                                     print a new random bearer token
mcp-freesound config [--show-secrets]                   print the effective configuration
mcp-freesound check                                     verify the Freesound API key
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from mcp_freesound import __version__
from mcp_freesound.config import LOG_LEVELS, TRANSPORTS, Config, default_config_path, generate_token, load_config
from mcp_freesound.freesound import FreesoundClient, FreesoundError
from mcp_freesound.protocol import MCPServer

log = logging.getLogger("mcp_freesound")

SECRET_FIELDS = ("api_key", "auth_token")


def mask(value: str) -> str:
    if not value:
        return ""
    return value[:4] + "..." if len(value) > 8 else "***"


def _add_server_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--transport", choices=TRANSPORTS, help="Transport to use (default: stdio).")
    parser.add_argument("--host", help="HTTP bind address (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, help="HTTP port (default: 8000).")
    parser.add_argument("--path", help="HTTP endpoint path (default: /mcp).")
    parser.add_argument("--auth-token", dest="auth_token", help="Bearer token required by the HTTP transport.")
    parser.add_argument(
        "--allowed-origin",
        dest="allowed_origins",
        action="append",
        help="Extra browser Origin allowed to call the HTTP endpoint (repeatable).",
    )
    parser.add_argument("--tls-cert", dest="tls_cert", help="PEM certificate to serve HTTPS.")
    parser.add_argument("--tls-key", dest="tls_key", help="PEM private key to serve HTTPS.")
    parser.add_argument(
        "--insecure-no-auth",
        action="store_true",
        help="Disable bearer authentication on the HTTP transport (local testing only).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-freesound",
        description="Pure-Python MCP server for Freesound.org audio search.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, help=f"Config file (default: {default_config_path()}).")
    parser.add_argument("--api-key", dest="api_key", help="Freesound API key (prefer FREESOUND_API_KEY).")
    parser.add_argument("--download-dir", dest="download_dir", help="Folder for downloaded previews.")
    parser.add_argument("--log-level", dest="log_level", choices=LOG_LEVELS, type=str.upper)
    _add_server_args(parser)

    sub = parser.add_subparsers(dest="command")
    # SUPPRESS keeps options given before the sub-command from being reset to None.
    serve = sub.add_parser("serve", help="Run the MCP server (default command).", argument_default=argparse.SUPPRESS)
    _add_server_args(serve)
    sub.add_parser("gui", help="Open the configuration GUI.")
    sub.add_parser("token", help="Print a new random bearer token.")
    show = sub.add_parser("config", help="Print the effective configuration as JSON.")
    show.add_argument("--show-secrets", action="store_true", help="Do not mask the API key and token.")
    sub.add_parser("check", help="Verify that the Freesound API key works.")
    return parser


def setup_logging(level: str) -> None:
    # Logs always go to stderr: stdout is reserved for the stdio protocol stream.
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def check_api_key(config: Config) -> tuple[bool, str]:
    client = FreesoundClient(config.api_key, timeout=config.timeout)
    try:
        data = client.search(query="test", page_size=1, fields="id")
    except FreesoundError as exc:
        return False, str(exc)
    return True, f"API key works ({data.get('count', 0)} results for a test query)."


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    non_config = {"command", "config", "insecure_no_auth", "show_secrets"}
    overrides = {k: v for k, v in vars(args).items() if k not in non_config}
    try:
        config = load_config(args.config, overrides)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    setup_logging(config.log_level)

    command = args.command or "serve"
    if command == "token":
        print(generate_token())
        return 0
    if command == "config":
        data = config.to_dict()
        if not args.show_secrets:
            for key in SECRET_FIELDS:
                data[key] = mask(data[key])
        print(json.dumps(data, indent=2))
        return 0
    if command == "gui":
        from mcp_freesound.gui import run_gui

        return run_gui(args.config)
    if command == "check":
        ok, message = check_api_key(config)
        print(message, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1

    problems = config.validate()
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 2

    client = FreesoundClient(config.api_key, timeout=config.timeout)
    if config.transport == "stdio":
        from mcp_freesound.transport_stdio import serve_stdio

        serve_stdio(MCPServer(config, client))
        return 0

    from mcp_freesound.transport_http import serve_http

    try:
        serve_http(config, lambda: MCPServer(config, client), require_auth=not args.insecure_no_auth)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
