import base64
import pytest
from core.magnet_parser import MagnetURIParser


def test_parse_hex_magnet_link():
    hex_hash = "0123456789abcdef0123456789abcdef01234567"
    uri = (
        f"magnet:?xt=urn:btih:{hex_hash}"
        "&dn=Ubuntu+24.04+LTS"
        "&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce"
        "&tr=http%3A%2F%2Ftracker.example.com%3A80%2Fannounce"
    )

    parsed = MagnetURIParser.parse(uri)
    assert parsed.info_hash == bytes.fromhex(hex_hash)
    assert parsed.info_hash_hex == hex_hash
    assert parsed.display_name == "Ubuntu 24.04 LTS"
    assert len(parsed.trackers) == 2
    assert parsed.trackers[0] == "udp://tracker.opentrackr.org:1337/announce"


def test_parse_base32_magnet_link():
    raw_bytes = b"12345678901234567890"
    b32_hash = base64.b32encode(raw_bytes).decode("ascii")
    assert len(b32_hash) == 32

    uri = f"magnet:?xt=urn:btih:{b32_hash}&dn=Archive.tar"
    parsed = MagnetURIParser.parse(uri)

    assert parsed.info_hash == raw_bytes
    assert parsed.display_name == "Archive.tar"
    assert parsed.trackers == []


def test_invalid_magnet_raises_error():
    with pytest.raises(ValueError):
        MagnetURIParser.parse("http://example.com/file.torrent")

    with pytest.raises(ValueError):
        MagnetURIParser.parse("magnet:?dn=NoHashProvided")