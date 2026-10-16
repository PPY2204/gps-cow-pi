from datetime import datetime, timezone
from human_gps.domain.enums import BehaviorState, FixQuality, QualityFlag, SubjectType
from human_gps.domain.models import GPSMeasurement, QualityResult, SubjectProfile
from human_gps.pipeline.filter import KinematicFilter


def test_cow_speed_limit_rejection():
    cow_filter = KinematicFilter(profile=SubjectProfile.cow_default())

    # Measurement with valid fix but unrealistic speed for a cow (e.g. 45 km/h jump)
    m = GPSMeasurement(
        timestamp=datetime.now(timezone.utc),
        utc_time="120000.00",
        latitude=35.6,
        longitude=139.7,
        fix_quality=FixQuality.GPS_FIX,
        satellites=8,
        hdop=1.0,
        speed_kmh=45.0,  # Far above cow limit (25 km/h)
        quality=QualityResult(),
    )

    filtered = cow_filter.filter(m)
    assert filtered.quality.accepted is False
    assert QualityFlag.SPEED_EXCEEDED in filtered.quality.flags


def test_human_running_accepted():
    human_filter = KinematicFilter(profile=SubjectProfile.human_default())

    m = GPSMeasurement(
        timestamp=datetime.now(timezone.utc),
        utc_time="120000.00",
        latitude=35.6,
        longitude=139.7,
        fix_quality=FixQuality.GPS_FIX,
        satellites=8,
        hdop=1.0,
        speed_kmh=18.0,  # Fast run, within human limit (35 km/h)
        quality=QualityResult(),
    )

    filtered = human_filter.filter(m)
    assert filtered.quality.accepted is True
    assert filtered.behavior_state == BehaviorState.RUNNING


def test_cow_stationary_jitter_suppression():
    cow_filter = KinematicFilter(profile=SubjectProfile.cow_default())

    # Point 1: initial resting point
    p1 = GPSMeasurement(
        timestamp=datetime.now(timezone.utc),
        utc_time="120000.00",
        latitude=35.600000,
        longitude=139.700000,
        fix_quality=FixQuality.GPS_FIX,
        satellites=8,
        hdop=1.0,
        speed_kmh=0.1,
        quality=QualityResult(),
    )
    cow_filter.filter(p1)

    # Point 2: 1 second later, cow didn't move but GPS drifted 0.8 meters (speed reported 0.2 km/h)
    p2 = GPSMeasurement(
        timestamp=datetime.now(timezone.utc),
        utc_time="120001.00",
        latitude=35.600005,
        longitude=139.700005,
        fix_quality=FixQuality.GPS_FIX,
        satellites=8,
        hdop=1.0,
        speed_kmh=0.2,
        distance_from_previous_m=0.8,
        quality=QualityResult(),
    )

    filtered = cow_filter.filter(p2)
    assert filtered.quality.accepted is True
    assert filtered.quality.jitter_suppressed is True
    # The artificial distance must be zeroed out
    assert filtered.distance_from_previous_m == 0.0
    assert filtered.behavior_state == BehaviorState.RESTING


def test_cow_grazing_classification():
    cow_filter = KinematicFilter(profile=SubjectProfile.cow_default())

    m = GPSMeasurement(
        timestamp=datetime.now(timezone.utc),
        utc_time="120000.00",
        latitude=35.6,
        longitude=139.7,
        fix_quality=FixQuality.GPS_FIX,
        satellites=8,
        hdop=1.0,
        speed_kmh=1.2,  # Grazing speed (0.3 - 1.8 km/h)
        quality=QualityResult(),
    )

    filtered = cow_filter.filter(m)
    assert filtered.behavior_state == BehaviorState.GRAZING


def test_cow_speed_spike_suppression():
    cow_filter = KinematicFilter(profile=SubjectProfile.cow_default())

    # Feed 3 resting points (speed = 0.1 km/h)
    for i in range(3):
        m = GPSMeasurement(
            timestamp=datetime.now(timezone.utc),
            utc_time=f"12000{i}.00",
            latitude=35.6,
            longitude=139.7,
            fix_quality=FixQuality.GPS_FIX,
            satellites=8,
            hdop=1.0,
            speed_kmh=0.1,
            quality=QualityResult(),
        )
        cow_filter.filter(m)

    # An isolated multipath noise spike to 2.8 km/h occurs for 1 epoch
    spike_m = GPSMeasurement(
        timestamp=datetime.now(timezone.utc),
        utc_time="120003.00",
        latitude=35.6,
        longitude=139.7,
        fix_quality=FixQuality.GPS_FIX,
        satellites=8,
        hdop=2.0,
        speed_kmh=2.8,
        distance_from_previous_m=0.3,
        quality=QualityResult(),
    )
    filtered = cow_filter.filter(spike_m)
    # Median smoothing prevents the single spike from falsely triggering WALKING
    assert filtered.behavior_state == BehaviorState.RESTING
