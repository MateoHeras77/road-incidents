"""Open511 adapter (British Columbia / DriveBC).

DriveBC implements the Open511 standard:
    https://api.open511.gov.bc.ca/events?format=json
Geometry is already GeoJSON; schedules come as ISO interval strings.
"""
from __future__ import annotations

from typing import List, Optional

from ..highway import classify_highway
from ..models import (
    CLASS_ACCIDENT,
    CLASS_CONSTRUCTION,
    CLASS_CONDITION,
    CLASS_OTHER,
    CLASS_SPECIAL,
    RoadEvent,
)
from .base import http_get_json, ts_from_iso

BC_EVENTS_URL = "https://api.open511.gov.bc.ca/events?format=json&limit=500"

_EVENT_CLASS = {
    "CONSTRUCTION": CLASS_CONSTRUCTION,
    "INCIDENT": CLASS_ACCIDENT,
    "SPECIAL_EVENT": CLASS_SPECIAL,
    "WEATHER_CONDITION": CLASS_CONDITION,
    "ROAD_CONDITION": CLASS_CONDITION,
}


def _interval_bounds(schedule: dict):
    intervals = (schedule or {}).get("intervals") or []
    if not intervals:
        return None, None
    first = str(intervals[0])
    start, _, end = first.partition("/")
    return ts_from_iso(start), ts_from_iso(end or None)


def _full_closure(roads: list, description: str) -> bool:
    for road in roads or []:
        if str(road.get("state", "")).upper() == "CLOSED":
            return True
    return "road closed" in (description or "").lower()


def parse_events(payload: dict) -> List[RoadEvent]:
    """Parse an Open511 events FeatureCollection-like payload."""
    events: List[RoadEvent] = []
    for rec in (payload or {}).get("events", []):
        roads = rec.get("roads") or []
        roadway = roads[0].get("name") if roads else None
        is_hw, road_no = classify_highway(roadway)
        start, end = _interval_bounds(rec.get("schedule"))
        subtypes = rec.get("event_subtypes") or []
        events.append(
            RoadEvent(
                source="bc",
                source_event_id=rec.get("id"),
                province="British Columbia",
                event_class=_EVENT_CLASS.get(rec.get("event_type"), CLASS_OTHER),
                roadway_name=roadway,
                road_number=road_no,
                is_highway=is_hw,
                is_full_closure=_full_closure(roads, rec.get("description", "")),
                direction=roads[0].get("direction") if roads else None,
                severity=rec.get("severity"),
                headline=rec.get("headline"),
                description=rec.get("description"),
                raw_event_type=rec.get("event_type"),
                raw_event_subtype=subtypes[0] if subtypes else None,
                starts_at=start,
                planned_end_at=end,
                reported_at=ts_from_iso(rec.get("created")),
                last_updated=ts_from_iso(rec.get("updated")),
                geojson=rec.get("geography"),
                raw=rec,
            )
        )
    return events


def fetch_events(url: str = BC_EVENTS_URL) -> List[RoadEvent]:
    return parse_events(http_get_json(url))
