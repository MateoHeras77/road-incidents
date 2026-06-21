from src.ingest.highway import classify_highway, quebec_is_highway


def test_named_numbered_highways():
    assert classify_highway("Highway 401") == (True, "401")
    assert classify_highway("Hwy 16") == (True, "16")
    assert classify_highway("Autoroute 20") == (True, "20")


def test_named_highway_without_number():
    is_hw, _ = classify_highway("Trans-Canada Highway")
    assert is_hw is True
    assert classify_highway("QEW") == (True, "QEW")


def test_route_code():
    assert classify_highway("AB-2") == (True, "AB-2")


def test_local_roads_are_not_highways():
    assert classify_highway("Moraine Lake Rd") == (False, None)
    assert classify_highway("Main Street") == (False, None)
    assert classify_highway(None) == (False, None)


def test_quebec_route_number():
    assert quebec_is_highway("20") == (True, "20")
    assert quebec_is_highway("") == (False, None)
    assert quebec_is_highway(None) == (False, None)
