# Examples

| File | Purpose |
|---|---|
| `.env.example` | Environment variables understood by the server |
| `config.example.json` | Shape of the config file written by the GUI |
| `claude_desktop_stdio.json` | Claude Desktop, pip-installed server over stdio |
| `claude_desktop_stdio_from_source.json` | Claude Desktop, running `mcp-freesound.py` from a clone |
| `claude_desktop_http_bridge.json` | Claude Desktop reaching the HTTP server through `mcp-remote` |
| `http_client.json` | Generic config for clients that support Streamable HTTP + headers |
| `curl_examples.sh` | Raw JSON-RPC calls against the HTTP transport |

On Windows, if `FREESOUND_API_KEY` is set as a user or system environment variable, you can
drop the `env` blocks: the server reads the variable from the registry.

Claude Code:

```bash
claude mcp add freesound -e FREESOUND_API_KEY=your_key -- mcp-freesound serve --transport stdio
claude mcp add --transport http freesound http://127.0.0.1:8000/mcp --header "Authorization: Bearer your_token"
```
