"""IBI/511 platform adapter (Alberta, Saskatchewan, Ontario, Manitoba, Atlantic).

All these provinces expose the same contract:
    https://<host>/api/v2/get/<resource>?format=json&lang=en[&key=...]
Events, cameras and road conditions are parsed here into the shared models.
"""
from __future__ import annotations

from typing import List, Optional

from ..highway import classify_highway
from ..models import (
    CLASS_ACCIDENT,
    CLASS_CLOSURE,
    CLASS_CONSTRUCTION,
    CLASS_INFO,
    CLASS_OTHER,
    CLASS_RESTRICTION,
    CLASS_SPECIAL,
    Camera,
    RoadCondition,
    RoadEvent,
)
from .base import http_get_json, ts_from_epoch
from .polyline import to_geojson

# Province registry: source code -> host + whether it needs an API key.
IBI_PROVINCES = {
    "ab": {"province": "Alberta", "host": "511.alberta.ca", "needs_key": False},
    "sk": {"province": "Saskatchewan", "host": "hotline.gov.sk.ca", "needs_key": True},
    "on": {"province": "Ontario", "host": "511on.ca", "needs_key": False},
    "mb": {"province": "Manitoba", "host": "www.manitoba511.ca", "needs_key": True},
    "nb": {"province": "New Brunswick", "host": "511.gnb.ca", "needs_key": True},
    "ns": {"province": "Nova Scotia", "host": "511.novascotia.ca", "needs_key": True},
    "pe": {"province": "Prince Edward Island", "host": "511.gov.pe.ca", "needs_key": True},
    "nl": {"province": "Newfoundland and Labrador", "host": "511nl.ca", "needs_key": True},
}

_EVENT_CLASS = {
    "closures": CLASS_CLOSURE,
    "accidentsAndIncidents": CLASS_ACCIDENT,
    "roadwork": CLASS_CONSTRUCTION,
    "restrictionClass": CLASS_RESTRICTION,
    "specialEvents": CLASS_SPECIAL,
    "generalInfo": CLASS_INFO,
}

_NOISE_CONDITIONS = {"", "no report", "not reported", "unknown"}


def build_url(host: str, resource: str, *, version: str = "v2", key: Optional[str] = None) -> str:
    url = f"https://{host}/api/{version}/get/{resource}?format=json&lang=en"
    if key:
        url += f"&key={key}"
    return url


def _restrictions(raw: dict) -> Optional[dict]:
    r = raw.get("Restrictions") or {}
    out = {k.lower(): v for k, v in r.items() if v not in (None, "", 0)}
    return out or None


def parse_events(records: list, source: str, province: str) -> List[RoadEvent]:
    """Parse the IBI `event` resource into RoadEvent objects."""
    events: List[RoadEvent] = []
    for rec in records or []:
        roadway = rec.get("RoadwayName")
        is_hw, road_no = classify_highway(roadway)
        lat, lon = rec.get("Latitude"), rec.get("Longitude")
        geojson = to_geojson(rec.get("EncodedPolyline"))
        if geojson is None and lat is not None and lon is not None:
            geojson = {"type": "Point", "coordinates": [lon, lat]}
        ev_type = rec.get("EventType")
        events.append(
            RoadEvent(
                source=source,
                source_event_id=rec.get("SourceId") or rec.get("ID"),
                province=province,
                event_class=_EVENT_CLASS.get(ev_type, CLASS_OTHER),
                roadway_name=roadway,
                road_number=road_no,
                is_highway=is_hw,
                is_full_closure=bool(rec.get("IsFullClosure")),
                direction=rec.get("DirectionOfTravel"),
                severity=rec.get("Severity"),
                description=rec.get("Description"),
                raw_event_type=ev_type,
                raw_event_subtype=rec.get("EventSubType"),
                restrictions=_restrictions(rec),
                starts_at=ts_from_epoch(rec.get("StartDate")),
                planned_end_at=ts_from_epoch(rec.get("PlannedEndDate")),
                reported_at=ts_from_epoch(rec.get("Reported")),
                last_updated=ts_from_epoch(rec.get("LastUpdated")),
                geojson=geojson,
                raw=rec,
            )
        )
    return events


def parse_cameras(records: list, source: str, province: str) -> List[Camera]:
    cams: List[Camera] = []
    for rec in records or []:
        cams.append(
            Camera(
                source=source,
                source_camera_id=rec.get("SourceId") or rec.get("Id"),
                province=province,
                title=rec.get("Location") or rec.get("Roadway"),
                roadway=rec.get("Roadway"),
                lat=rec.get("Latitude"),
                lon=rec.get("Longitude"),
                views=[v.get("Url") for v in rec.get("Views", []) if v.get("Url")] or None,
                raw=rec,
            )
        )
    return cams


def _condition_text(rec: dict) -> Optional[str]:
    value = rec.get("Primary Condition")
    if value is None:
        cond = rec.get("Condition")
        if isinstance(cond, list):
            value = ", ".join(str(c) for c in cond if c)
        else:
            value = cond
    return value


def parse_conditions(records: list, source: str, province: str) -> List[RoadCondition]:
    """Parse `roadconditions` (ON/MB) or `winterroads` (AB) resources."""
    out: List[RoadCondition] = []
    for idx, rec in enumerate(records or []):
        cond = _condition_text(rec)
        if cond is None or str(cond).strip().lower() in _NOISE_CONDITIONS:
            continue
        roadway = rec.get("RoadwayName")
        is_hw, road_no = classify_highway(roadway)
        if not is_hw and roadway and str(roadway).strip().replace("A", "").isdigit():
            is_hw, road_no = True, str(roadway).strip()  # bare numeric route (ON)
        out.append(
            RoadCondition(
                source=source,
                source_cond_id=str(rec.get("Id") or f"{roadway}-{idx}"),
                province=province,
                roadway_name=roadway,
                road_number=road_no,
                is_highway=is_hw,
                condition=str(cond),
                condition_raw=str(cond),
                geojson=to_geojson(rec.get("EncodedPolyline")),
                last_updated=ts_from_epoch(rec.get("LastUpdated")),
                raw=rec,
            )
        )
    return out


# --- network fetchers ------------------------------------------------------

def fetch_events(source: str, key: Optional[str] = None) -> List[RoadEvent]:
    cfg = IBI_PROVINCES[source]
    data = http_get_json(build_url(cfg["host"], "event", key=key))
    return parse_events(data, source, cfg["province"])


def fetch_cameras(source: str, key: Optional[str] = None) -> List[Camera]:
    cfg = IBI_PROVINCES[source]
    data = http_get_json(build_url(cfg["host"], "cameras", key=key))
    return parse_cameras(data, source, cfg["province"])


def fetch_conditions(source: str, key: Optional[str] = None, *, resource: str = "roadconditions",
                     version: str = "v2") -> List[RoadCondition]:
    cfg = IBI_PROVINCES[source]
    data = http_get_json(build_url(cfg["host"], resource, version=version, key=key))
    return parse_conditions(data, source, cfg["province"])
