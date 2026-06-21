import json
from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _load(name: str):
    with open(SAMPLES / name, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def samples_dir() -> Path:
    return SAMPLES


@pytest.fixture
def bc_events_raw():
    return _load("bc_open511_events.json")


@pytest.fixture
def ab_events_raw():
    return _load("ab_event.json")


@pytest.fixture
def ab_cameras_raw():
    return _load("ab_cameras.json")


@pytest.fixture
def ab_winterroads_raw():
    return _load("ab_winterroads.json")


@pytest.fixture
def on_conditions_raw():
    return _load("on_roadconditions.json")


@pytest.fixture
def qc_events_raw():
    return _load("qc_events.geojson")
