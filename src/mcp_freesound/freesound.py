"""Minimal Freesound API v2 client built on :mod:`urllib` (no third-party dependencies)."""

from __future__ import annotations

import json
import logging
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from mcp_freesound import __version__

log = logging.getLogger(__name__)

BASE_URL = "https://freesound.org/apiv2"
USER_AGENT = f"mcp-freesound/{__version__} (+https://freesound.org)"

# Preview files are served from Freesound's CDN; only download from these hosts.
PREVIEW_HOSTS = ("freesound.org", "cdn.freesound.org")


class FreesoundError(Exception):
    """Raised for any failure talking to the Freesound API."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


_STATUS_HINTS = {
    401: "Authentication failed: check your Freesound API key.",
    403: "Access forbidden: this resource may require OAuth2 or your key lacks permission.",
    404: "Resource not found.",
    429: "Rate limit exceeded: wait before sending more requests.",
}


class FreesoundClient:
    """Thin synchronous wrapper around the Freesound REST API."""

    def __init__(self, api_key: str, timeout: float = 30.0, base_url: str = BASE_URL):
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")

    # ----------------------------------------------------------------- plumbing
    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """GET ``endpoint`` (relative to the API root) and return decoded JSON."""
        if not self.api_key:
            raise FreesoundError("Freesound API key is not configured.")
        query = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(
            url,
            headers={
                # Token goes in a header so it never appears in URLs or logs.
                "Authorization": f"Token {self.api_key}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        log.debug("GET %s", url)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = _error_detail(exc)
            hint = _STATUS_HINTS.get(exc.code, "")
            message = f"Freesound API error {exc.code} for /{endpoint.strip('/')}/"
            message += "".join(f" {part}" for part in (hint, detail) if part)
            raise FreesoundError(message, exc.code) from exc
        except urllib.error.URLError as exc:
            raise FreesoundError(f"Network error contacting Freesound: {exc.reason}") from exc
        except TimeoutError as exc:
            raise FreesoundError("Request to Freesound timed out.") from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise FreesoundError("Invalid JSON response from Freesound.") from exc

    def download(self, url: str, destination: Path) -> int:
        """Download a public preview file to ``destination``. Returns the size in bytes."""
        host = urllib.parse.urlparse(url).hostname or ""
        if urllib.parse.urlparse(url).scheme != "https" or not any(
            host == h or host.endswith("." + h) for h in PREVIEW_HOSTS
        ):
            raise FreesoundError(f"Refusing to download from untrusted URL host '{host}'.")
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(destination.suffix + ".part")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response, tmp.open("wb") as fh:
                shutil.copyfileobj(response, fh)
            tmp.replace(destination)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            tmp.unlink(missing_ok=True)
            raise FreesoundError(f"Download failed: {exc}") from exc
        return destination.stat().st_size

    # ---------------------------------------------------------------- endpoints
    def search(self, **params: Any) -> dict:
        return self.get("search/", params)

    def sound(self, sound_id: int, fields: str | None = None) -> dict:
        return self.get(f"sounds/{int(sound_id)}/", {"fields": fields})

    def similar(self, sound_id: int, **params: Any) -> dict:
        return self.get(f"sounds/{int(sound_id)}/similar/", params)

    def analysis(self, sound_id: int, fields: str | None = None) -> dict:
        return self.get(f"sounds/{int(sound_id)}/analysis/", {"fields": fields})

    def comments(self, sound_id: int, **params: Any) -> dict:
        return self.get(f"sounds/{int(sound_id)}/comments/", params)

    def user(self, username: str) -> dict:
        return self.get(f"users/{_quote_segment(username)}/")

    def user_sounds(self, username: str, **params: Any) -> dict:
        return self.get(f"users/{_quote_segment(username)}/sounds/", params)

    def user_packs(self, username: str, **params: Any) -> dict:
        return self.get(f"users/{_quote_segment(username)}/packs/", params)

    def pack(self, pack_id: int) -> dict:
        return self.get(f"packs/{int(pack_id)}/")

    def pack_sounds(self, pack_id: int, **params: Any) -> dict:
        return self.get(f"packs/{int(pack_id)}/sounds/", params)

    def usage(self, num_days: int = 7) -> dict:
        return self.get("usage/", {"num_days": num_days})


def _quote_segment(value: str) -> str:
    value = value.strip()
    if not value:
        raise FreesoundError("Username must not be empty.")
    return urllib.parse.quote(value, safe="")


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read() or b"{}")
    except (json.JSONDecodeError, OSError):
        return ""
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("error")
        if detail:
            return str(detail)
    return ""


_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_filename(name: str, max_length: int = 120) -> str:
    """Turn an arbitrary sound name into a safe file name component."""
    cleaned = _UNSAFE_FILENAME.sub("_", name).strip(" ._") or "sound"
    return cleaned[:max_length]
