"""Normalized data models shared across all source adapters.

Every provincial feed is mapped into these structures so the rest of the
pipeline (highway filter, database sink, dashboard) is source-agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

# Canonical event classes used across all provinces.
CLASS_CLOSURE = "closure"
CLASS_ACCIDENT = "accident"
CLASS_CONSTRUCTION = "construction"
CLASS_RESTRICTION = "restriction"
CLASS_SPECIAL = "special"
CLASS_INFO = "info"
CLASS_CONDITION = "condition"
CLASS_OTHER = "other"


def _clean(value: Any) -> Any:
    """Drop empty strings so they land as NULL instead of '' in the DB."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


@dataclass
class RoadEvent:
    """A single road event (closure, accident, construction, ...)."""

    source: str
    source_event_id: str
    province: str
    event_class: str
    roadway_name: Optional[str] = None
    road_number: Optional[str] = None
    is_highway: bool = False
    is_full_closure: bool = False
    direction: Optional[str] = None
    severity: Optional[str] = None
    headline: Optional[str] = None
    description: Optional[str] = None
    raw_event_type: Optional[str] = None
    raw_event_subtype: Optional[str] = None
    restrictions: Optional[dict] = None
    starts_at: Optional[datetime] = None
    planned_end_at: Optional[datetime] = None
    reported_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    geojson: Optional[dict] = None
    raw: Optional[dict] = None

    @property
    def is_scheduled(self) -> bool:
        """True when the event starts in the future (planned, not yet active)."""
        if self.starts_at is None:
            return False
        return self.starts_at > datetime.now(timezone.utc)

    def to_payload(self, include_raw: bool = True) -> dict:
        """JSON-serializable dict consumed by the `replace_road_events` RPC."""
        return {
            "source": self.source,
            "source_event_id": str(self.source_event_id),
            "province": self.province,
            "event_class": self.event_class,
            "raw_event_type": _clean(self.raw_event_type),
            "raw_event_subtype": _clean(self.raw_event_subtype),
            "roadway_name": _clean(self.roadway_name),
            "road_number": _clean(self.road_number),
            "is_highway": bool(self.is_highway),
            "is_full_closure": bool(self.is_full_closure),
            "direction": _clean(self.direction),
            "severity": _clean(self.severity),
            "headline": _clean(self.headline),
            "description": _clean(self.description),
            "restrictions": self.restrictions or None,
            "starts_at": _iso(self.starts_at),
            "planned_end_at": _iso(self.planned_end_at),
            "is_scheduled": self.is_scheduled,
            "reported_at": _iso(self.reported_at),
            "last_updated": _iso(self.last_updated),
            "geojson": self.geojson,
            "raw": self.raw if include_raw else None,
        }


@dataclass
class Camera:
    """A traffic camera location."""

    source: str
    source_camera_id: str
    province: str
    title: Optional[str] = None
    roadway: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    views: Optional[list] = None
    last_updated: Optional[datetime] = None
    raw: Optional[dict] = None

    def to_payload(self, include_raw: bool = True) -> dict:
        return {
            "source": self.source,
            "source_camera_id": str(self.source_camera_id),
            "province": self.province,
            "title": _clean(self.title),
            "roadway": _clean(self.roadway),
            "lat": self.lat,
            "lon": self.lon,
            "views": self.views or None,
            "last_updated": _iso(self.last_updated),
            "raw": self.raw if include_raw else None,
        }


@dataclass
class RoadCondition:
    """A road surface / winter condition over a road segment."""

    source: str
    source_cond_id: str
    province: str
    roadway_name: Optional[str] = None
    road_number: Optional[str] = None
    is_highway: bool = False
    condition: Optional[str] = None
    condition_raw: Optional[str] = None
    geojson: Optional[dict] = None
    last_updated: Optional[datetime] = None
    raw: Optional[dict] = None

    def to_payload(self, include_raw: bool = True) -> dict:
        return {
            "source": self.source,
            "source_cond_id": str(self.source_cond_id),
            "province": self.province,
            "roadway_name": _clean(self.roadway_name),
            "road_number": _clean(self.road_number),
            "is_highway": bool(self.is_highway),
            "condition": _clean(self.condition),
            "condition_raw": _clean(self.condition_raw),
            "geojson": self.geojson,
            "last_updated": _iso(self.last_updated),
            "raw": self.raw if include_raw else None,
        }


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else None
