from src.ingest.adapters.polyline import decode, to_geojson

# Canonical Google example: 3 points in (lat, lon).
ENCODED = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


def test_decode_known_polyline():
    coords = decode(ENCODED)  # returns (lon, lat) pairs
    assert len(coords) == 3
    lon, lat = coords[0]
    assert round(lat, 3) == 38.500
    assert round(lon, 3) == -120.200


def test_to_geojson_linestring():
    geo = to_geojson(ENCODED)
    assert geo["type"] == "LineString"
    assert len(geo["coordinates"]) == 3


def test_to_geojson_multilinestring():
    geo = to_geojson([ENCODED, ENCODED])
    assert geo["type"] == "MultiLineString"
    assert len(geo["coordinates"]) == 2


def test_to_geojson_empty():
    assert to_geojson(None) is None
    assert to_geojson([]) is None
