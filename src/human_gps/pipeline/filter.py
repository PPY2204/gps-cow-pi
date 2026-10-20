"""Subject-aware kinematic filter and behavior classification engine."""
from collections import deque
import statistics
from typing import Optional
from human_gps.domain.enums import BehaviorState, QualityFlag, SubjectType
from human_gps.domain.models import GPSMeasurement, SubjectProfile
from human_gps.pipeline.measurement import haversine_distance


def parse_utc_seconds(utc_str: str) -> Optional[float]:
    """Parse NMEA UTC string hhmmss.ss into seconds of day."""
    if not utc_str or len(utc_str) < 6:
        return None
    try:
        hours = float(utc_str[0:2])
        minutes = float(utc_str[2:4])
        seconds = float(utc_str[4:])
        return hours * 3600.0 + minutes * 60.0 + seconds
    except ValueError:
        return None


class KinematicFilter:
    """Applies kinematic limits (speed, acceleration, wandering jitter suppression)

    tailored specifically to the tracked subject (Human vs Cow vs Other animals).
    """

    def __init__(self, profile: SubjectProfile):
        self.profile = profile
        self._last_accepted: Optional[GPSMeasurement] = None
        self._recent_speeds: deque[float] = deque(maxlen=self.profile.stationary_window_samples)

    def filter(self, measurement: GPSMeasurement) -> GPSMeasurement:
        """Evaluate kinematic rules on measurement and update quality flags and behavior."""
        if measurement.quality is None:
            from human_gps.domain.models import QualityResult
            measurement.quality = QualityResult()

        quality = measurement.quality

        # If already rejected by GNSS validator (no fix, etc.), skip kinematic processing
        if not quality.accepted:
            measurement.behavior_state = BehaviorState.UNKNOWN
            return measurement

        # 1. Direct sensor speed check
        if measurement.speed_kmh is not None:
            if measurement.speed_kmh > self.profile.max_speed_kmh:
                quality.speed_valid = False
                quality.add_rejection(
                    QualityFlag.SPEED_EXCEEDED,
                    f"Measured speed ({measurement.speed_kmh:.1f} km/h) exceeds {self.profile.subject_type.value} limit ({self.profile.max_speed_kmh:.1f} km/h)",
                )

        # 2. Inter-epoch kinematic checks (implied speed & acceleration)
        if self._last_accepted is not None and measurement.has_coordinates:
            t1 = parse_utc_seconds(self._last_accepted.utc_time)
            t2 = parse_utc_seconds(measurement.utc_time)

            if t1 is not None and t2 is not None:
                dt = t2 - t1
                # Handle midnight rollover (24h = 86400s)
                if dt < 0:
                    dt += 86400.0

                if 0.05 <= dt <= 10.0:  # Valid time window for sequential epochs
                    if (
                        self._last_accepted.latitude is not None
                        and self._last_accepted.longitude is not None
                        and measurement.latitude is not None
                        and measurement.longitude is not None
                    ):
                        dist_m = haversine_distance(
                            self._last_accepted.latitude,
                            self._last_accepted.longitude,
                            measurement.latitude,
                            measurement.longitude,
                        )
                        measurement.distance_from_previous_m = round(dist_m, 3)
                    else:
                        dist_m = measurement.distance_from_previous_m

                    implied_speed_kmh = (dist_m / dt) * 3.6

                    # Check implied velocity jump
                    if implied_speed_kmh > self.profile.max_speed_kmh:
                        quality.speed_valid = False
                        quality.add_rejection(
                            QualityFlag.SPEED_EXCEEDED,
                            f"Implied jump speed ({implied_speed_kmh:.1f} km/h) exceeds limit ({self.profile.max_speed_kmh:.1f} km/h)",
                        )

                    # Check acceleration
                    v1_ms = ((self._last_accepted.speed_kmh or 0.0) * 1000.0) / 3600.0
                    v2_ms = ((measurement.speed_kmh or implied_speed_kmh) * 1000.0) / 3600.0
                    accel_ms2 = abs(v2_ms - v1_ms) / dt

                    if accel_ms2 > self.profile.max_acceleration_ms2:
                        quality.accel_valid = False
                        quality.add_rejection(
                            QualityFlag.ACCEL_EXCEEDED,
                            f"Acceleration ({accel_ms2:.2f} m/s²) exceeds limit ({self.profile.max_acceleration_ms2:.2f} m/s²)",
                        )

                    # 3. GPS Wandering Jitter Suppression (critical for cattle resting/rumination)
                    eff_speed = measurement.speed_kmh if measurement.speed_kmh is not None else implied_speed_kmh
                    if (
                        eff_speed <= self.profile.stationary_speed_kmh
                        and dist_m < self.profile.min_movement_threshold_m
                    ):
                        quality.jitter_suppressed = True
                        quality.add_warning(QualityFlag.JITTER_SUPPRESSED)
                        # Suppress artificial distance and velocity accumulation while stationary
                        measurement.distance_from_previous_m = 0.0
                        if measurement.speed_kmh is not None and measurement.speed_kmh < self.profile.deadband_speed_kmh:
                            measurement.speed_kmh = 0.0

        # 4. Inferred behavioral state classification with sliding window smoothing
        measurement.behavior_state = self._classify_behavior(measurement)

        # Update last accepted point if valid
        if quality.accepted:
            self._last_accepted = measurement

        return measurement

    def _classify_behavior(self, measurement: GPSMeasurement) -> BehaviorState:
        """Infer behavioral state from smoothed speed and profile."""
        current_speed = measurement.speed_kmh or 0.0
        self._recent_speeds.append(current_speed)

        if len(self._recent_speeds) >= 3:
            smoothed_speed = statistics.median(self._recent_speeds)
        else:
            smoothed_speed = current_speed

        quality = measurement.quality
        if quality and quality.jitter_suppressed and smoothed_speed < self.profile.deadband_speed_kmh:
            return BehaviorState.RESTING

        if self.profile.subject_type == SubjectType.BOVINE:
            if smoothed_speed < 0.35:
                return BehaviorState.RESTING
            elif 0.35 <= smoothed_speed <= 1.8:
                return BehaviorState.GRAZING
            elif 1.8 < smoothed_speed <= 10.0:
                return BehaviorState.WALKING
            else:
                return BehaviorState.RUNNING

        elif self.profile.subject_type == SubjectType.HUMAN:
            if smoothed_speed < 0.5:
                return BehaviorState.RESTING
            elif 0.5 <= smoothed_speed <= 7.0:
                return BehaviorState.WALKING
            else:
                return BehaviorState.RUNNING

        else:
            if smoothed_speed < 0.5:
                return BehaviorState.RESTING
            elif smoothed_speed <= 10.0:
                return BehaviorState.WALKING
            else:
                return BehaviorState.RUNNING
