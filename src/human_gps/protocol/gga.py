"""Parser for NMEA GGA (Global Positioning System Fix Data)."""
from dataclasses import dataclass
from typing import Optional
from human_gps.domain.enums import FixQuality
from human_gps.domain.exceptions import NMEAParseError
from human_gps.protocol.coordinates import parse_latitude, parse_longitude


@dataclass(frozen=True)
class GGAData:
    """Decoded fields from a GGA sentence."""
    utc_time: str
    latitude: Optional[float]
    longitude: Optional[float]
    fix_quality: FixQuality
    satellites: int
    hdop: Optional[float]
    altitude: Optional[float]


def parse_gga(sentence: str) -> GGAData:
    """Parse a GGA sentence (e.g. $GNGGA or $GPGGA) into GGAData."""
    clean = sentence.strip()
    if "*" in clean:
        clean = clean.split("*")[0]

    parts = clean.split(",")
    if len(parts) < 10:
        raise NMEAParseError(f"GGA sentence has insufficient fields ({len(parts)} < 10): {sentence}")

    utc_time = parts[1].strip()
    lat_val, lat_hemi = parts[2].strip(), parts[3].strip()
    lon_val, lon_hemi = parts[4].strip(), parts[5].strip()
    fix_str = parts[6].strip()
    sats_str = parts[7].strip()
    hdop_str = parts[8].strip()
    alt_str = parts[9].strip()

    # Parse coordinates
    latitude = parse_latitude(lat_val, lat_hemi)
    longitude = parse_longitude(lon_val, lon_hemi)

    # Parse fix quality
    try:
        fix_int = int(fix_str) if fix_str else 0
        fix_quality = FixQuality(fix_int)
    except (ValueError, ValueError):
        fix_quality = FixQuality.INVALID

    # Parse satellites
    try:
        satellites = int(sats_str) if sats_str else 0
    except ValueError:
        satellites = 0

    # Parse HDOP
    try:
        hdop = float(hdop_str) if hdop_str else None
    except ValueError:
        hdop = None

    # Parse Altitude
    try:
        altitude = float(alt_str) if alt_str else None
    except ValueError:
        altitude = None

    return GGAData(
        utc_time=utc_time,
        latitude=latitude,
        longitude=longitude,
        fix_quality=fix_quality,
        satellites=satellites,
        hdop=hdop,
        altitude=altitude,
    )
