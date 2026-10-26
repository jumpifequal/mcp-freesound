# Tests

Everything runs inside this folder; outputs go to `test/_out/` (git-ignored).

```bash
python -m venv test/.venv
test/.venv/Scripts/python -m pip install pytest ruff build      # Linux/macOS: test/.venv/bin/python

# offline unit + integration tests (fake Freesound client, real HTTP and stdio transports)
test/.venv/Scripts/python -m pytest -p no:cacheprovider --basetemp=test/_out/pytest test

# end-to-end: start the real CLI over HTTP + bearer token (dummy key, expects a clean 401 tool error)
test/.venv/Scripts/python test/smoke_http.py

# open the GUI, visit every tab, save a throwaway config
test/.venv/Scripts/python test/smoke_gui.py

# lint / format / build
test/.venv/Scripts/ruff check . && test/.venv/Scripts/ruff format --check .
test/.venv/Scripts/python -m build --outdir test/_out/dist .

# maintainers: regenerate assets/*.png from the SVGs (needs Edge or Chrome)
python test/render_assets.py
```

| File | What it checks |
|---|---|
| `test_server.py` | MCP handshake, 13 tools, error mapping, attribution, downloads, config precedence, CLI, HTTP auth/Origin/sessions, stdio launcher, client snippets |
| `smoke_http.py` | The real server process over HTTP, including a live call to Freesound |
| `smoke_gui.py` | The Tkinter GUI builds, switches tabs, generates snippets and saves |
| `render_assets.py` | Not a test: renders the logo and infographic PNGs |
