"""Recorder service orchestrating live acquisition, processing, and multi-store persistence."""
import logging
from pathlib import Path
import threading
import time
from typing import Generator, Optional

from human_gps.acquisition.reconnect import ResilientStreamReader
from human_gps.device.health import HealthMonitor
from human_gps.device.session import SessionManager
from human_gps.domain.models import GPSMeasurement, SubjectProfile
from human_gps.pipeline.filter import KinematicFilter
from human_gps.pipeline.measurement import MeasurementBuilder
from human_gps.pipeline.synchronizer import EpochBundle, EpochSynchronizer
from human_gps.pipeline.validator import QualityValidator
from human_gps.protocol.gga import GGAData
from human_gps.protocol.nmea import NMEARouter
from human_gps.protocol.rmc import RMCData
from human_gps.protocol.vtg import VTGData
from human_gps.storage.csv_store import CSVStore
from human_gps.storage.raw_store import RawStore
from human_gps.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)


class RecorderService:
    """Core runtime engine executing on the Raspberry Pi Zero 2 W."""

    def __init__(
        self,
        session_mgr: SessionManager,
        profile: SubjectProfile,
        raw_dir: Path = Path("data/raw"),
        processed_dir: Path = Path("data/processed"),
        min_satellites: int = 4,
        max_hdop: float = 5.0,
        enable_sqlite: bool = True,
        enable_raw: bool = True,
        on_measurement: Optional[object] = None,
        on_raw_line: Optional[object] = None,
        is_recording: bool = True,
        strict_checksum: bool = True,
    ):
        self._lock = threading.RLock()
        self.session_mgr = session_mgr
        self.profile = profile
        self.health = HealthMonitor()
        self.on_measurement = on_measurement
        self.on_raw_line = on_raw_line
        self.latest_measurement: Optional[GPSMeasurement] = None
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir
        self.enable_raw = enable_raw
        self.enable_sqlite = enable_sqlite
        self.is_recording = is_recording
        self.strict_checksum = strict_checksum

        # Instant real-time telemetry dictionary (always updated on every raw sentence)
        self.live_telemetry = {
            "latitude": None,
            "longitude": None,
            "altitude": None,
            "speed_kmh": None,
            "satellites": 0,
            "hdop": None,
            "fix_quality": "INVALID",
            "utc_time": None,
            "last_update_ts": 0.0,
        }

        # Pipeline components
        self.router = NMEARouter(strict_checksum=self.strict_checksum)
        self.synchronizer = EpochSynchronizer()
        self.builder = MeasurementBuilder()
        self.validator = QualityValidator(
            min_satellites=min_satellites,
            max_hdop=max_hdop,
            require_fix=True,
        )
        self.filter = KinematicFilter(profile=self.profile)

        self.raw_store: Optional[RawStore] = None
        self.csv_store: Optional[CSVStore] = None
        self.sqlite_store: Optional[SQLiteStore] = None

        if self.is_recording:
            self._init_stores()

    def _init_stores(self) -> None:
        with self._lock:
            session_id = self.session_mgr.session_id
            sub_dir = self.session_mgr.subject_dir
            d_str = self.session_mgr.date_str

            proc_dir = self.processed_dir / sub_dir / d_str
            raw_dir = self.raw_dir / sub_dir / d_str

            raw_file = raw_dir / f"{session_id}_raw.nmea"
            csv_file = proc_dir / f"{session_id}.csv"
            db_file = proc_dir / f"{session_id}.db"

            self.raw_store = RawStore(raw_file) if self.enable_raw else None
            self.csv_store = CSVStore(csv_file)
            self.sqlite_store = SQLiteStore(db_file) if self.enable_sqlite else None

            # Persist session metadata JSON alongside processed data
            try:
                self.session_mgr.save_metadata(proc_dir)
            except Exception as e:
                logger.warning(f"Failed to persist session metadata: {e}")

    def start_new_session(self, subject_id: Optional[str] = None) -> str:
        """Close current stores and roll to a new timestamped session."""
        with self._lock:
            self.close()
            sub_id = subject_id or self.session_mgr.metadata.subject_id
            self.session_mgr = SessionManager(
                device_id=self.session_mgr.metadata.device_id,
                subject_id=sub_id,
                subject_type=self.profile.subject_type,
                mount_type=self.session_mgr.metadata.mount_type,
                sampling_rate_hz=self.session_mgr.metadata.sampling_rate_hz,
            )
            self._init_stores()
            self.is_recording = True
            return self.session_mgr.session_id

    def stop_recording(self) -> None:
        """Stop recording and flush stores."""
        with self._lock:
            self.is_recording = False
            self.close()

    def process_sentence(self, sentence: str) -> Optional[EpochBundle]:
        """Process a single raw NMEA sentence through router and synchronizer."""
        self.health.record_sentence(sentence)
        with self._lock:
            if self.raw_store and self.is_recording:
                self.raw_store.write_raw(sentence)

        if self.on_raw_line:
            try:
                self.on_raw_line(sentence)
            except Exception:
                pass

        try:
            sent_type, parsed = self.router.route(sentence)
        except Exception as e:
            logger.debug(f"Router skipped line: {e}")
            return None

        # Instantly update live telemetry so Web UI never freezes
        now_ts = time.time()
        emitted_bundle = None

        if sent_type == "GGA" and isinstance(parsed, GGAData):
            self.live_telemetry["satellites"] = parsed.satellites
            self.live_telemetry["hdop"] = parsed.hdop
            self.live_telemetry["fix_quality"] = parsed.fix_quality.value
            self.live_telemetry["altitude"] = parsed.altitude
            if parsed.latitude is not None and parsed.longitude is not None:
                self.live_telemetry["latitude"] = parsed.latitude
                self.live_telemetry["longitude"] = parsed.longitude
            if parsed.utc_time:
                self.live_telemetry["utc_time"] = parsed.utc_time
            self.live_telemetry["last_update_ts"] = now_ts
            emitted_bundle = self.synchronizer.feed_gga(parsed, sentence)
        elif sent_type == "VTG" and isinstance(parsed, VTGData):
            if parsed.speed_kmh is not None:
                self.live_telemetry["speed_kmh"] = parsed.speed_kmh
            self.live_telemetry["last_update_ts"] = now_ts
            self.synchronizer.feed_vtg(parsed, sentence)
        elif sent_type == "RMC" and isinstance(parsed, RMCData):
            if parsed.speed_kmh is not None:
                self.live_telemetry["speed_kmh"] = parsed.speed_kmh
            if parsed.latitude is not None and parsed.longitude is not None:
                self.live_telemetry["latitude"] = parsed.latitude
                self.live_telemetry["longitude"] = parsed.longitude
            if parsed.utc_time:
                self.live_telemetry["utc_time"] = parsed.utc_time
            self.live_telemetry["last_update_ts"] = now_ts
            emitted_bundle = self.synchronizer.feed_rmc(parsed, sentence)

        return emitted_bundle

    def handle_epoch(self, bundle: EpochBundle) -> None:
        """Construct measurement, validate, filter, and write to stores."""
        measurement = self.builder.build(bundle)
        measurement.quality = self.validator.validate(measurement)
        measurement = self.filter.filter(measurement)

        with self._lock:
            if self.is_recording:
                if self.csv_store:
                    self.csv_store.write_measurement(measurement)
                if self.sqlite_store:
                    self.sqlite_store.write_measurement(measurement)

        self.health.record_measurement(measurement)
        self.latest_measurement = measurement

        if self.on_measurement:
            try:
                self.on_measurement(measurement)
            except Exception as e:
                logger.debug(f"Error in on_measurement callback: {e}")

    def run_stream(self, line_generator: Generator[str, None, None]) -> None:
        """Run continuous stream loop."""
        try:
            for line in line_generator:
                bundle = self.process_sentence(line)
                if bundle is not None:
                    self.handle_epoch(bundle)
        finally:
            # Flush final buffered bundle
            remaining = self.synchronizer.flush()
            if remaining is not None:
                self.handle_epoch(remaining)

    def close(self) -> None:
        """Cleanly close all stores."""
        with self._lock:
            if self.raw_store:
                try:
                    self.raw_store.close()
                except Exception:
                    pass
                self.raw_store = None
            if self.csv_store:
                try:
                    self.csv_store.close()
                except Exception:
                    pass
                self.csv_store = None
            if self.sqlite_store:
                try:
                    self.sqlite_store.close()
                except Exception:
                    pass
                self.sqlite_store = None
