# Architecture

mcp-freesound is a single Python package with **no third-party runtime dependencies**.
Everything (JSON-RPC, HTTP server, HTTP client, GUI) comes from the standard library.

![How it works](../assets/infographic.svg)

```text
mcp-freesound.py            launcher: adds src/ to sys.path, runs the CLI (no install needed)
src/mcp_freesound/
  cli.py                    argparse CLI: serve | gui | token | config | check
  config.py                 Config dataclass, file/.env/env/CLI precedence, persistence
  protocol.py               MCP JSON-RPC 2.0 dispatcher (initialize, ping, tools/list, tools/call)
  tools.py                  the 13 tools: JSON Schemas + handlers + formatting
  freesound.py              Freesound API v2 client (urllib), safe preview downloader
  transport_stdio.py        newline-delimited JSON-RPC over stdin/stdout
  transport_http.py         Streamable HTTP (JSON mode), bearer auth, Origin check, sessions, TLS
  clients.py                client config snippets, Claude Desktop installer
  gui.py                    Tkinter configuration GUI and server runner
```

## Request flow

1. The MCP client (Claude Desktop, Claude Code, an IDE, an agent framework) sends a JSON-RPC
   message over **stdio** or **HTTP POST**.
2. HTTP only: `transport_http` checks the path, the `Origin` header and the
   `Authorization: Bearer <token>` header (constant-time comparison), then routes the message
   to the `MCPServer` of the session named by `Mcp-Session-Id`.
3. `protocol.MCPServer` negotiates the protocol version (`2025-06-18`, `2025-03-26`,
   `2024-11-05`), validates the tool name and arguments, and calls the handler.
4. The handler in `tools.py` calls `FreesoundClient`, which sends
   `Authorization: Token <api key>` to `https://freesound.org/apiv2/...`.
5. The result is returned as MCP `content` (pretty JSON text) and, for protocol
   `2025-06-18`, also as `structuredContent`.

## Configuration precedence

```text
defaults  <  config file  <  ./.env  <  environment variables  <  CLI flags
```

On Windows, a variable missing from the process environment is looked up in the registry
(`HKCU\Environment`, then `HKLM\...\Session Manager\Environment`). This covers MCP clients
that start servers with a reduced environment.

Config file location (override with `MCP_FREESOUND_CONFIG` or `--config`):

| OS | Path |
|---|---|
| Windows | `%APPDATA%\mcp-freesound\config.json` |
| macOS | `~/Library/Application Support/mcp-freesound/config.json` |
| Linux | `$XDG_CONFIG_HOME/mcp-freesound/config.json` (default `~/.config/...`) |

## HTTP transport details

| Request | Response |
|---|---|
| `POST /mcp` with a request | `200 application/json` with the JSON-RPC response |
| `POST /mcp` with only notifications | `202 Accepted` |
| `POST /mcp` `initialize` | `200` + `Mcp-Session-Id` header |
| unknown `Mcp-Session-Id` | `404` (client must re-initialize) |
| `DELETE /mcp` | ends the session (`204`) |
| `GET /mcp` | `405` (no server-initiated stream is needed) |
| `GET /health` | `200 {"status": "ok"}`, no authentication |
| missing/wrong token | `401` + `WWW-Authenticate: Bearer` |
| foreign browser `Origin` | `403` |

Requests without `Mcp-Session-Id` are served statelessly, which keeps simple clients and
`curl` working. At most 1000 sessions are kept (least recently used are evicted); bodies are
limited to 1 MiB.
