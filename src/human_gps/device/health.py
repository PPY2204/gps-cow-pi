"""Device health, sampling rate estimation, and diagnostic metrics."""
from collections import Counter
import time
from typing import Dict, List, Optional
from human_gps.domain.models import GPSMeasurement


class HealthMonitor:
    """Tracks acquisition statistics, actual sampling frequency, and quality metrics."""

    def __init__(self):
        self.start_wall_time = time.time()
        self.last_seen_time: Optional[float] = None
        self.last_sentence: str = ""
        self.total_sentences_read = 0
        self.total_epochs = 0
        self.accepted_epochs = 0
        self.rejected_epochs = 0
        self.rejection_counts: Counter[str] = Counter()
        self.behavior_counts: Counter[str] = Counter()

        self._recent_timestamps: List[float] = []

    def record_sentence(self, sentence: str = "") -> None:
        self.total_sentences_read += 1
        self.last_seen_time = time.time()
        if sentence:
            self.last_sentence = sentence

    def record_measurement(self, measurement: GPSMeasurement) -> None:
        self.total_epochs += 1
        now = time.time()
        self._recent_timestamps.append(now)
        # Keep sliding window of last 50 timestamps for instantaneous Hz
        if len(self._recent_timestamps) > 50:
            self._recent_timestamps.pop(0)

        if measurement.is_accepted:
            self.accepted_epochs += 1
        else:
            self.rejected_epochs += 1
            if measurement.quality:
                for r in measurement.quality.rejection_reasons:
                    self.rejection_counts[r] += 1

        self.behavior_counts[measurement.behavior_state.value] += 1

    @property
    def instantaneous_hz(self) -> float:
        """Estimate actual incoming Hz over the recent epoch sliding window."""
        if len(self._recent_timestamps) < 2:
            return 0.0
        dt = self._recent_timestamps[-1] - self._recent_timestamps[0]
        if dt <= 0:
            return 0.0
        return (len(self._recent_timestamps) - 1) / dt

    @property
    def fix_rate_percent(self) -> float:
        """Percentage of epochs accepted by quality engine."""
        if self.total_epochs == 0:
            return 0.0
        return (self.accepted_epochs / self.total_epochs) * 100.0

    def summary(self) -> Dict[str, object]:
        uptime_s = max(0.001, time.time() - self.start_wall_time)
        return {
            "uptime_seconds": round(uptime_s, 1),
            "total_sentences": self.total_sentences_read,
            "total_epochs": self.total_epochs,
            "accepted_epochs": self.accepted_epochs,
            "rejected_epochs": self.rejected_epochs,
            "fix_rate_percent": round(self.fix_rate_percent, 1),
            "current_sampling_hz": round(self.instantaneous_hz, 1),
            "rejections": dict(self.rejection_counts),
            "behaviors": dict(self.behavior_counts),
        }
