"""Offline tests: protocol, tools (with a fake Freesound client), HTTP and stdio transports.

Run from the project root:
    python -m pytest -p no:cacheprovider --basetemp=test/_out/pytest test
"""

import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp_freesound import cli, clients  # noqa: E402
from mcp_freesound.config import Config, load_config  # noqa: E402
from mcp_freesound.freesound import FreesoundClient, FreesoundError  # noqa: E402
from mcp_freesound.protocol import MCPServer  # noqa: E402
from mcp_freesound.transport_http import build_http_server  # noqa: E402

SOUND = {
    "id": 1,
    "name": "Rain",
    "tags": ["rain"],
    "license": "http://creativecommons.org/licenses/by/4.0/",
    "duration": 3.2,
    "previews": {"preview-hq-mp3": "https://cdn.freesound.org/previews/x.mp3"},
    "url": "https://freesound.org/s/1/",
    "username": "uploader",
    "type": "wav",
    "description": "x" * 300,
}


class FakeClient:
    def __init__(self):
        self.calls = []

    def search(self, **params):
        self.calls.append(("search", params))
        return {"count": 50, "next": "n", "results": [SOUND]}

    def sound(self, sound_id, fields=None):
        if sound_id == 404:
            raise FreesoundError("Freesound API error 404", 404)
        return dict(SOUND, id=sound_id)

    def similar(self, sound_id, **params):
        self.calls.append(("similar", params))
        return {"count": 0, "results": []}

    def usage(self, num_days):
        return {"days": num_days}

    def download(self, url, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"abc")
        return 3


def make_server(**config):
    return MCPServer(Config(api_key="k", **config), FakeClient())


def rpc(method, params=None, msg_id=1):
    message = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def call_tool(server, name, arguments):
    return server.handle(rpc("tools/call", {"name": name, "arguments": arguments}))


def tool_json(response):
    return json.loads(response["result"]["content"][0]["text"])


# --------------------------------------------------------------------- protocol
def test_initialize_and_list():
    server = make_server()
    reply = server.handle(rpc("initialize", {"protocolVersion": "2025-03-26"}))
    assert reply["result"]["protocolVersion"] == "2025-03-26"
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = server.handle(rpc("tools/list", msg_id=2))["result"]["tools"]
    assert len(tools) == 13
    assert tools[0]["name"] == "search_sounds"
    assert server.handle(rpc("nope", msg_id=3))["error"]["code"] == -32601


def test_search_format_matches_original():
    server = make_server()
    server.handle(rpc("initialize", {"protocolVersion": "2025-06-18"}))
    reply = call_tool(server, "search_sounds", {"query": " rain ", "max_results": 99})
    data = reply["result"]["structuredContent"]
    assert data["query"] == "rain"
    assert data["sounds"][0]["description"].endswith("...")
    assert "note" in data
    assert server.client.calls[0][1]["page_size"] == 30


def test_errors():
    server = make_server()
    assert call_tool(server, "get_sound", {"sound_id": 404})["result"]["isError"]
    assert call_tool(server, "get_sound", {"bad": 1})["error"]["code"] == -32602
    assert call_tool(server, "search_sounds", {"query": "a", "sort": "zzz"})["result"]["isError"]
    assert json.loads(server.handle_raw("{bad"))["error"]["code"] == -32700


def test_attribution_and_download(tmp_path):
    server = make_server(download_dir=str(tmp_path))
    data = tool_json(call_tool(server, "get_attribution", {"sound_ids": [1, 404]}))
    assert "CC BY" in data["credits_text"]
    assert data["errors"][0]["sound_id"] == 404

    data = tool_json(call_tool(server, "download_preview", {"sound_id": 7}))
    assert Path(data["saved_to"]).name == "7_Rain.mp3"

    server.config.allow_downloads = False
    assert call_tool(server, "download_preview", {"sound_id": 7})["result"]["isError"]


def test_download_only_from_freesound_hosts(tmp_path):
    with pytest.raises(FreesoundError):
        FreesoundClient("k").download("https://example.com/x.mp3", tmp_path / "a")


# --------------------------------------------------------------------- config / cli
def test_config_precedence(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"api_key": "file", "port": 9000}))
    config = load_config(path, {"port": 9100}, environ={"FREESOUND_API_KEY": "env"}, dotenv_path=tmp_path / "none")
    assert config.api_key == "env"
    assert config.port == 9100


def test_registry_environment_fallback(tmp_path):
    none = tmp_path / "none"
    registry = {"FREESOUND_API_KEY": "from-registry", "MCP_FREESOUND_PORT": "9200"}
    # Variables missing from the process environment come from the registry...
    config = load_config(none, environ={}, registry=registry, dotenv_path=none)
    assert config.api_key == "from-registry"
    assert config.port == 9200
    # ...but the process environment and CLI flags still win.
    config = load_config(
        none, {"port": 9300}, environ={"FREESOUND_API_KEY": "from-env"}, registry=registry, dotenv_path=none
    )
    assert config.api_key == "from-env"
    assert config.port == 9300


def test_registry_reader_is_safe():
    from mcp_freesound.config import read_registry_environment

    assert read_registry_environment(["MCP_FREESOUND_SURELY_UNDEFINED_VARIABLE"]) == {}


def test_cli_options_before_subcommand(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("MCP_FREESOUND_CONFIG", str(tmp_path / "missing.json"))
    assert cli.main(["--port", "9999", "config"]) == 0
    assert json.loads(capsys.readouterr().out)["port"] == 9999


# --------------------------------------------------------------------- HTTP
def http(url, body=None, headers=None, method=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data, {"Content-Type": "application/json", **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def test_http_transport():
    config = Config(api_key="k", transport="http", port=0, auth_token="secret")
    fake = FakeClient()
    httpd = build_http_server(config, lambda: MCPServer(config, fake))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    auth = {"Authorization": "Bearer secret"}
    init = rpc("initialize", {"protocolVersion": "2025-06-18"})
    try:
        assert http(url + "/health")[0] == 200
        assert http(url + "/mcp", init)[0] == 401
        assert http(url + "/mcp", init, {"Authorization": "Bearer wrong"})[0] == 401
        assert http(url + "/mcp", init, {**auth, "Origin": "https://example.com"})[0] == 403

        status, headers, _ = http(url + "/mcp", init, {**auth, "Origin": "http://localhost:3000"})
        assert status == 200
        session = {**auth, "Mcp-Session-Id": headers["Mcp-Session-Id"]}

        notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        assert http(url + "/mcp", notification, session)[0] == 202

        usage = rpc("tools/call", {"name": "get_api_usage", "arguments": {}}, msg_id=2)
        status, _, body = http(url + "/mcp", usage, session)
        assert status == 200
        assert json.loads(body)["result"]["structuredContent"] == {"days": 7}

        assert http(url + "/mcp", rpc("ping"), {**auth, "Mcp-Session-Id": "unknown"})[0] == 404
        assert http(url + "/mcp", None, auth, method="GET")[0] == 405
        assert http(url + "/mcp", None, session, method="DELETE")[0] == 204
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_http_requires_token():
    with pytest.raises(ValueError):
        build_http_server(Config(api_key="k", port=0), lambda: None)


# --------------------------------------------------------------------- stdio
def test_stdio_launcher_subprocess(tmp_path):
    env = dict(os.environ, FREESOUND_API_KEY="dummy", MCP_FREESOUND_CONFIG=str(tmp_path / "c.json"))
    messages = [
        rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}),
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        rpc("tools/list", msg_id=2),
    ]
    result = subprocess.run(
        [sys.executable, str(ROOT / "mcp-freesound.py")],
        input="\n".join(json.dumps(m) for m in messages) + "\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
        cwd=tmp_path,
    )
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2], result.stderr
    assert replies[0]["result"]["serverInfo"]["name"] == "mcp-freesound"


# --------------------------------------------------------------------- client snippets
def test_client_snippets_and_desktop_install(tmp_path):
    config = Config(transport="http", auth_token="tok", port=8123)
    assert "Bearer tok" in clients.generic_http_snippet(config)
    assert "--transport http" in clients.claude_code_command(config)

    target = tmp_path / "claude.json"
    target.write_text(json.dumps({"mcpServers": {"other": {}}}))
    clients.install_claude_desktop(Config(), tmp_path / "cfg.json", target)
    assert set(json.loads(target.read_text())["mcpServers"]) == {"other", "freesound"}
    assert list(tmp_path.glob("claude.json.*.bak"))
