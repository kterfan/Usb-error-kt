"""Small, careful HTTPS client: only known official hosts, timeouts, size cap, no data sent about the PC."""

from __future__ import annotations

import json
import urllib.request
from typing import Callable, Optional
from urllib.parse import urlparse

from . import __version__

ALLOWED_HOSTS = {"www.asus.com"}
USER_AGENT = f"USB-Fixer/{__version__} (+https://github.com/kterfan/Usb-error-kt)"
MAX_BYTES = 3 * 1024 * 1024

Fetch = Callable[[str], Optional[str]]


class NetError(Exception):
    pass


def fetch_text(url: str, timeout: int = 15) -> str:
    parts = urlparse(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        raise NetError(f"blocked url: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # certificate checks stay on (default context)
            data = resp.read(MAX_BYTES + 1)
    except OSError as exc:  # URLError, timeouts, TLS errors
        raise NetError(str(exc)) from exc
    if len(data) > MAX_BYTES:
        raise NetError("response too large")
    return data.decode("utf-8", errors="replace")


def fetch_json(url: str, fetch: Optional[Fetch] = None) -> dict:
    text = (fetch or fetch_text)(url)
    if text is None:
        raise NetError("no response")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise NetError(f"bad json: {exc}") from exc
