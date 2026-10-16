"""NMEA 0183 XOR checksum calculation and verification."""


def compute_checksum(sentence: str) -> str:
    """Compute the 2-digit uppercase hex checksum for an NMEA sentence.
    Excludes leading '$' or '!' and everything starting from '*'.
    """
    clean = sentence.strip()
    if clean.startswith(("$", "!")):
        clean = clean[1:]
    if "*" in clean:
        clean = clean.split("*")[0]

    csum = 0
    for char in clean:
        csum ^= ord(char)
    return f"{csum:02X}"


def verify_checksum(sentence: str) -> bool:
    """Check if the provided NMEA sentence has a valid checksum."""
    clean = sentence.strip()
    if "*" not in clean:
        return False

    body, given_csum = clean.split("*", 1)
    given_csum = given_csum[:2].upper()

    expected_csum = compute_checksum(body)
    return given_csum == expected_csum
