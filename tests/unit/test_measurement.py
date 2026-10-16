from datetime import datetime, timezone
from human_gps.pipeline.measurement import MeasurementBuilder, parse_gnss_datetime
from human_gps.pipeline.synchronizer import EpochBundle
from human_gps.protocol.gga import GGAData
from human_gps.protocol.rmc import RMCData
from human_gps.domain.enums import FixQuality


def test_parse_gnss_datetime_valid():
    dt = parse_gnss_datetime("170926", "125808.20")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 9
    assert dt.day == 17
    assert dt.hour == 12
    assert dt.minute == 58
    assert dt.second == 8
    assert dt.microsecond == 200000
    assert dt.tzinfo == timezone.utc


def test_parse_gnss_datetime_invalid():
    assert parse_gnss_datetime("", "125808.20") is None
    assert parse_gnss_datetime("1709", "125808.20") is None
    assert parse_gnss_datetime("170926", "") is None
    assert parse_gnss_datetime("invalid", "invalid") is None


def test_measurement_builder_extracts_atomic_timestamp():
    builder = MeasurementBuilder()

    bundle = EpochBundle(
        utc_time="125808.20",
        arrival_time=datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc),  # System clock default
        gga=GGAData(
            utc_time="125808.20",
            latitude=35.6332,
            longitude=139.3284,
            fix_quality=FixQuality.GPS_FIX,
            satellites=8,
            hdop=1.2,
            altitude=140.0,
        ),
        rmc=RMCData(
            utc_time="125808.20",
            status="A",
            latitude=35.6332,
            longitude=139.3284,
            speed_knots=0.5,
            speed_kmh=0.93,
            track_degrees=45.0,
            date_str="170926",
        ),
    )

    measurement = builder.build(bundle)

    # Must prioritize atomic GNSS UTC date (2026-09-17) over system clock (2020-01-01)
    assert measurement.timestamp.year == 2026
    assert measurement.timestamp.month == 9
    assert measurement.timestamp.day == 17
    assert measurement.timestamp.hour == 12
    assert measurement.timestamp.minute == 58
    assert measurement.timestamp.second == 8
