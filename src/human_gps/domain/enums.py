from enum import Enum, IntEnum


class FixQuality(IntEnum):
    """NMEA GGA Fix Quality indicator."""
    INVALID = 0
    GPS_FIX = 1
    DGPS_FIX = 2
    PPS_FIX = 3
    RTK_FIX = 4
    RTK_FLOAT = 5
    ESTIMATED = 6
    MANUAL = 7
    SIMULATION = 8

    @property
    def is_valid(self) -> bool:
        return self in (
            FixQuality.GPS_FIX,
            FixQuality.DGPS_FIX,
            FixQuality.RTK_FIX,
            FixQuality.RTK_FLOAT,
        )


class SubjectType(str, Enum):
    """Entity type being tracked."""
    BOVINE = "BOVINE"        # Cattle (Cows, Bulls, Calves)
    HUMAN = "HUMAN"          # Human researcher or handler
    OVINE = "OVINE"          # Sheep, Goats
    WILDLIFE = "WILDLIFE"    # Deer, Boar, etc.
    VEHICLE = "VEHICLE"      # Farm tractor, ATV
    STATIC_STATION = "STATIC_STATION" # Base station / reference point


class MountType(str, Enum):
    """Attachment / mounting method on subject."""
    COLLAR = "COLLAR"        # Neck collar (standard for cattle)
    BACKPACK = "BACKPACK"    # Backpack / Vest (human, dog)
    HARNESS = "HARNESS"      # Body harness (horse, cattle halter)
    EAR_TAG = "EAR_TAG"      # Ear tag
    HANDHELD = "HANDHELD"    # Handheld / test fixture


class QualityFlag(str, Enum):
    """Quality engine validation and filter tags."""
    VALID = "VALID"
    NO_FIX = "NO_FIX"
    LOW_SATELLITES = "LOW_SATELLITES"
    HIGH_HDOP = "HIGH_HDOP"
    SPEED_EXCEEDED = "SPEED_EXCEEDED"
    ACCEL_EXCEEDED = "ACCEL_EXCEEDED"
    JITTER_SUPPRESSED = "JITTER_SUPPRESSED"
    COORDINATE_OUT_OF_BOUNDS = "COORDINATE_OUT_OF_BOUNDS"
    TIME_JUMP = "TIME_JUMP"
    INCOMPLETE_EPOCH = "INCOMPLETE_EPOCH"


class BehaviorState(str, Enum):
    """Classified or inferred behavioral state."""
    RESTING = "RESTING"      # Lying down or stationary
    GRAZING = "GRAZING"      # Slow moving foraging (0.3 - 1.8 km/h)
    WALKING = "WALKING"      # Directed travel
    RUNNING = "RUNNING"      # Fast movement / panic
    UNKNOWN = "UNKNOWN"
