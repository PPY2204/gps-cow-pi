"""Parser for NMEA RMC (Recommended Minimum Specific GNSS Data)."""
from dataclasses import dataclass
from typing import Optional
from human_gps.domain.exceptions import NMEAParseError
from human_gps.protocol.coordinates import parse_latitude, parse_longitude


@dataclass(frozen=True)
class RMCData:
    """Decoded fields from an RMC sentence."""
    utc_time: str
    status: str  # 'A' = Valid, 'V' = Warning
    latitude: Optional[float]
    longitude: Optional[float]
    speed_knots: Optional[float]
    speed_kmh: Optional[float]
    track_degrees: Optional[float]
    date_str: str


def parse_rmc(sentence: str) -> RMCData:
    """Parse an RMC sentence into RMCData."""
    clean = sentence.strip()
    if "*" in clean:
        clean = clean.split("*")[0]

    parts = clean.split(",")
    if len(parts) < 10:
        raise NMEAParseError(f"RMC sentence has insufficient fields ({len(parts)} < 10): {sentence}")

    utc_time = parts[1].strip()
    status = parts[2].strip().upper()
    lat_val, lat_hemi = parts[3].strip(), parts[4].strip()
    lon_val, lon_hemi = parts[5].strip(), parts[6].strip()
    speed_knots_str = parts[7].strip()
    track_str = parts[8].strip()
    date_str = parts[9].strip()

    latitude = parse_latitude(lat_val, lat_hemi)
    longitude = parse_longitude(lon_val, lon_hemi)

    try:
        speed_knots = float(speed_knots_str) if speed_knots_str else None
        speed_kmh = round(speed_knots * 1.852, 2) if speed_knots is not None else None
    except ValueError:
        speed_knots, speed_kmh = None, None

    try:
        track_degrees = float(track_str) if track_str else None
    except ValueError:
        track_degrees = None

    return RMCData(
        utc_time=utc_time,
        status=status,
        latitude=latitude,
        longitude=longitude,
        speed_knots=speed_knots,
        speed_kmh=speed_kmh,
        track_degrees=track_degrees,
        date_str=date_str,
    )
