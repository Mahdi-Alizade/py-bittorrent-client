from core.lpd_service import LocalPeerDiscovery


def test_lpd_announce_packet_build_and_parse():
    info_hash = bytes.fromhex("0123456789abcdef0123456789abcdef01234567")
    lpd = LocalPeerDiscovery(listen_port=6889, cookie="testcookie123")

    packet = lpd.build_announce_packet(info_hash)
    decoded_text = packet.decode("ascii")

    assert "BT-SEARCH * HTTP/1.1" in decoded_text
    assert "Host: 239.192.152.143:6771" in decoded_text
    assert "Port: 6889" in decoded_text
    assert "Infohash: 0123456789abcdef0123456789abcdef01234567" in decoded_text

    parsed = LocalPeerDiscovery.parse_announce_packet(packet)
    assert parsed is not None
    assert parsed["port"] == "6889"
    assert parsed["infohash"] == "0123456789abcdef0123456789abcdef01234567"
    assert parsed["cookie"] == "testcookie123"


def test_lpd_ignores_malformed_packets():
    assert LocalPeerDiscovery.parse_announce_packet(b"GET / HTTP/1.1\r\n\r\n") is None
    assert LocalPeerDiscovery.parse_announce_packet(b"BT-SEARCH * HTTP/1.1\r\nPort: 6881\r\n\r\n") is None