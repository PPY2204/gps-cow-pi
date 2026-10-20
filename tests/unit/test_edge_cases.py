from pathlib import Path
import pytest
from human_gps.cli.main import is_safe_data_path
from human_gps.domain.enums import BehaviorState, FixQuality, QualityFlag
from human_gps.domain.models import GPSMeasurement, QualityResult, SubjectProfile
from human_gps.pipeline.filter import KinematicFilter
from human_gps.pipeline.synchronizer import EpochSynchronizer
from human_gps.protocol.gga import parse_gga
from human_gps.protocol.nmea import NMEARouter
from human_gps.protocol.vtg import parse_vtg
from human_gps.domain.exceptions import ChecksumMismatchError
from human_gps.services.replay import ReplayService


def test_no_fix_rejection_from_fixture(tmp_path: Path):
    fixture_path = Path("tests/fixtures/nmea/no_fix.txt")
    replay = ReplayService(
        filepath=fixture_path,
        profile=SubjectProfile.cow_default(),
        subject_id="TEST-NO-FIX",
        output_dir=tmp_path / "processed",
        realtime_delay=False,
    )
    summary = replay.run()
    assert summary["accepted_epochs"] == 0
    assert summary["rejected_epochs"] >= 1
    assert summary["fix_rate_percent"] == 0.0


def test_invalid_checksum_rejected_in_strict_mode():
    router = NMEARouter(strict_checksum=True)
    bad_sentence = "$GNGGA,012345.00,3540.1234,N,13945.5678,E,1,08,1.2,45.2,M,36.5,M,,*FF"
    with pytest.raises(ChecksumMismatchError):
        router.route(bad_sentence)


def test_vtg_before_gga_preserved():
    sync = EpochSynchronizer()
    vtg_line = "$GNVTG,123.4,T,120.0,M,2.5,N,4.63,K,A*0C"
    gga_line = "$GNGGA,012345.00,3540.1234,N,13945.5678,E,1,08,1.2,45.2,M,36.5,M,,*4B"

    vtg = parse_vtg(vtg_line)
    sync.feed_vtg(vtg, vtg_line)

    gga = parse_gga(gga_line)
    emitted = sync.feed_gga(gga, gga_line)
    assert emitted is None

    final = sync.flush()
    assert final is not None
    assert final.is_complete is True
    assert final.vtg is not None
    assert final.vtg.speed_kmh == 4.63


def test_kinematic_recovery_after_speed_spike():
    cow_filter = KinematicFilter(profile=SubjectProfile.cow_default())

    # Point 1: Resting at (35.600000, 139.700000)
    p1 = GPSMeasurement(
        timestamp=pytest.importorskip("datetime").datetime.now(pytest.importorskip("datetime").timezone.utc),
        utc_time="120000.00",
        latitude=35.600000,
        longitude=139.700000,
        fix_quality=FixQuality.GPS_FIX,
        satellites=8,
        hdop=1.0,
        speed_kmh=0.1,
        quality=QualityResult(),
    )
    res1 = cow_filter.filter(p1)
    assert res1.quality.accepted is True

    # Point 2: Erroneous satellite spike jumping far away (implied speed 100 km/h)
    p2 = GPSMeasurement(
        timestamp=pytest.importorskip("datetime").datetime.now(pytest.importorskip("datetime").timezone.utc),
        utc_time="120001.00",
        latitude=35.602000,
        longitude=139.700000,
        fix_quality=FixQuality.GPS_FIX,
        satellites=8,
        hdop=1.0,
        speed_kmh=100.0,
        quality=QualityResult(),
    )
    res2 = cow_filter.filter(p2)
    assert res2.quality.accepted is False
    assert QualityFlag.SPEED_EXCEEDED in res2.quality.flags

    # Point 3: Returns to true position near Point 1 (35.600002, 139.700001)
    p3 = GPSMeasurement(
        timestamp=pytest.importorskip("datetime").datetime.now(pytest.importorskip("datetime").timezone.utc),
        utc_time="120002.00",
        latitude=35.600002,
        longitude=139.700001,
        fix_quality=FixQuality.GPS_FIX,
        satellites=8,
        hdop=1.0,
        speed_kmh=0.2,
        quality=QualityResult(),
    )
    res3 = cow_filter.filter(p3)
    # Must recover and accept Point 3 based on distance from Point 1, NOT Point 2!
    assert res3.quality.accepted is True
    assert res3.quality.speed_valid is True
    assert res3.behavior_state == BehaviorState.RESTING


def test_safe_data_path_blocks_traversal():
    assert is_safe_data_path(Path("data/processed/SESSION_01.csv")) is True
    assert is_safe_data_path(Path("data/raw/SESSION_01.nmea")) is True

    # Traversal attempts should be blocked
    assert is_safe_data_path(Path("data/../../etc/passwd")) is False
    assert is_safe_data_path(Path("../../../windows/system32/cmd.exe")) is False
