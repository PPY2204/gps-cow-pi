"""Epoch synchronizer for pairing GGA and VTG sentences from high-frequency GNSS."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from human_gps.protocol.gga import GGAData
from human_gps.protocol.rmc import RMCData
from human_gps.protocol.vtg import VTGData


@dataclass
class EpochBundle:
    """Consolidated sentences belonging to a single GNSS sampling epoch."""
    utc_time: str
    arrival_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    gga: Optional[GGAData] = None
    vtg: Optional[VTGData] = None
    rmc: Optional[RMCData] = None
    raw_lines: List[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """True if we have both position (GGA) and velocity (VTG)."""
        return self.gga is not None and (self.vtg is not None or self.rmc is not None)


class EpochSynchronizer:
    """Buffers and groups incoming NMEA data into synchronized epoch bundles."""

    def __init__(self):
        self._current_bundle: Optional[EpochBundle] = None
        self._pending_vtg: Optional[tuple[VTGData, str]] = None

    def feed_gga(self, gga: GGAData, raw_line: str) -> Optional[EpochBundle]:
        """Feed a GGA sentence. If timestamp changed, emits previous bundle."""
        emitted = None
        if self._current_bundle is not None:
            if self._current_bundle.utc_time != gga.utc_time:
                emitted = self._current_bundle
                self._current_bundle = EpochBundle(
                    utc_time=gga.utc_time,
                    gga=gga,
                    raw_lines=[raw_line],
                )
                if self._pending_vtg is not None:
                    vtg, vtg_raw = self._pending_vtg
                    self._current_bundle.vtg = vtg
                    self._current_bundle.raw_lines.append(vtg_raw)
                    self._pending_vtg = None
                return emitted
            else:
                self._current_bundle.gga = gga
                self._current_bundle.raw_lines.append(raw_line)
                return None

        self._current_bundle = EpochBundle(
            utc_time=gga.utc_time,
            gga=gga,
            raw_lines=[raw_line],
        )
        if self._pending_vtg is not None:
            vtg, vtg_raw = self._pending_vtg
            self._current_bundle.vtg = vtg
            self._current_bundle.raw_lines.append(vtg_raw)
            self._pending_vtg = None
        return None

    def feed_vtg(self, vtg: VTGData, raw_line: str) -> None:
        """Attach VTG to the active epoch bundle or stash if bundle not yet created."""
        if self._current_bundle is not None:
            self._current_bundle.vtg = vtg
            self._current_bundle.raw_lines.append(raw_line)
        else:
            self._pending_vtg = (vtg, raw_line)

    def feed_rmc(self, rmc: RMCData, raw_line: str) -> Optional[EpochBundle]:
        """Feed RMC data. Can also drive epoch boundaries if GGA is absent."""
        if self._current_bundle is not None and self._current_bundle.utc_time == rmc.utc_time:
            self._current_bundle.rmc = rmc
            self._current_bundle.raw_lines.append(raw_line)
            return None

        if self._current_bundle is not None and self._current_bundle.utc_time != rmc.utc_time:
            emitted = self._current_bundle
            self._current_bundle = EpochBundle(
                utc_time=rmc.utc_time,
                rmc=rmc,
                raw_lines=[raw_line],
            )
            if self._pending_vtg is not None:
                vtg, vtg_raw = self._pending_vtg
                self._current_bundle.vtg = vtg
                self._current_bundle.raw_lines.append(vtg_raw)
                self._pending_vtg = None
            return emitted

        self._current_bundle = EpochBundle(
            utc_time=rmc.utc_time,
            rmc=rmc,
            raw_lines=[raw_line],
        )
        if self._pending_vtg is not None:
            vtg, vtg_raw = self._pending_vtg
            self._current_bundle.vtg = vtg
            self._current_bundle.raw_lines.append(vtg_raw)
            self._pending_vtg = None
        return None

    def flush(self) -> Optional[EpochBundle]:
        """Emit any remaining buffered epoch."""
        bundle = self._current_bundle
        self._current_bundle = None
        self._pending_vtg = None
        return bundle
