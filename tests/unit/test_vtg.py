import pytest
from human_gps.domain.exceptions import NMEAParseError
from human_gps.protocol.vtg import parse_vtg


def test_parse_valid_vtg():
    line = "$GNVTG,123.4,T,120.0,M,2.5,N,4.63,K,A*23"
    data = parse_vtg(line)
    assert data.track_true == 123.4
    assert data.track_mag == 120.0
    assert data.speed_knots == 2.5
    assert data.speed_kmh == 4.63
    assert data.mode == "A"


def test_parse_vtg_knots_only():
    line = "$GNVTG,100.0,T,,M,10.0,N,,K,A"
    data = parse_vtg(line)
    assert data.speed_knots == 10.0
    # 10 knots = 18.52 km/h
    assert data.speed_kmh == 18.52


def test_parse_vtg_empty():
    line = "$GNVTG,,,,,,,,,N"
    data = parse_vtg(line)
    assert data.speed_kmh is None
    assert data.track_true is None
