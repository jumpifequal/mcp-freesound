"""Configuration handling.

Precedence (lowest to highest):
    built-in defaults < config file < ``.env`` file < environment variables < CLI flags

On Windows, environment variables missing from the process are also looked up in the
registry (user and system variables), see :func:`read_registry_environment`.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

APP_DIR_NAME = "mcp-freesound"
CONFIG_FILE_NAME = "config.json"

TRANSPORTS = ("stdio", "http")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")

# Environment variable -> config attribute
ENV_MAP = {
    "FREESOUND_API_KEY": "api_key",
    "MCP_FREESOUND_TRANSPORT": "transport",
    "MCP_FREESOUND_HOST": "host",
    "MCP_FREESOUND_PORT": "port",
    "MCP_FREESOUND_PATH": "path",
    "MCP_FREESOUND_AUTH_TOKEN": "auth_token",
    "MCP_FREESOUND_ALLOWED_ORIGINS": "allowed_origins",
    "MCP_FREESOUND_TLS_CERT": "tls_cert",
    "MCP_FREESOUND_TLS_KEY": "tls_key",
    "MCP_FREESOUND_DOWNLOAD_DIR": "download_dir",
    "MCP_FREESOUND_ALLOW_DOWNLOADS": "allow_downloads",
    "MCP_FREESOUND_TIMEOUT": "timeout",
    "MCP_FREESOUND_LOG_LEVEL": "log_level",
}


def default_config_dir() -> Path:
    """Return the per-user configuration directory for the current platform."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_DIR_NAME


def default_config_path() -> Path:
    override = os.environ.get("MCP_FREESOUND_CONFIG")
    if override:
        return Path(override).expanduser()
    return default_config_dir() / CONFIG_FILE_NAME


def default_download_dir() -> str:
    return str(Path.home() / "Downloads" / "freesound")


def generate_token() -> str:
    """Generate a random bearer token suitable for the HTTP transport."""
    return secrets.token_urlsafe(32)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    api_key: str = ""
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    path: str = "/mcp"
    auth_token: str = ""
    allowed_origins: list[str] = field(default_factory=list)
    tls_cert: str = ""
    tls_key: str = ""
    download_dir: str = field(default_factory=default_download_dir)
    allow_downloads: bool = True
    timeout: float = 30.0
    log_level: str = "INFO"

    # ------------------------------------------------------------------ helpers
    def update(self, values: dict[str, Any]) -> None:
        """Merge ``values`` into the config, coercing types. Unknown keys are ignored."""
        known = {f.name for f in fields(self)}
        for key, value in values.items():
            if key not in known or value is None:
                continue
            setattr(self, key, self._coerce(key, value))

    @staticmethod
    def _coerce(key: str, value: Any) -> Any:
        if key == "port":
            return int(value)
        if key == "timeout":
            return float(value)
        if key == "allow_downloads":
            return _to_bool(value)
        if key == "allowed_origins":
            if isinstance(value, str):
                return [o.strip() for o in value.split(",") if o.strip()]
            return [str(o) for o in value]
        if key == "transport":
            return str(value).strip().lower()
        if key == "log_level":
            return str(value).strip().upper()
        return str(value)

    def validate(self) -> list[str]:
        """Return a list of human readable problems (empty when the config is usable)."""
        problems = []
        if not self.api_key:
            problems.append("Freesound API key is not set (FREESOUND_API_KEY).")
        if self.transport not in TRANSPORTS:
            problems.append(f"Unknown transport '{self.transport}' (expected one of {TRANSPORTS}).")
        if not 0 < self.port < 65536:
            problems.append(f"Invalid port {self.port}.")
        if not self.path.startswith("/"):
            problems.append("HTTP path must start with '/'.")
        if bool(self.tls_cert) != bool(self.tls_key):
            problems.append("TLS requires both a certificate and a key file.")
        if self.log_level not in LOG_LEVELS:
            problems.append(f"Unknown log level '{self.log_level}'.")
        return problems

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # --------------------------------------------------------------- persistence
    def save(self, path: Path | None = None) -> Path:
        path = path or default_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        if os.name == "posix":
            # The file holds secrets: keep it private to the user.
            os.chmod(path, 0o600)
        return path


def read_config_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read config file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} must contain a JSON object.")
    return data


def read_dotenv(path: Path) -> dict[str, str]:
    """Minimal ``.env`` parser (KEY=VALUE lines, ``#`` comments, optional quotes)."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def env_overrides(environ: dict[str, str]) -> dict[str, Any]:
    return {attr: environ[name] for name, attr in ENV_MAP.items() if environ.get(name)}


# Where Windows stores persistent environment variables (system first, user wins).
_REGISTRY_ENV_KEYS = (
    ("HKEY_LOCAL_MACHINE", r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ("HKEY_CURRENT_USER", "Environment"),
)


def read_registry_environment(names: list[str]) -> dict[str, str]:
    """Read persistent user/system environment variables from the Windows registry.

    MCP clients may start the server with a reduced environment (some only pass a fixed
    allow-list such as PATH and APPDATA), so a variable set in the Windows settings would
    never reach the process. This returns them straight from the registry.
    Returns an empty dict on other platforms.
    """
    if sys.platform != "win32":
        return {}
    import winreg

    values: dict[str, str] = {}
    for hive_name, path in _REGISTRY_ENV_KEYS:
        try:
            key = winreg.OpenKey(getattr(winreg, hive_name), path)
        except OSError:
            continue
        with key:
            for name in names:
                try:
                    value, kind = winreg.QueryValueEx(key, name)
                except OSError:
                    continue
                if kind == winreg.REG_EXPAND_SZ:
                    value = winreg.ExpandEnvironmentStrings(value)
                if isinstance(value, str) and value:
                    values[name] = value
    return values


def effective_environment(environ: dict[str, str] | None = None, registry: dict[str, str] | None = None) -> dict:
    """Process environment, completed with registry values for variables it lacks."""
    env = dict(os.environ) if environ is None else dict(environ)
    missing = [name for name in ENV_MAP if not env.get(name)]
    if missing:
        stored = read_registry_environment(missing) if registry is None else registry
        env.update({name: stored[name] for name in missing if stored.get(name)})
    return env


def load_config(
    config_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
    dotenv_path: Path | None = None,
    registry: dict[str, str] | None = None,
) -> Config:
    """Build the effective configuration from all sources.

    ``registry`` replaces the Windows registry lookup (used by tests); when ``environ`` is
    given explicitly and ``registry`` is not, the registry is not consulted.
    """
    cfg = Config()
    cfg.update(read_config_file(config_path or default_config_path()))
    cfg.update(env_overrides(read_dotenv(dotenv_path or Path.cwd() / ".env")))
    if environ is not None and registry is None:
        registry = {}
    cfg.update(env_overrides(effective_environment(environ, registry)))
    if overrides:
        cfg.update(overrides)
    return cfg
