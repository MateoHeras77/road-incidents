"""Supabase sink: writes normalized records via security-definer RPCs.

Geometry is built server-side from GeoJSON (ST_GeomFromGeoJSON), so the
ingester only sends plain JSON. Large feeds are loaded as clear-then-append
in batches to stay under the database statement timeout. Requires the
service_role key.

Every RPC is retried on transient failures: the Supabase gateway returns a
504 for ~1-3% of calls even when the database is idle, and one such blip
must not fail a whole run. All RPCs are idempotent (clear is a plain delete,
append uses ON CONFLICT DO NOTHING) so retrying is always safe.
"""
from __future__ import annotations

import time
from typing import Iterable, List

import httpx
from postgrest.exceptions import APIError
from supabase import Client, create_client

from .models import Camera, RoadCondition, RoadEvent

BATCH_SIZE = 150
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = (2, 5, 10)


def _batches(items: list, size: int = BATCH_SIZE) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, APIError):
        code = exc.code
        try:
            return 500 <= int(code) < 600
        except (TypeError, ValueError):
            return False
    return False


class SupabaseSink:
    def __init__(self, url: str, service_key: str):
        self.client: Client = create_client(url, service_key)

    def _rpc(self, fn: str, params: dict):
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self.client.rpc(fn, params).execute().data
            except Exception as exc:
                if attempt == MAX_ATTEMPTS or not _is_transient(exc):
                    raise
                delay = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS)) - 1]
                print(f"  ! {fn}: transient error ({exc}); retry {attempt}/{MAX_ATTEMPTS - 1} in {delay}s")
                time.sleep(delay)

    def _replace(self, clear_fn: str, append_fn: str, source: str, payloads: List[dict]) -> int:
        self._rpc(clear_fn, {"p_source": source})
        total = 0
        for batch in _batches(payloads):
            data = self._rpc(append_fn, {"payload": batch})
            total += data if isinstance(data, int) else 0
        return total

    def replace_events(self, source: str, events: List[RoadEvent]) -> int:
        return self._replace(
            "clear_road_events", "append_road_events", source, [e.to_payload() for e in events]
        )

    def replace_cameras(self, source: str, cameras: List[Camera]) -> int:
        return self._replace(
            "clear_cameras", "append_cameras", source, [c.to_payload() for c in cameras]
        )

    def replace_conditions(self, source: str, conditions: List[RoadCondition]) -> int:
        return self._replace(
            "clear_road_conditions", "append_road_conditions", source,
            [c.to_payload() for c in conditions],
        )

    def upsert_facilities(self, facilities: List[dict]) -> int:
        data = self._rpc("upsert_facilities", {"payload": facilities})
        return data if isinstance(data, int) else 0
