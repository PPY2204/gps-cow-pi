from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from human_gps.domain.enums import (
    BehaviorState,
    FixQuality,
    MountType,
    QualityFlag,
    SubjectType,
)


@dataclass(frozen=True)
class SubjectProfile:
    """Kinematic constraints and motion characteristics for a tracked entity."""
    subject_type: SubjectType
    max_speed_kmh: float = 25.0
    max_acceleration_ms2: float = 3.0
    min_movement_threshold_m: float = 1.5
    stationary_speed_kmh: float = 0.5
    deadband_speed_kmh: float = 0.6
    stationary_window_samples: int = 10
    max_heading_change_rate_deg_s: float = 90.0

    @classmethod
    def cow_default(cls) -> "SubjectProfile":
        return cls(
            subject_type=SubjectType.BOVINE,
            max_speed_kmh=25.0,
            max_acceleration_ms2=3.0,
            min_movement_threshold_m=1.5,
            stationary_speed_kmh=0.5,
            deadband_speed_kmh=0.6,
            stationary_window_samples=10,
            max_heading_change_rate_deg_s=90.0,
        )

    @classmethod
    def human_default(cls) -> "SubjectProfile":
        return cls(
            subject_type=SubjectType.HUMAN,
            max_speed_kmh=35.0,
            max_acceleration_ms2=6.0,
            min_movement_threshold_m=0.8,
            stationary_speed_kmh=0.6,
            deadband_speed_kmh=0.7,
            stationary_window_samples=8,
            max_heading_change_rate_deg_s=180.0,
        )


@dataclass
class QualityResult:
    """Detailed validation outcome for a single GPS measurement."""
    accepted: bool = True
    flags: List[QualityFlag] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)

    fix_valid: bool = True
    satellite_valid: bool = True
    hdop_valid: bool = True
    speed_valid: bool = True
    accel_valid: bool = True
    jitter_suppressed: bool = False

    def add_rejection(self, flag: QualityFlag, reason: str) -> None:
        self.accepted = False
        if flag not in self.flags:
            self.flags.append(flag)
        if reason not in self.rejection_reasons:
            self.rejection_reasons.append(reason)

    def add_warning(self, flag: QualityFlag) -> None:
        if flag not in self.flags:
            self.flags.append(flag)


@dataclass
class GPSMeasurement:
    """Synchronized epoch measurement, independent of device protocol."""
    timestamp: datetime
    utc_time: str

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None

    fix_quality: FixQuality = FixQuality.INVALID
    satellites: int = 0
    hdop: Optional[float] = None

    speed_kmh: Optional[float] = None
    track_degrees: Optional[float] = None

    distance_from_previous_m: float = 0.0
    behavior_state: BehaviorState = BehaviorState.UNKNOWN
    quality: Optional[QualityResult] = None
    raw_sentences: List[str] = field(default_factory=list)

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def is_accepted(self) -> bool:
        return self.quality.accepted if self.quality else True


@dataclass
class SessionMetadata:
    """Metadata describing a data collection session."""
    session_id: str
    device_id: str
    subject_id: str
    subject_type: SubjectType
    mount_type: MountType
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sampling_rate_hz: int = 10
    notes: str = ""
