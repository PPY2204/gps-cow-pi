"""NMEA router and sentence classifier."""
from typing import Any, Optional, Tuple, Union
from human_gps.domain.exceptions import ChecksumMismatchError, NMEAParseError
from human_gps.protocol.checksum import verify_checksum
from human_gps.protocol.gga import GGAData, parse_gga
from human_gps.protocol.rmc import RMCData, parse_rmc
from human_gps.protocol.vtg import VTGData, parse_vtg


def identify_sentence(sentence: str) -> str:
    """Identify the 3-character sentence type (e.g. GGA, VTG, RMC) from talker + sentence ID."""
    clean = sentence.strip()
    if not clean.startswith(("$", "!")):
        return "UNKNOWN"

    first_field = clean[1:].split(",")[0]
    if len(first_field) >= 3:
        return first_field[-3:].upper()
    return "UNKNOWN"


class NMEARouter:
    """Validates checksum and routes NMEA lines to dedicated sentence parsers."""

    def __init__(self, strict_checksum: bool = True):
        self.strict_checksum = strict_checksum

    def route(
        self, sentence: str
    ) -> Tuple[str, Optional[Union[GGAData, VTGData, RMCData]]]:
        """Validate and route sentence to parser.

        Returns:
            Tuple[sentence_type, parsed_data_or_None]
        """
        clean = sentence.strip()
        if not clean:
            return "EMPTY", None

        # Checksum validation
        if self.strict_checksum and "*" in clean:
            if not verify_checksum(clean):
                raise ChecksumMismatchError(f"Checksum mismatch for: {clean}")

        sentence_type = identify_sentence(clean)

        try:
            if sentence_type == "GGA":
                return "GGA", parse_gga(clean)
            elif sentence_type == "VTG":
                return "VTG", parse_vtg(clean)
            elif sentence_type == "RMC":
                return "RMC", parse_rmc(clean)
            else:
                return sentence_type, None
        except Exception as e:
            if not isinstance(e, NMEAParseError):
                raise NMEAParseError(f"Failed to parse {sentence_type}: {e}") from e
            raise
