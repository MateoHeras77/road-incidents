"""Supabase sink: writes normalized records via security-definer RPCs.

Geometry is built server-side from GeoJSON (ST_GeomFromGeoJSON), so the
ingester only sends plain JSON. Large feeds are loaded as clear-then-append
in batches to stay under the database statement timeout. Requires the
service_role key.
"""
from __future__ import annotations

from typing import Iterable, List

from supabase import Client, create_client

from .models import Camera, RoadCondition, RoadEvent

BATCH_SIZE = 150


def _batches(items: list, size: int = BATCH_SIZE) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class SupabaseSink:
    def __init__(self, url: str, service_key: str):
        self.client: Client = create_client(url, service_key)

    def _rpc(self, fn: str, params: dict):
        return self.client.rpc(fn, params).execute().data

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
