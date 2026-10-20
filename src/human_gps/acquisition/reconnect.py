"""Resilient reconnection loop for field IoT GPS acquisition."""
import logging
import os
import subprocess
import time
from typing import Callable, Generator

from human_gps.acquisition.serial_reader import SerialReader
from human_gps.domain.exceptions import DeviceConnectionError

logger = logging.getLogger(__name__)


class ResilientStreamReader:
    """Wraps SerialReader with automatic retry and backoff when connection drops."""

    def __init__(
        self,
        port: str = "/dev/rfcomm0",
        baud_rate: int = 115200,
        timeout: float = 2.0,
        reconnect_delay_seconds: float = 3.0,
        max_retries: int = -1,  # -1 for infinite retries in field
        on_reconnect_callback: Callable[[], None] | None = None,
        mac_address: str | None = None,
    ):
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.reconnect_delay = reconnect_delay_seconds
        self.max_retries = max_retries
        self.on_reconnect = on_reconnect_callback
        self.mac_address = mac_address or os.environ.get("NARO_DROGGER_MAC")
        self._running = False
        self._reader: SerialReader | None = None

    def stream_lines(self) -> Generator[str, None, None]:
        """Continuously yield lines across reconnect cycles."""
        self._running = True
        attempt = 0

        while self._running:
            try:
                # If /dev/rfcomm0 does not exist, try auto-binding to DG-PRO1S if on Linux
                if not os.path.exists(self.port) and "rfcomm" in self.port and self.mac_address:
                    logger.info(f"{self.port} not found, attempting auto-bind to {self.mac_address}...")
                    try:
                        subprocess.run(["sudo", "-n", "rfcomm", "bind", "0", self.mac_address, "1"], timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except Exception:
                        pass

                self._reader = SerialReader(self.port, self.baud_rate, self.timeout)
                logger.info(f"Connecting to GNSS on {self.port}...")
                for line in self._reader.read_lines():
                    if not self._running:
                        break
                    yield line
                attempt = 0
            except DeviceConnectionError as e:
                attempt += 1
                logger.warning(f"Connection lost ({e}). Attempt {attempt} to reconnect...")
                if self._reader:
                    self._reader.close()
                if self.on_reconnect:
                    try:
                        self.on_reconnect()
                    except Exception as cb_err:
                        logger.warning(f"Error in reconnect callback: {cb_err}")

                if 0 <= self.max_retries < attempt:
                    logger.error(f"Max retries ({self.max_retries}) reached. Exiting.")
                    break

                time.sleep(self.reconnect_delay)
            except Exception as e:
                logger.exception(f"Unexpected error in reader stream: {e}")
                time.sleep(self.reconnect_delay)

    def stop(self) -> None:
        """Signal the stream loop to stop."""
        self._running = False
        if self._reader:
            self._reader.close()
