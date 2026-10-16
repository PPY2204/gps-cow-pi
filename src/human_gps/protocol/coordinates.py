"""Coordinate parsing from NMEA ddmm.mmmm format to decimal degrees."""
from typing import Optional


def parse_latitude(raw_value: str, hemisphere: str) -> Optional[float]:
    """Convert NMEA latitude (DDMM.MMMMM) and hemisphere (N/S) to decimal degrees."""
    if not raw_value or not hemisphere:
        return None

    try:
        raw = float(raw_value)
        degrees = int(raw // 100)
        minutes = raw - (degrees * 100)
        decimal = degrees + (minutes / 60.0)

        if hemisphere.upper() == "S":
            decimal = -decimal

        if -90.0 <= decimal <= 90.0:
            return round(decimal, 7)
        return None
    except (ValueError, TypeError):
        return None


def parse_longitude(raw_value: str, hemisphere: str) -> Optional[float]:
    """Convert NMEA longitude (DDDMM.MMMMM) and hemisphere (E/W) to decimal degrees."""
    if not raw_value or not hemisphere:
        return None

    try:
        raw = float(raw_value)
        degrees = int(raw // 100)
        minutes = raw - (degrees * 100)
        decimal = degrees + (minutes / 60.0)

        if hemisphere.upper() == "W":
            decimal = -decimal

        if -180.0 <= decimal <= 180.0:
            return round(decimal, 7)
        return None
    except (ValueError, TypeError):
        return None
