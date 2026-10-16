"""Replay service for deterministic simulation of field datasets without hardware."""
import logging
from pathlib import Path
import time
from typing import Optional

from human_gps.device.session import SessionManager
from human_gps.domain.enums import MountType, SubjectType
from human_gps.domain.models import SubjectProfile
from human_gps.services.recorder import RecorderService

logger = logging.getLogger(__name__)


class ReplayService:
    """Replays raw NMEA recordings to test, benchmark, and verify filter parameters."""

    def __init__(
        self,
        filepath: Path,
        profile: SubjectProfile,
        subject_id: str = "SIM-001",
        output_dir: Path = Path("data/processed"),
        realtime_delay: bool = False,
        simulated_hz: float = 10.0,
        on_measurement: Optional[object] = None,
    ):
        self.filepath = Path(filepath)
        self.profile = profile
        self.output_dir = output_dir
        self.realtime_delay = realtime_delay
        self.simulated_hz = simulated_hz

        self.session_mgr = SessionManager(
            device_id="REPLAY-ENGINE",
            subject_id=subject_id,
            subject_type=profile.subject_type,
            mount_type=MountType.HANDHELD,
            notes=f"Replayed from {self.filepath.name}",
        )

        self.recorder = RecorderService(
            session_mgr=self.session_mgr,
            profile=self.profile,
            raw_dir=Path("data/raw"),
            processed_dir=self.output_dir,
            enable_sqlite=True,
            enable_raw=False,  # Input is already raw
            on_measurement=on_measurement,
        )

    def run(self) -> dict:
        """Execute the replay and return summary statistics."""
        if not self.filepath.exists():
            raise FileNotFoundError(f"Fixture file not found: {self.filepath}")

        start_t = time.time()
        delay_s = (1.0 / self.simulated_hz) if (self.realtime_delay and self.simulated_hz > 0) else 0.0

        with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or not line.startswith(("$", "!")):
                    continue

                bundle = self.recorder.process_sentence(line)
                if bundle is not None:
                    self.recorder.handle_epoch(bundle)
                    if delay_s > 0:
                        time.sleep(delay_s)

        # Flush trailing epoch
        trailing = self.recorder.synchronizer.flush()
        if trailing is not None:
            self.recorder.handle_epoch(trailing)

        csv_path = str(self.recorder.csv_store.filepath) if self.recorder.csv_store else ""
        self.recorder.close()

        summary = self.recorder.health.summary()
        summary["session_id"] = self.session_mgr.session_id
        summary["wall_time_seconds"] = round(time.time() - start_t, 2)
        summary["output_csv"] = csv_path
        return summary
