"""Storage abstractions and protocols."""
from typing import Protocol, runtime_checkable
from human_gps.domain.models import GPSMeasurement


@runtime_checkable
class GPSStore(Protocol):
    """Abstract interface for GPS data storage backends."""

    def write_measurement(self, measurement: GPSMeasurement) -> None:
        """Persist a processed GPSMeasurement."""
        ...

    def write_raw(self, raw_sentence: str) -> None:
        """Persist a raw NMEA sentence."""
        ...

    def flush(self) -> None:
        """Flush buffered data to disk."""
        ...

    def close(self) -> None:
        """Close files and release handles."""
        ...
