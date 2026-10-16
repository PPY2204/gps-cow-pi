"""GNSS quality validation engine."""
from human_gps.domain.enums import QualityFlag
from human_gps.domain.models import GPSMeasurement, QualityResult


class QualityValidator:
    """Validates raw GNSS measurement parameters before kinematic filtering."""

    def __init__(
        self,
        min_satellites: int = 4,
        max_hdop: float = 5.0,
        require_fix: bool = True,
    ):
        self.min_satellites = min_satellites
        self.max_hdop = max_hdop
        self.require_fix = require_fix

    def validate(self, measurement: GPSMeasurement) -> QualityResult:
        """Evaluate satellite fix, count, HDOP and coordinate bounds."""
        res = QualityResult()

        # 1. Fix quality check
        if self.require_fix and not measurement.fix_quality.is_valid:
            res.fix_valid = False
            res.add_rejection(QualityFlag.NO_FIX, f"Invalid GNSS fix ({measurement.fix_quality.name})")

        # 2. Satellite count
        if measurement.satellites < self.min_satellites:
            res.satellite_valid = False
            res.add_rejection(
                QualityFlag.LOW_SATELLITES,
                f"Satellites ({measurement.satellites}) below threshold ({self.min_satellites})",
            )

        # 3. HDOP (Horizontal Dilution of Precision)
        if measurement.hdop is not None and measurement.hdop > self.max_hdop:
            res.hdop_valid = False
            res.add_rejection(
                QualityFlag.HIGH_HDOP,
                f"HDOP ({measurement.hdop}) exceeds threshold ({self.max_hdop})",
            )

        # 4. Coordinate range sanity check
        if measurement.latitude is not None:
            if not (-90.0 <= measurement.latitude <= 90.0):
                res.add_rejection(
                    QualityFlag.COORDINATE_OUT_OF_BOUNDS,
                    f"Latitude {measurement.latitude} out of bounds",
                )
        if measurement.longitude is not None:
            if not (-180.0 <= measurement.longitude <= 180.0):
                res.add_rejection(
                    QualityFlag.COORDINATE_OUT_OF_BOUNDS,
                    f"Longitude {measurement.longitude} out of bounds",
                )

        if not measurement.has_coordinates:
            res.add_rejection(QualityFlag.NO_FIX, "Coordinates missing in measurement")

        return res
