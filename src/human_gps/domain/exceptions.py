"""Domain and protocol exceptions."""


class GPSException(Exception):
    """Base exception for GPS system."""
    pass


class NMEAParseError(GPSException):
    """Raised when an NMEA sentence cannot be parsed."""
    pass


class ChecksumMismatchError(NMEAParseError):
    """Raised when NMEA sentence checksum fails verification."""
    pass


class DeviceConnectionError(GPSException):
    """Raised when communication with GPS device fails."""
    pass


class ConfigurationError(GPSException):
    """Raised when configuration values are missing or invalid."""
    pass
