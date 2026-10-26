"""Transport-independent MCP (JSON-RPC 2.0) message handling."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp_freesound import SERVER_NAME, __version__
from mcp_freesound.config import Config
from mcp_freesound.freesound import FreesoundClient, FreesoundError
from mcp_freesound.tools import TOOLS, ToolContext, ToolInputError

log = logging.getLogger(__name__)

# Newest first. The first entry is offered when the client asks for an unknown version.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

INSTRUCTIONS = (
    "Tools for searching and exploring Freesound.org audio. Start with search_sounds, inspect "
    "results with get_sound or find_similar_sounds, and always check licenses: use "
    "get_attribution to produce credits for sounds that require attribution."
)


def error_response(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class MCPServer:
    """Handles decoded JSON-RPC messages and produces responses."""

    def __init__(self, config: Config, client: FreesoundClient | None = None):
        self.config = config
        self.client = client or FreesoundClient(config.api_key, timeout=config.timeout)
        self.context = ToolContext(client=self.client, config=config)
        self.protocol_version = LATEST_PROTOCOL_VERSION
        self.client_info: dict[str, Any] = {}

    # ------------------------------------------------------------------ dispatch
    def handle_raw(self, raw: str | bytes) -> str | None:
        """Handle a serialized message (or batch). Returns the serialized reply, if any."""
        try:
            message = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return json.dumps(error_response(None, PARSE_ERROR, "Parse error"))
        reply = self.handle(message)
        return None if reply is None else json.dumps(reply, ensure_ascii=False)

    def handle(self, message: Any) -> Any:
        """Handle a decoded message or batch. Returns a response object, list or ``None``."""
        if isinstance(message, list):
            if not message:
                return error_response(None, INVALID_REQUEST, "Empty batch")
            replies = [r for r in (self.handle_one(m) for m in message) if r is not None]
            return replies or None
        return self.handle_one(message)

    def handle_one(self, message: Any) -> dict | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return error_response(None, INVALID_REQUEST, "Invalid Request")
        method = message.get("method")
        request_id = message.get("id")
        is_notification = "id" not in message

        if method is None:
            # A response from the client (we never send requests, so just ignore it).
            return None
        if not isinstance(method, str):
            return None if is_notification else error_response(request_id, INVALID_REQUEST, "Invalid method")

        params = message.get("params") or {}
        if not isinstance(params, dict):
            return None if is_notification else error_response(request_id, INVALID_PARAMS, "params must be an object")

        if is_notification:
            log.debug("Notification %s", method)
            return None

        handler = self._handlers().get(method)
        if handler is None:
            return error_response(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")
        try:
            result = handler(params)
        except ToolInputError as exc:
            return error_response(request_id, INVALID_PARAMS, str(exc))
        except Exception:  # pragma: no cover - defensive
            log.exception("Unhandled error in %s", method)
            return error_response(request_id, INTERNAL_ERROR, "Internal error")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _handlers(self):
        return {
            "initialize": self.initialize,
            "ping": lambda params: {},
            "tools/list": self.list_tools,
            "tools/call": self.call_tool,
            "resources/list": lambda params: {"resources": []},
            "resources/templates/list": lambda params: {"resourceTemplates": []},
            "prompts/list": lambda params: {"prompts": []},
        }

    # ------------------------------------------------------------------ methods
    def initialize(self, params: dict) -> dict:
        requested = params.get("protocolVersion")
        self.protocol_version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
        self.client_info = params.get("clientInfo") or {}
        log.info(
            "Client %s %s connected (protocol %s)",
            self.client_info.get("name", "?"),
            self.client_info.get("version", ""),
            self.protocol_version,
        )
        return {
            "protocolVersion": self.protocol_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "title": "Freesound", "version": __version__},
            "instructions": INSTRUCTIONS,
        }

    def list_tools(self, params: dict) -> dict:
        return {"tools": [t.to_mcp() for t in TOOLS.values()]}

    def call_tool(self, params: dict) -> dict:
        name = params.get("name")
        tool = TOOLS.get(name) if isinstance(name, str) else None
        if tool is None:
            raise ToolInputError(f"Unknown tool: {name}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise ToolInputError("Tool arguments must be an object.")
        unknown = set(arguments) - set(tool.input_schema["properties"])
        if unknown:
            raise ToolInputError(f"Unknown argument(s) for {name}: {', '.join(sorted(unknown))}")
        log.info("Tool call %s", name)
        try:
            data = tool.handler(self.context, arguments)
        except (FreesoundError, ToolInputError) as exc:
            # Execution errors are reported to the model, not as protocol errors.
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        result: dict[str, Any] = {
            "content": [{"type": "text", "text": json.dumps(data, indent=2, ensure_ascii=False)}],
            "isError": False,
        }
        if self.protocol_version >= "2025-06-18":
            result["structuredContent"] = data
        return result
