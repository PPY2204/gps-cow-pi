"""Parser for NMEA VTG (Course over ground and Ground speed)."""
from dataclasses import dataclass
from typing import Optional
from human_gps.domain.exceptions import NMEAParseError


@dataclass(frozen=True)
class VTGData:
    """Decoded fields from a VTG sentence."""
    track_true: Optional[float]
    track_mag: Optional[float]
    speed_knots: Optional[float]
    speed_kmh: Optional[float]
    mode: str = ""


def parse_vtg(sentence: str) -> VTGData:
    """Parse a VTG sentence (e.g. $GNVTG or $GPVTG) into VTGData."""
    clean = sentence.strip()
    if "*" in clean:
        clean = clean.split("*")[0]

    parts = clean.split(",")
    if len(parts) < 8:
        raise NMEAParseError(f"VTG sentence has insufficient fields ({len(parts)} < 8): {sentence}")

    true_str = parts[1].strip()
    mag_str = parts[3].strip()
    knots_str = parts[5].strip()
    kmh_str = parts[7].strip()
    mode = parts[9].strip() if len(parts) > 9 else ""

    try:
        track_true = float(true_str) if true_str else None
    except ValueError:
        track_true = None

    try:
        track_mag = float(mag_str) if mag_str else None
    except ValueError:
        track_mag = None

    try:
        speed_knots = float(knots_str) if knots_str else None
    except ValueError:
        speed_knots = None

    try:
        speed_kmh = float(kmh_str) if kmh_str else None
    except ValueError:
        speed_kmh = None

    # If speed in km/h is missing but knots is present, derive it
    if speed_kmh is None and speed_knots is not None:
        speed_kmh = round(speed_knots * 1.852, 2)

    return VTGData(
        track_true=track_true,
        track_mag=track_mag,
        speed_knots=speed_knots,
        speed_kmh=speed_kmh,
        mode=mode,
    )
