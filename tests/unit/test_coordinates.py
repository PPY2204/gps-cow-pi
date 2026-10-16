from human_gps.protocol.coordinates import parse_latitude, parse_longitude


def test_parse_latitude_north():
    # 35 degrees 40.1234 minutes -> 35 + 40.1234/60 = 35.6687233
    lat = parse_latitude("3540.1234", "N")
    assert lat is not None
    assert round(lat, 4) == 35.6687


def test_parse_latitude_south():
    lat = parse_latitude("3540.1234", "S")
    assert lat is not None
    assert lat < 0
    assert round(lat, 4) == -35.6687


def test_parse_longitude_east():
    # 139 degrees 45.5678 minutes -> 139 + 45.5678/60 = 139.7594633
    lon = parse_longitude("13945.5678", "E")
    assert lon is not None
    assert round(lon, 4) == 139.7595


def test_parse_longitude_west():
    lon = parse_longitude("13945.5678", "W")
    assert lon is not None
    assert lon < 0


def test_parse_empty_coordinates():
    assert parse_latitude("", "N") is None
    assert parse_longitude("", "E") is None
    assert parse_latitude("invalid", "N") is None
