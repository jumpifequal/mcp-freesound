"""stdio transport: newline-delimited JSON-RPC on stdin/stdout."""

from __future__ import annotations

import logging
import sys
from typing import BinaryIO

from mcp_freesound.protocol import MCPServer

log = logging.getLogger(__name__)


def serve_stdio(server: MCPServer, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> None:
    """Serve requests until stdin is closed. stdout carries protocol messages only."""
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    log.info("Freesound MCP server listening on stdio")
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        reply = server.handle_raw(line)
        if reply is not None:
            stdout.write(reply.encode("utf-8") + b"\n")
            stdout.flush()
    log.info("stdin closed, shutting down")
