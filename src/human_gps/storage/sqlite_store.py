"""SQLite storage backend for indexed, queryable trajectory measurements."""
from pathlib import Path
import sqlite3
from typing import Union
from human_gps.domain.models import GPSMeasurement


class SQLiteStore:
    """Stores GPS measurements in a local SQLite database with indices."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        # WAL mode and NORMAL synchronous: massive write performance boost on SD card
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._uncommitted_count = 0
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                utc_time TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                altitude REAL,
                fix_quality INTEGER,
                satellites INTEGER,
                hdop REAL,
                speed_kmh REAL,
                track_degrees REAL,
                distance_m REAL,
                behavior_state TEXT,
                accepted INTEGER,
                flags TEXT,
                rejection_reasons TEXT
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_utc ON measurements(utc_time)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_accepted ON measurements(accepted)"
        )
        self._conn.commit()

    def write_measurement(self, measurement: GPSMeasurement) -> None:
        quality = measurement.quality
        accepted = quality.accepted if quality else True
        flags_str = ";".join([f.value for f in quality.flags]) if quality else ""
        reasons_str = ";".join(quality.rejection_reasons) if quality else ""

        self._conn.execute(
            """
            INSERT INTO measurements (
                timestamp, utc_time, latitude, longitude, altitude,
                fix_quality, satellites, hdop, speed_kmh, track_degrees,
                distance_m, behavior_state, accepted, flags, rejection_reasons
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                measurement.timestamp.isoformat(),
                measurement.utc_time,
                measurement.latitude,
                measurement.longitude,
                measurement.altitude,
                measurement.fix_quality.value,
                measurement.satellites,
                measurement.hdop,
                measurement.speed_kmh,
                measurement.track_degrees,
                measurement.distance_from_previous_m,
                measurement.behavior_state.value,
                1 if accepted else 0,
                flags_str,
                reasons_str,
            ),
        )
        self._uncommitted_count += 1
        # Commit every 50 records to minimize SD card sync latency
        if self._uncommitted_count >= 50:
            self._conn.commit()
            self._uncommitted_count = 0

    def flush(self) -> None:
        if self._conn is not None:
            self._conn.commit()
            self._uncommitted_count = 0

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.commit()
                self._conn.close()
            except Exception:
                pass
            finally:
                self._conn = None
                self._uncommitted_count = 0
