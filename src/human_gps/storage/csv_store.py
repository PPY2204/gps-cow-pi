"""CSV storage implementation with explicit quality and rejection audit trail."""
import csv
from pathlib import Path
from typing import Optional, TextIO, Union
from human_gps.domain.models import GPSMeasurement

CSV_COLUMNS = [
    "timestamp",
    "utc_time",
    "latitude",
    "longitude",
    "altitude",
    "fix_quality",
    "satellites",
    "hdop",
    "speed_kmh",
    "track_degrees",
    "distance_m",
    "behavior_state",
    "accepted",
    "flags",
    "rejection_reasons",
]


class CSVStore:
    """Writes GPS measurements to CSV with complete validation metadata."""

    def __init__(self, filepath: Union[str, Path]):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        exists = self.filepath.exists() and self.filepath.stat().st_size > 0

        self._file: TextIO = open(self.filepath, "a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._write_count = 0

        if not exists:
            self._writer.writerow(CSV_COLUMNS)
            self._file.flush()

    def write_measurement(self, measurement: GPSMeasurement) -> None:
        """Write single measurement row."""
        quality = measurement.quality
        accepted = quality.accepted if quality else True
        flags_str = ";".join([f.value for f in quality.flags]) if quality else ""
        reasons_str = ";".join(quality.rejection_reasons) if quality else ""

        row = [
            measurement.timestamp.isoformat(),
            measurement.utc_time,
            f"{measurement.latitude:.7f}" if measurement.latitude is not None else "",
            f"{measurement.longitude:.7f}" if measurement.longitude is not None else "",
            f"{measurement.altitude:.2f}" if measurement.altitude is not None else "",
            measurement.fix_quality.value,
            measurement.satellites,
            f"{measurement.hdop:.2f}" if measurement.hdop is not None else "",
            f"{measurement.speed_kmh:.2f}" if measurement.speed_kmh is not None else "",
            f"{measurement.track_degrees:.1f}" if measurement.track_degrees is not None else "",
            f"{measurement.distance_from_previous_m:.3f}",
            measurement.behavior_state.value,
            1 if accepted else 0,
            flags_str,
            reasons_str,
        ]
        self._writer.writerow(row)
        self._write_count += 1
        if self._write_count % 50 == 0:
            self._file.flush()

    def flush(self) -> None:
        self._file.flush()

    def close(self) -> None:
        if not self._file.closed:
            self._file.flush()
            self._file.close()
