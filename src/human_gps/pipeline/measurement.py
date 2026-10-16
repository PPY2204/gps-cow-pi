"""Builder converting synchronized epoch bundles into unified GPSMeasurement models."""
import math
from datetime import datetime, timezone
from typing import Optional
from human_gps.domain.enums import FixQuality
from human_gps.domain.models import GPSMeasurement
from human_gps.pipeline.synchronizer import EpochBundle


def parse_gnss_datetime(date_str: Optional[str], utc_time_str: Optional[str]) -> Optional[datetime]:
    """Parse NMEA date (ddmmyy) and UTC time (hhmmss[.ss]) into a true UTC datetime.

    This ensures accurate atomic timestamping even when the host system (Raspberry Pi)
    has no RTC battery or internet connection in the field.
    """
    if not date_str or len(date_str) < 6 or not utc_time_str or len(utc_time_str) < 6:
        return None
    try:
        day = int(date_str[0:2])
        month = int(date_str[2:4])
        year = 2000 + int(date_str[4:6])

        hour = int(utc_time_str[0:2])
        minute = int(utc_time_str[2:4])
        sec_float = float(utc_time_str[4:])
        second = int(sec_float)
        microsecond = int(round((sec_float - second) * 1_000_000))
        if microsecond >= 1_000_000:
            second += 1
            microsecond -= 1_000_000

        return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=timezone.utc)
    except Exception:
        return None


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth in meters."""
    r_earth = 6371000.0  # Earth radius in meters

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_earth * c


class MeasurementBuilder:
    """Constructs GPSMeasurement objects and maintains trajectory continuity."""

    def __init__(self):
        self._last_measurement: Optional[GPSMeasurement] = None
        self._last_known_date_str: Optional[str] = None

    def build(self, bundle: EpochBundle) -> GPSMeasurement:
        """Construct a GPSMeasurement from an EpochBundle."""
        lat = bundle.gga.latitude if bundle.gga else (bundle.rmc.latitude if bundle.rmc else None)
        lon = bundle.gga.longitude if bundle.gga else (bundle.rmc.longitude if bundle.rmc else None)
        altitude = bundle.gga.altitude if bundle.gga else None
        fix_quality = bundle.gga.fix_quality if bundle.gga else FixQuality.INVALID
        satellites = bundle.gga.satellites if bundle.gga else 0
        hdop = bundle.gga.hdop if bundle.gga else None

        # Speed and track: prioritize VTG, fallback to RMC
        speed_kmh = None
        track_deg = None

        if bundle.vtg is not None:
            speed_kmh = bundle.vtg.speed_kmh
            track_deg = bundle.vtg.track_true or bundle.vtg.track_mag
        elif bundle.rmc is not None:
            speed_kmh = bundle.rmc.speed_kmh
            track_deg = bundle.rmc.track_degrees

        # Update last known GNSS date string (ddmmyy) from RMC
        if bundle.rmc and bundle.rmc.date_str and len(bundle.rmc.date_str) >= 6:
            self._last_known_date_str = bundle.rmc.date_str

        # Derive authoritative atomic UTC timestamp from GNSS
        gnss_dt = None
        if self._last_known_date_str and bundle.utc_time:
            gnss_dt = parse_gnss_datetime(self._last_known_date_str, bundle.utc_time)

        final_timestamp = gnss_dt if gnss_dt is not None else bundle.arrival_time

        # Calculate incremental distance if consecutive points have coordinates
        dist_m = 0.0
        if (
            lat is not None
            and lon is not None
            and self._last_measurement is not None
            and self._last_measurement.latitude is not None
            and self._last_measurement.longitude is not None
        ):
            dist_m = haversine_distance(
                self._last_measurement.latitude,
                self._last_measurement.longitude,
                lat,
                lon,
            )

        measurement = GPSMeasurement(
            timestamp=final_timestamp,
            utc_time=bundle.utc_time,
            latitude=lat,
            longitude=lon,
            altitude=altitude,
            fix_quality=fix_quality,
            satellites=satellites,
            hdop=hdop,
            speed_kmh=speed_kmh,
            track_degrees=track_deg,
            distance_from_previous_m=round(dist_m, 3),
            raw_sentences=list(bundle.raw_lines),
        )

        self._last_measurement = measurement
        return measurement
