"""MTQ Québec adapter (Transports Québec open data, WFS GeoJSON).

Feed fields are in French. A non-empty `numeroRoute` marks a numbered route
(highway); local streets carry an empty `numeroRoute`.
"""
from __future__ import annotations

from typing import List

from ..highway import quebec_is_highway
from ..models import (
    CLASS_ACCIDENT,
    CLASS_CLOSURE,
    CLASS_CONSTRUCTION,
    CLASS_RESTRICTION,
    RoadEvent,
)
from .base import http_get_json, ts_from_iso

QC_EVENTS_URL = (
    "https://ws.mapserver.transports.gouv.qc.ca/swtq"
    "?service=wfs&version=2.0.0&request=getfeature"
    "&typename=ms:evenements&outfile=AvertissementRoutier"
    "&srsname=EPSG:4326&outputformat=geojson"
)


def _classify(entrave: str, cause: str):
    e, c = (entrave or "").lower(), (cause or "").lower()
    if "accident" in c or "incident" in c:
        ev_class = CLASS_ACCIDENT
    elif any(k in c for k in ("travaux", "construct", "entretien", "réfection", "refection")):
        ev_class = CLASS_CONSTRUCTION
    elif "fermeture" in e:
        ev_class = CLASS_CLOSURE
    else:
        ev_class = CLASS_RESTRICTION
    full = "fermeture" in e and "voie" not in e
    return ev_class, full


def _description(props: dict) -> str:
    parts = [props.get(k) for k in ("localisation", "cause", "consequence", "detour")]
    return " | ".join(p for p in parts if p)


def parse_events(payload: dict) -> List[RoadEvent]:
    events: List[RoadEvent] = []
    for feat in (payload or {}).get("features", []):
        props = feat.get("properties", {})
        is_hw, road_no = quebec_is_highway(props.get("numeroRoute"))
        ev_class, full = _classify(props.get("entrave"), props.get("cause"))
        roadway = f"Route {road_no}" if road_no else props.get("localisation")
        events.append(
            RoadEvent(
                source="qc",
                source_event_id=props.get("identifiant"),
                province="Quebec",
                event_class=ev_class,
                roadway_name=roadway,
                road_number=road_no,
                is_highway=is_hw,
                is_full_closure=full,
                direction=props.get("direction"),
                headline=props.get("entrave"),
                description=_description(props),
                raw_event_type=props.get("entrave"),
                raw_event_subtype=props.get("cause"),
                starts_at=ts_from_iso(props.get("enVigueurDepuis")),
                last_updated=ts_from_iso(props.get("enVigueurDepuis")),
                geojson=feat.get("geometry"),
                raw=props,
            )
        )
    return events


def fetch_events(url: str = QC_EVENTS_URL) -> List[RoadEvent]:
    return parse_events(http_get_json(url))
