import pytest
from human_gps.protocol.checksum import compute_checksum, verify_checksum


def test_compute_checksum():
    sentence = "GNGGA,012345.00,3540.1234,N,13945.5678,E,1,08,1.2,45.2,M,36.5,M,,"
    csum = compute_checksum(sentence)
    assert len(csum) == 2
    # Verify hex format
    int(csum, 16)


def test_verify_checksum_valid():
    sentence = "$GNVTG,123.4,T,120.0,M,2.5,N,4.63,K,A"
    csum = compute_checksum(sentence)
    full_sentence = f"{sentence}*{csum}"
    assert verify_checksum(full_sentence) is True


def test_verify_checksum_invalid():
    bad_sentence = "$GNVTG,123.4,T,120.0,M,2.5,N,4.63,K,A*00"
    assert verify_checksum(bad_sentence) is False


def test_verify_checksum_missing():
    assert verify_checksum("$GNVTG,123.4,T") is False
