import socket
import struct
from core.tracker_client import TrackerClient


class TestTrackerClient:
    def test_parse_compact_peers(self):
        # Prepare two peers: 127.0.0.1:6881 and 192.168.1.10:8080
        peer1_ip = socket.inet_aton("127.0.0.1")
        peer1_port = struct.pack('>H', 6881)

        peer2_ip = socket.inet_aton("192.168.1.10")
        peer2_port = struct.pack('>H', 8080)

        compact_payload = peer1_ip + peer1_port + peer2_ip + peer2_port

        peers = TrackerClient.parse_compact_peers(compact_payload)
        assert len(peers) == 2
        assert peers[0] == ("127.0.0.1", 6881)
        assert peers[1] == ("192.168.1.10", 8080)

    def test_parse_compact_peers_invalid_length(self):
        # 5 bytes instead of multiple of 6
        invalid_data = b"\x7f\x00\x00\x01\x1a"
        peers = TrackerClient.parse_compact_peers(invalid_data)
        assert peers == []

    def test_unsupported_tracker_scheme(self):
        client = TrackerClient(b"12345678901234567890", b"peeridpeeridpeerid01")
        result = client.announce("ftp://tracker.example.com/announce")
        assert "error" in result
        assert result["peers"] == []