"""Bluetooth RFCOMM binding helpers for Raspberry Pi."""
import logging
import platform
import subprocess
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def is_linux() -> bool:
    return platform.system().lower() == "linux"


def bind_rfcomm(
    device_index: int = 0,
    mac_address: str = "94:51:DC:57:BE:12",
    channel: int = 1,
) -> Tuple[bool, str]:
    """Execute 'sudo rfcomm bind <dev> <mac> <channel>' on Linux Raspberry Pi."""
    if not is_linux():
        return False, "rfcomm binding is only supported on Linux/Raspberry Pi."

    cmd = ["sudo", "rfcomm", "bind", str(device_index), mac_address, str(channel)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            logger.info(f"Successfully bound /dev/rfcomm{device_index} to {mac_address} channel {channel}")
            return True, f"/dev/rfcomm{device_index} bound"
        else:
            err = res.stderr.strip() or res.stdout.strip()
            logger.error(f"rfcomm bind failed: {err}")
            return False, err
    except Exception as e:
        logger.exception("Subprocess error running rfcomm bind")
        return False, str(e)


def release_rfcomm(device_index: int = 0) -> Tuple[bool, str]:
    """Release bound rfcomm device via 'sudo rfcomm release <dev>'."""
    if not is_linux():
        return False, "rfcomm release is only supported on Linux/Raspberry Pi."

    cmd = ["sudo", "rfcomm", "release", str(device_index)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return res.returncode == 0, res.stderr.strip() or res.stdout.strip()
    except Exception as e:
        return False, str(e)
