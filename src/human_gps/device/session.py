"""Session lifecycle management and metadata tracking."""
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional
from human_gps.domain.enums import MountType, SubjectType
from human_gps.domain.models import SessionMetadata


class SessionManager:
    """Manages recording session lifecycle, identifiers, and persistence."""

    def __init__(
        self,
        device_id: str = "PI-ZERO-01",
        subject_id: str = "COW-001",
        subject_type: SubjectType = SubjectType.BOVINE,
        mount_type: MountType = MountType.COLLAR,
        sampling_rate_hz: int = 10,
        notes: str = "",
    ):
        now_dt = datetime.now(timezone.utc)
        now_str = now_dt.strftime("%Y%m%d_%H%M%S")
        self.date_str = now_dt.strftime("%Y-%m-%d")
        self.subject_dir = subject_type.value.lower()
        self.session_id = f"SESSION_{now_str}_{subject_id}"
        self.metadata = SessionMetadata(
            session_id=self.session_id,
            device_id=device_id,
            subject_id=subject_id,
            subject_type=subject_type,
            mount_type=mount_type,
            start_time=now_dt,
            sampling_rate_hz=sampling_rate_hz,
            notes=notes,
        )

    def save_metadata(self, directory: Path) -> Path:
        """Write session metadata to JSON."""
        directory.mkdir(parents=True, exist_ok=True)
        file_path = directory / f"{self.session_id}_meta.json"
        data = {
            "session_id": self.metadata.session_id,
            "device_id": self.metadata.device_id,
            "subject_id": self.metadata.subject_id,
            "subject_type": self.metadata.subject_type.value,
            "mount_type": self.metadata.mount_type.value,
            "start_time": self.metadata.start_time.isoformat(),
            "sampling_rate_hz": self.metadata.sampling_rate_hz,
            "notes": self.metadata.notes,
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return file_path
