#!/usr/bin/env sh
# Talk to the HTTP transport by hand. Start it first:
#   mcp-freesound serve --transport http --auth-token "$TOKEN"
URL=${URL:-http://127.0.0.1:8000/mcp}
TOKEN=${TOKEN:?set TOKEN to your bearer token}

# 1. initialize: the response carries the Mcp-Session-Id header
curl -si "$URL" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'

# 2. call a tool (add -H "Mcp-Session-Id: <id>" to stay in the session)
curl -s "$URL" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_sounds","arguments":{"query":"rain on window","max_results":3,"filter":"duration:[1 TO 20]"}}}'
