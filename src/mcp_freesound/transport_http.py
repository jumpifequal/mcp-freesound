"""Streamable HTTP transport (JSON response mode) with bearer-token authentication.

Implements the subset of the MCP Streamable HTTP transport a tools-only server needs:

* ``POST <path>``   - JSON-RPC message or batch; replies with ``application/json``
* ``DELETE <path>`` - terminate the session named by ``Mcp-Session-Id``
* ``GET <path>``    - 405 (this server never pushes server-initiated messages)
* ``GET /health``   - unauthenticated liveness probe
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import secrets
import ssl
import threading
import urllib.parse
from collections import OrderedDict
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from mcp_freesound import SERVER_NAME, __version__
from mcp_freesound.config import Config
from mcp_freesound.protocol import INVALID_REQUEST, PARSE_ERROR, MCPServer, error_response

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 1024 * 1024
MAX_SESSIONS = 1000
SESSION_HEADER = "Mcp-Session-Id"


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return host.endswith(".localhost")


class SessionStore:
    """Thread-safe, bounded map of session id -> MCPServer."""

    def __init__(self, factory: Callable[[], MCPServer], limit: int = MAX_SESSIONS):
        self._factory = factory
        self._limit = limit
        self._sessions: OrderedDict[str, MCPServer] = OrderedDict()
        self._lock = threading.Lock()
        # Used for clients that do not send a session id (stateless use).
        self.default = factory()

    def create(self) -> tuple[str, MCPServer]:
        session_id = secrets.token_hex(16)
        server = self._factory()
        with self._lock:
            self._sessions[session_id] = server
            while len(self._sessions) > self._limit:
                self._sessions.popitem(last=False)
        return session_id, server

    def get(self, session_id: str) -> MCPServer | None:
        with self._lock:
            server = self._sessions.get(session_id)
            if server is not None:
                self._sessions.move_to_end(session_id)
            return server

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def __len__(self) -> int:
        return len(self._sessions)


class MCPHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, config: Config, sessions: SessionStore, require_auth: bool = True):
        self.config = config
        self.sessions = sessions
        self.require_auth = require_auth
        super().__init__(address, MCPRequestHandler)


class MCPRequestHandler(BaseHTTPRequestHandler):
    server: MCPHTTPServer
    server_version = f"{SERVER_NAME}/{__version__}"
    protocol_version = "HTTP/1.1"

    # ----------------------------------------------------------------- helpers
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        log.info("%s - %s", self.client_address[0], format % args)

    def _send(self, status: int, body: Any = None, headers: dict[str, str] | None = None) -> None:
        payload = b"" if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        if payload:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _route(self) -> str:
        return urllib.parse.urlsplit(self.path).path.rstrip("/") or "/"

    def _mcp_path(self) -> str:
        return self.server.config.path.rstrip("/") or "/"

    def _check_origin(self) -> bool:
        """Reject cross-origin browser requests (DNS-rebinding protection)."""
        origin = self.headers.get("Origin")
        if not origin:
            return True
        allowed = self.server.config.allowed_origins
        if "*" in allowed or origin in allowed:
            return True
        host = urllib.parse.urlsplit(origin).hostname or ""
        return is_loopback(host)

    def _check_auth(self) -> bool:
        if not self.server.require_auth:
            return True
        header = self.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        expected = self.server.config.auth_token
        if scheme.lower() == "bearer" and token and expected:
            return hmac.compare_digest(token.strip().encode(), expected.encode())
        return False

    def _guard(self) -> bool:
        """Run checks shared by all MCP endpoint methods. Sends the error reply on failure."""
        if self._route() != self._mcp_path():
            self._send(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return False
        if not self._check_origin():
            self._send(HTTPStatus.FORBIDDEN, {"error": "Origin not allowed"})
            return False
        if not self._check_auth():
            self._send(
                HTTPStatus.UNAUTHORIZED,
                {"error": "Missing or invalid bearer token"},
                {"WWW-Authenticate": f'Bearer realm="{SERVER_NAME}"'},
            )
            return False
        return True

    # ----------------------------------------------------------------- methods
    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if self._route() == "/health":
            self._send(HTTPStatus.OK, {"status": "ok", "server": SERVER_NAME, "version": __version__})
            return
        if self._guard():
            self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "SSE stream not supported"}, {"Allow": "POST, DELETE"})

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._guard():
            return
        session_id = self.headers.get(SESSION_HEADER)
        if session_id and self.server.sessions.delete(session_id):
            self._send(HTTPStatus.NO_CONTENT)
        else:
            self._send(HTTPStatus.NOT_FOUND, {"error": "Unknown session"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._guard():
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._send(HTTPStatus.LENGTH_REQUIRED, error_response(None, INVALID_REQUEST, "Content-Length required"))
            return
        if length > MAX_BODY_BYTES or length < 0:
            self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, error_response(None, INVALID_REQUEST, "Body too large"))
            return
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type.lower():
            self._send(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                error_response(None, INVALID_REQUEST, "Content-Type must be application/json"),
            )
            return
        try:
            message = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(HTTPStatus.BAD_REQUEST, error_response(None, PARSE_ERROR, "Parse error"))
            return

        headers: dict[str, str] = {}
        sessions = self.server.sessions
        session_id = self.headers.get(SESSION_HEADER)
        is_initialize = isinstance(message, dict) and message.get("method") == "initialize"
        if is_initialize:
            session_id, mcp = sessions.create()
            headers[SESSION_HEADER] = session_id
        elif session_id:
            mcp = sessions.get(session_id)
            if mcp is None:
                self._send(HTTPStatus.NOT_FOUND, error_response(None, INVALID_REQUEST, "Unknown or expired session"))
                return
        else:
            mcp = sessions.default

        reply = mcp.handle(message)
        if reply is None:
            # Only notifications / responses: acknowledge without a body.
            self._send(HTTPStatus.ACCEPTED, headers=headers)
        else:
            self._send(HTTPStatus.OK, reply, headers)


def build_http_server(config: Config, factory: Callable[[], MCPServer], require_auth: bool = True) -> MCPHTTPServer:
    if require_auth and not config.auth_token:
        raise ValueError(
            "HTTP transport requires a bearer token. Set MCP_FREESOUND_AUTH_TOKEN, use "
            "--auth-token, or generate one with 'mcp-freesound token'."
        )
    httpd = MCPHTTPServer((config.host, config.port), config, SessionStore(factory), require_auth)
    if config.tls_cert:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(config.tls_cert, config.tls_key)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    return httpd


def serve_http(config: Config, factory: Callable[[], MCPServer], require_auth: bool = True) -> None:
    httpd = build_http_server(config, factory, require_auth)
    scheme = "https" if config.tls_cert else "http"
    host, port = httpd.server_address[:2]
    log.info("Freesound MCP server listening on %s://%s:%s%s", scheme, host, port, config.path)
    if not require_auth:
        log.warning("Authentication is DISABLED. Only use this on a trusted machine.")
    if not is_loopback(config.host) and not config.tls_cert:
        log.warning("Listening on a non-loopback address without TLS: the bearer token travels in clear text.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("Interrupted, shutting down")
    finally:
        httpd.server_close()
