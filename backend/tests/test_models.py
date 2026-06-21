from datetime import datetime, timedelta, timezone

from src.ingest.models import RoadEvent


def _event(**kw):
    base = dict(source="ab", source_event_id="x1", province="Alberta", event_class="closure")
    base.update(kw)
    return RoadEvent(**base)


def test_is_scheduled_future_vs_past():
    future = _event(starts_at=datetime.now(timezone.utc) + timedelta(days=2))
    past = _event(starts_at=datetime.now(timezone.utc) - timedelta(days=2))
    assert future.is_scheduled is True
    assert past.is_scheduled is False
    assert _event().is_scheduled is False


def test_to_payload_blank_strings_become_null():
    ev = _event(direction="", description="  ")
    payload = ev.to_payload()
    assert payload["direction"] is None
    assert payload["description"] is None
    assert payload["is_highway"] is False


def test_to_payload_can_exclude_raw():
    ev = _event(raw={"big": "blob"})
    assert ev.to_payload(include_raw=False)["raw"] is None
    assert ev.to_payload(include_raw=True)["raw"] == {"big": "blob"}
