"""Open the configuration GUI on a throwaway config, visit every tab, save and close.

python test/smoke_gui.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "test" / "_out"
sys.path.insert(0, str(ROOT / "src"))

import tkinter as tk  # noqa: E402
from tkinter import ttk  # noqa: E402

from mcp_freesound.gui import ConfigApp  # noqa: E402


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    config_path = OUT / "gui_config.json"
    root = tk.Tk()
    app = ConfigApp(root, config_path)
    app.v_api_key.set("dummy-key")
    app.v_transport.set("http")
    app._on_transport_change()
    app.v_token.set("example-token")
    notebook = next(w for w in root.winfo_children() if isinstance(w, ttk.Notebook))

    def visit(index=0):
        if index < len(notebook.tabs()):
            notebook.select(index)
            root.after(200, visit, index + 1)
            return
        snippet = app.t_desktop.get("1.0", "end")
        assert "mcp-remote" in snippet, snippet
        assert app.save(), "save failed"
        saved = json.loads(config_path.read_text())
        assert saved["transport"] == "http" and saved["auth_token"] == "example-token"
        print(f"GUI ok: {len(notebook.tabs())} tabs visited, config saved to {config_path.relative_to(ROOT)}")
        root.destroy()

    root.after(300, visit)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
