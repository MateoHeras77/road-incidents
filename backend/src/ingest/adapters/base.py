"""Shared helpers for source adapters: HTTP fetching and time parsing."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import requests

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 30


def http_get_json(url: str, *, timeout: int = DEFAULT_TIMEOUT) -> Any:
    """GET a URL with a browser User-Agent (some 511 WAFs block default UAs)."""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def ts_from_epoch(value: Any) -> Optional[datetime]:
    """Convert a Unix epoch (seconds) into a tz-aware UTC datetime."""
    if value in (None, "", 0):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (ValueError, OSError, TypeError):
        return None


def ts_from_iso(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 string into a tz-aware datetime (assume UTC if naive)."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
