"""End-to-end smoke test: start the real CLI with the HTTP transport and talk to it.

    python test/smoke_http.py [launcher...]

Default launcher: ``python mcp-freesound.py``. Uses a dummy Freesound key, so the live
search is expected to come back as a clean tool error (401 from Freesound).
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "test" / "_out"
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


def post(body, headers):
    request = urllib.request.Request(
        BASE + "/mcp", json.dumps(body).encode(), {"Content-Type": "application/json", **headers}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"null"), response.headers.get("Mcp-Session-Id")
    except urllib.error.HTTPError as exc:
        return exc.code, None, None


def main() -> int:
    launcher = sys.argv[1:] or [sys.executable, str(ROOT / "mcp-freesound.py")]
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, FREESOUND_API_KEY="dummy-key", MCP_FREESOUND_CONFIG=str(OUT / "smoke_config.json"))
    token = subprocess.run([*launcher, "token"], capture_output=True, text=True, env=env, check=True).stdout.strip()
    log = (OUT / "smoke_http.log").open("w")
    server = subprocess.Popen(
        [*launcher, "serve", "--transport", "http", "--port", str(PORT), "--auth-token", token],
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=OUT,
    )
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(BASE + "/health", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        print("health: ok")
        print("no token ->", post({"jsonrpc": "2.0", "id": 1, "method": "ping"}, {})[0])
        auth = {"Authorization": f"Bearer {token}"}
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
        status, body, session = post(init, auth)
        print("initialize ->", status, body["result"]["serverInfo"], "session:", bool(session))
        call = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "search_sounds", "arguments": {"query": "rain"}},
        }
        status, body, _ = post(call, {**auth, "Mcp-Session-Id": session})
        print("live search, dummy key ->", status, "isError:", body["result"]["isError"])
        print("   ", body["result"]["content"][0]["text"][:100])
    finally:
        server.terminate()
        server.wait(10)
        log.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
