from src.ingest.adapters import ibi511, mtq_quebec, open511
from src.ingest.models import (
    CLASS_ACCIDENT,
    CLASS_CLOSURE,
    CLASS_CONSTRUCTION,
)


# --- Open511 (BC) ----------------------------------------------------------

def test_open511_parses_events(bc_events_raw):
    events = open511.parse_events(bc_events_raw)
    assert events, "expected BC events"
    ev = events[0]
    assert ev.source == "bc"
    assert ev.province == "British Columbia"
    assert ev.source_event_id
    assert ev.geojson and ev.geojson["type"] in ("Point", "LineString", "MultiLineString")


def test_open511_event_classes(bc_events_raw):
    classes = {e.event_class for e in open511.parse_events(bc_events_raw)}
    assert classes.issubset(
        {"closure", "accident", "construction", "special", "condition", "other"}
    )


# --- IBI/511 (Alberta) -----------------------------------------------------

def test_ibi_parses_events(ab_events_raw):
    events = ibi511.parse_events(ab_events_raw, "ab", "Alberta")
    assert len(events) == len(ab_events_raw)
    assert {e.source for e in events} == {"ab"}


def test_ibi_event_class_mapping(ab_events_raw):
    events = ibi511.parse_events(ab_events_raw, "ab", "Alberta")
    by_type = {e.raw_event_type: e.event_class for e in events}
    assert by_type.get("closures") == CLASS_CLOSURE
    assert by_type.get("roadwork") == CLASS_CONSTRUCTION
    assert by_type.get("accidentsAndIncidents") == CLASS_ACCIDENT


def test_ibi_full_closure_flag(ab_events_raw):
    events = ibi511.parse_events(ab_events_raw, "ab", "Alberta")
    assert any(e.is_full_closure for e in events)


def test_ibi_cameras_have_coordinates(ab_cameras_raw):
    cams = ibi511.parse_cameras(ab_cameras_raw, "ab", "Alberta")
    assert cams
    assert all(c.lat is not None and c.lon is not None for c in cams[:20])
    assert cams[0].views


def test_ibi_conditions_skip_noise_and_decode_geometry(ab_winterroads_raw):
    conds = ibi511.parse_conditions(ab_winterroads_raw, "ab", "Alberta")
    assert conds, "expected some non-noise winter conditions"
    assert all(c.condition.strip().lower() != "no report" for c in conds)
    assert any(c.geojson for c in conds)


def test_ibi_highway_filter_drops_local_roads(ab_events_raw):
    events = ibi511.parse_events(ab_events_raw, "ab", "Alberta")
    highways = [e for e in events if e.is_highway]
    assert 0 < len(highways) < len(events)


# --- MTQ (Québec) ----------------------------------------------------------

def test_quebec_parses_and_flags_highways(qc_events_raw):
    events = mtq_quebec.parse_events(qc_events_raw)
    assert events
    assert {e.source for e in events} == {"qc"}
    # Highway events must carry a route number; non-highway ones must not.
    for e in events:
        assert e.is_highway == bool(e.road_number)


def test_quebec_geometry_is_linestring(qc_events_raw):
    events = mtq_quebec.parse_events(qc_events_raw)
    assert any(e.geojson and e.geojson["type"] == "LineString" for e in events)


def test_quebec_closure_detection(qc_events_raw):
    events = mtq_quebec.parse_events(qc_events_raw)
    assert {e.event_class for e in events} <= {
        CLASS_CLOSURE,
        CLASS_ACCIDENT,
        CLASS_CONSTRUCTION,
        "restriction",
    }
