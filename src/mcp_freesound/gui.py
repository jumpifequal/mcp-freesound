"""Tkinter configuration GUI (standard library only)."""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover - Python built without Tk
    tk = None  # type: ignore[assignment]

from mcp_freesound import __version__
from mcp_freesound.clients import (
    claude_code_command,
    claude_desktop_config_path,
    claude_desktop_snippet,
    generic_http_snippet,
    install_claude_desktop,
    server_command,
)
from mcp_freesound.config import LOG_LEVELS, Config, default_config_path, generate_token, read_config_file

API_KEY_URL = "https://freesound.org/apiv2/apply/"
PAD = {"padx": 6, "pady": 4}


class ConfigApp:
    def __init__(self, root: tk.Tk, config_path: Path):
        self.root = root
        self.config_path = config_path
        self.config = self._load()
        self.process: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()

        root.title(f"mcp-freesound {__version__} - configuration")
        root.minsize(680, 520)
        self._build_vars()
        self._build_ui()
        self._refresh_snippets()
        self._on_transport_change()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(200, self._drain_log)

    # -------------------------------------------------------------------- state
    def _load(self) -> Config:
        # Only the file is edited here: environment overrides must not leak into it.
        cfg = Config()
        try:
            cfg.update(read_config_file(self.config_path))
        except ValueError as exc:
            messagebox.showwarning("Config file", str(exc))
        return cfg

    def _build_vars(self) -> None:
        c = self.config
        self.v_api_key = tk.StringVar(value=c.api_key)
        self.v_show_key = tk.BooleanVar(value=False)
        self.v_download_dir = tk.StringVar(value=c.download_dir)
        self.v_allow_downloads = tk.BooleanVar(value=c.allow_downloads)
        self.v_timeout = tk.StringVar(value=str(c.timeout))
        self.v_transport = tk.StringVar(value=c.transport)
        self.v_host = tk.StringVar(value=c.host)
        self.v_port = tk.StringVar(value=str(c.port))
        self.v_path = tk.StringVar(value=c.path)
        self.v_token = tk.StringVar(value=c.auth_token)
        self.v_show_token = tk.BooleanVar(value=False)
        self.v_origins = tk.StringVar(value=", ".join(c.allowed_origins))
        self.v_tls_cert = tk.StringVar(value=c.tls_cert)
        self.v_tls_key = tk.StringVar(value=c.tls_key)
        self.v_log_level = tk.StringVar(value=c.log_level)
        self.v_status = tk.StringVar(value=f"Config file: {self.config_path}")
        for var in (self.v_transport, self.v_host, self.v_port, self.v_path, self.v_token, self.v_tls_cert):
            var.trace_add("write", lambda *_: self._refresh_snippets())

    def _collect(self) -> Config:
        """Read the form into a new Config (raises ValueError on bad input)."""
        cfg = Config()
        cfg.update(
            {
                "api_key": self.v_api_key.get().strip(),
                "download_dir": self.v_download_dir.get().strip(),
                "allow_downloads": self.v_allow_downloads.get(),
                "timeout": self.v_timeout.get().strip() or "30",
                "transport": self.v_transport.get(),
                "host": self.v_host.get().strip(),
                "port": self.v_port.get().strip() or "8000",
                "path": self.v_path.get().strip() or "/mcp",
                "auth_token": self.v_token.get().strip(),
                "allowed_origins": self.v_origins.get(),
                "tls_cert": self.v_tls_cert.get().strip(),
                "tls_key": self.v_tls_key.get().strip(),
                "log_level": self.v_log_level.get(),
            }
        )
        return cfg

    # ----------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        notebook.add(self._tab_freesound(notebook), text="Freesound")
        notebook.add(self._tab_server(notebook), text="Server")
        notebook.add(self._tab_clients(notebook), text="Client setup")
        notebook.add(self._tab_run(notebook), text="Run")

        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(bar, textvariable=self.v_status, foreground="#555").pack(side="left")
        ttk.Button(bar, text="Save", command=self.save).pack(side="right")
        ttk.Button(bar, text="Reload", command=self.reload).pack(side="right", padx=6)

    def _tab_freesound(self, parent) -> ttk.Frame:
        f = ttk.Frame(parent, padding=10)
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="API key").grid(row=0, column=0, sticky="w", **PAD)
        self.e_key = ttk.Entry(f, textvariable=self.v_api_key, show="*")
        self.e_key.grid(row=0, column=1, sticky="ew", **PAD)
        ttk.Checkbutton(
            f,
            text="Show",
            variable=self.v_show_key,
            command=lambda: self.e_key.configure(show="" if self.v_show_key.get() else "*"),
        ).grid(row=0, column=2, **PAD)
        buttons = ttk.Frame(f)
        buttons.grid(row=1, column=1, sticky="w")
        ttk.Button(buttons, text="Test key", command=self.test_key).pack(side="left", **PAD)
        ttk.Button(buttons, text="Get an API key...", command=lambda: webbrowser.open(API_KEY_URL)).pack(
            side="left", **PAD
        )

        ttk.Label(f, text="Download folder").grid(row=2, column=0, sticky="w", **PAD)
        ttk.Entry(f, textvariable=self.v_download_dir).grid(row=2, column=1, sticky="ew", **PAD)
        ttk.Button(f, text="Browse...", command=self._browse_dir).grid(row=2, column=2, **PAD)
        ttk.Checkbutton(f, text="Allow the download_preview tool", variable=self.v_allow_downloads).grid(
            row=3, column=1, sticky="w", **PAD
        )
        ttk.Label(f, text="Request timeout (s)").grid(row=4, column=0, sticky="w", **PAD)
        ttk.Spinbox(f, from_=5, to=300, textvariable=self.v_timeout, width=8).grid(row=4, column=1, sticky="w", **PAD)
        ttk.Label(
            f,
            text="Environment variables (e.g. FREESOUND_API_KEY) override these values at runtime.",
            foreground="#555",
        ).grid(row=5, column=0, columnspan=3, sticky="w", **PAD)
        return f

    def _tab_server(self, parent) -> ttk.Frame:
        f = ttk.Frame(parent, padding=10)
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Transport").grid(row=0, column=0, sticky="w", **PAD)
        radios = ttk.Frame(f)
        radios.grid(row=0, column=1, sticky="w")
        for value, label in (("stdio", "stdio (local client launches the server)"), ("http", "HTTP + bearer token")):
            ttk.Radiobutton(
                radios, text=label, value=value, variable=self.v_transport, command=self._on_transport_change
            ).pack(side="left", **PAD)

        self.http_frame = ttk.LabelFrame(f, text="HTTP settings", padding=8)
        self.http_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=8)
        h = self.http_frame
        h.columnconfigure(1, weight=1)
        rows = [("Host", self.v_host), ("Port", self.v_port), ("Path", self.v_path)]
        for i, (label, var) in enumerate(rows):
            ttk.Label(h, text=label).grid(row=i, column=0, sticky="w", **PAD)
            ttk.Entry(h, textvariable=var).grid(row=i, column=1, sticky="ew", **PAD)

        ttk.Label(h, text="Bearer token").grid(row=3, column=0, sticky="w", **PAD)
        self.e_token = ttk.Entry(h, textvariable=self.v_token, show="*")
        self.e_token.grid(row=3, column=1, sticky="ew", **PAD)
        tb = ttk.Frame(h)
        tb.grid(row=3, column=2, sticky="w")
        ttk.Checkbutton(
            tb,
            text="Show",
            variable=self.v_show_token,
            command=lambda: self.e_token.configure(show="" if self.v_show_token.get() else "*"),
        ).pack(side="left")
        ttk.Button(tb, text="Generate", command=lambda: self.v_token.set(generate_token())).pack(side="left", padx=4)
        ttk.Button(tb, text="Copy", command=lambda: self._copy(self.v_token.get())).pack(side="left")

        ttk.Label(h, text="Allowed origins").grid(row=4, column=0, sticky="w", **PAD)
        ttk.Entry(h, textvariable=self.v_origins).grid(row=4, column=1, sticky="ew", **PAD)
        ttk.Label(h, text="comma separated", foreground="#555").grid(row=4, column=2, sticky="w")
        for i, (label, var) in enumerate((("TLS certificate", self.v_tls_cert), ("TLS key", self.v_tls_key)), start=5):
            ttk.Label(h, text=label).grid(row=i, column=0, sticky="w", **PAD)
            ttk.Entry(h, textvariable=var).grid(row=i, column=1, sticky="ew", **PAD)
            ttk.Button(h, text="Browse...", command=lambda v=var: self._browse_file(v)).grid(row=i, column=2, **PAD)

        ttk.Label(f, text="Log level").grid(row=2, column=0, sticky="w", **PAD)
        ttk.Combobox(f, textvariable=self.v_log_level, values=LOG_LEVELS, state="readonly", width=10).grid(
            row=2, column=1, sticky="w", **PAD
        )
        return f

    def _tab_clients(self, parent) -> ttk.Frame:
        f = ttk.Frame(parent, padding=10)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        f.rowconfigure(4, weight=1)
        ttk.Label(f, text="Claude Desktop (claude_desktop_config.json)").grid(row=0, column=0, sticky="w")
        self.t_desktop = tk.Text(f, height=10, wrap="none", font=("Consolas", 9))
        self.t_desktop.grid(row=1, column=0, sticky="nsew")
        row = ttk.Frame(f)
        row.grid(row=2, column=0, sticky="w", pady=4)
        ttk.Button(row, text="Copy", command=lambda: self._copy(self.t_desktop.get("1.0", "end"))).pack(side="left")
        ttk.Button(row, text="Add to Claude Desktop config...", command=self.install_desktop).pack(side="left", padx=6)

        ttk.Label(f, text="Claude Code / other clients").grid(row=3, column=0, sticky="w")
        self.t_other = tk.Text(f, height=8, wrap="word", font=("Consolas", 9))
        self.t_other.grid(row=4, column=0, sticky="nsew")
        ttk.Button(f, text="Copy", command=lambda: self._copy(self.t_other.get("1.0", "end"))).grid(
            row=5, column=0, sticky="w", pady=4
        )
        ttk.Label(
            f,
            text="Snippets reflect the current form. Save first: the stdio server reads the saved config file.",
            foreground="#555",
        ).grid(row=6, column=0, sticky="w")
        return f

    def _tab_run(self, parent) -> ttk.Frame:
        f = ttk.Frame(parent, padding=10)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        row = ttk.Frame(f)
        row.grid(row=0, column=0, sticky="w")
        self.b_start = ttk.Button(row, text="Start HTTP server", command=self.start_server)
        self.b_start.pack(side="left")
        self.b_stop = ttk.Button(row, text="Stop", command=self.stop_server, state="disabled")
        self.b_stop.pack(side="left", padx=6)
        ttk.Label(row, text="Saves the config, then runs the HTTP transport.", foreground="#555").pack(side="left")
        self.t_log = tk.Text(f, height=16, wrap="word", font=("Consolas", 9), state="disabled")
        self.t_log.grid(row=1, column=0, sticky="nsew", pady=6)
        return f

    # ------------------------------------------------------------------ actions
    def _on_transport_change(self) -> None:
        state = "normal" if self.v_transport.get() == "http" else "disabled"
        for child in self.http_frame.winfo_children():
            for widget in [child, *child.winfo_children()]:
                try:
                    widget.configure(state=state)
                except tk.TclError:
                    pass
        self._refresh_snippets()

    def _refresh_snippets(self) -> None:
        if not hasattr(self, "t_desktop"):
            return
        try:
            cfg = self._collect()
        except ValueError:
            return
        other = claude_code_command(cfg, self.config_path)
        if cfg.transport == "http":
            other += "\n\nGeneric HTTP client config:\n" + generic_http_snippet(cfg)
        for widget, text in ((self.t_desktop, claude_desktop_snippet(cfg, self.config_path)), (self.t_other, other)):
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", text)

    def _browse_dir(self) -> None:
        path = filedialog.askdirectory(initialdir=self.v_download_dir.get() or str(Path.home()))
        if path:
            self.v_download_dir.set(path)

    def _browse_file(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(filetypes=[("PEM files", "*.pem *.crt *.key"), ("All files", "*.*")])
        if path:
            var.set(path)

    def _copy(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text.strip())
        self.v_status.set("Copied to clipboard.")

    def save(self) -> bool:
        try:
            cfg = self._collect()
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc))
            return False
        problems = cfg.validate()
        if cfg.transport == "http" and not cfg.auth_token:
            problems.append("HTTP transport needs a bearer token (click Generate).")
        if problems and not messagebox.askyesno("Configuration problems", "\n".join(problems) + "\n\nSave anyway?"):
            return False
        self.config = cfg
        path = cfg.save(self.config_path)
        self.v_status.set(f"Saved to {path}")
        return True

    def reload(self) -> None:
        self.config = self._load()
        self._build_vars()
        for widget in self.root.winfo_children():
            widget.destroy()
        self._build_ui()
        self._refresh_snippets()
        self._on_transport_change()

    def test_key(self) -> None:
        from mcp_freesound.cli import check_api_key

        cfg = self._collect()
        self.v_status.set("Testing API key...")

        def worker():
            ok, message = check_api_key(cfg)
            self.root.after(0, lambda: self._show_test_result(ok, message))

        threading.Thread(target=worker, daemon=True).start()

    def _show_test_result(self, ok: bool, message: str) -> None:
        self.v_status.set(message)
        (messagebox.showinfo if ok else messagebox.showerror)("API key test", message)

    def install_desktop(self) -> None:
        target = claude_desktop_config_path()
        if not messagebox.askyesno(
            "Claude Desktop",
            f"Add the 'freesound' server to:\n{target}\n\nA timestamped backup of the existing file is kept. "
            "Restart Claude Desktop afterwards.",
        ):
            return
        if not self.save():
            return
        try:
            path = install_claude_desktop(self.config, self.config_path, target)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Claude Desktop", f"Could not update the config: {exc}")
            return
        self.v_status.set(f"Updated {path}")

    # ------------------------------------------------------------- server runner
    def start_server(self) -> None:
        if self.process is not None:
            return
        self.v_transport.set("http")
        self._on_transport_change()
        if not self.save():
            return
        command = server_command(self.config_path, "http")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=flags
        )
        self.b_start.configure(state="disabled")
        self.b_stop.configure(state="normal")
        threading.Thread(target=self._pump, args=(self.process,), daemon=True).start()

    def _pump(self, process: subprocess.Popen) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            self.log_queue.put(line)
        self.log_queue.put(f"[server exited with code {process.wait()}]\n")
        self.root.after(0, self._on_server_exit)

    def _on_server_exit(self) -> None:
        self.process = None
        self.b_start.configure(state="normal")
        self.b_stop.configure(state="disabled")

    def stop_server(self) -> None:
        if self.process is not None:
            self.process.terminate()

    def _drain_log(self) -> None:
        lines = []
        while not self.log_queue.empty():
            lines.append(self.log_queue.get_nowait())
        if lines:
            self.t_log.configure(state="normal")
            self.t_log.insert("end", "".join(lines))
            self.t_log.see("end")
            self.t_log.configure(state="disabled")
        self.root.after(200, self._drain_log)

    def _on_close(self) -> None:
        if self.process is not None:
            self.process.terminate()
        self.root.destroy()


def run_gui(config_path: Path | None = None) -> int:
    if tk is None:
        print("error: tkinter is not available in this Python installation.", file=sys.stderr)
        return 1
    root = tk.Tk()
    ConfigApp(root, config_path or default_config_path())
    root.mainloop()
    return 0


def main() -> int:
    """Entry point of the ``mcp-freesound-gui`` script."""
    import argparse

    parser = argparse.ArgumentParser(prog="mcp-freesound-gui", description="mcp-freesound configuration GUI")
    parser.add_argument("--config", type=Path, help="Config file to edit.")
    return run_gui(parser.parse_args().config)


if __name__ == "__main__":
    sys.exit(main())
