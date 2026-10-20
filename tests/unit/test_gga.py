import pytest
from human_gps.domain.enums import FixQuality
from human_gps.domain.exceptions import NMEAParseError
from human_gps.protocol.gga import parse_gga


def test_parse_valid_gga():
    line = "$GNGGA,012345.00,3540.1234,N,13945.5678,E,1,08,1.2,45.2,M,36.5,M,,*4B"
    data = parse_gga(line)
    assert data.utc_time == "012345.00"
    assert data.fix_quality == FixQuality.GPS_FIX
    assert data.satellites == 8
    assert data.hdop == 1.2
    assert data.altitude == 45.2
    assert data.latitude is not None
    assert data.longitude is not None


def test_parse_no_fix_gga():
    line = "$GNGGA,012345.00,,,,,0,00,99.99,,,,,,"
    data = parse_gga(line)
    assert data.fix_quality == FixQuality.INVALID
    assert data.satellites == 0
    assert data.latitude is None
    assert data.longitude is None


def test_parse_insufficient_fields():
    with pytest.raises(NMEAParseError):
        parse_gga("$GNGGA,1,2,3")
