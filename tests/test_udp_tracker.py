import socket
import struct
import threading
from core.pex_protocol import PeerExchangeProtocol
from core.tracker_client import TrackerClient
from core.udp_tracker import UDPTrackerClient


def test_udp_packet_serialization_and_parsing():
    info_hash = b"H" * 20
    peer_id = b"-PY0001-123456789012"
    client = UDPTrackerClient(info_hash=info_hash, peer_id=peer_id)

    conn_pkt = client.build_connect_request(transaction_id=0x12345678)
    assert len(conn_pkt) == 16
    magic, action, tx = struct.unpack(">QII", conn_pkt)
    assert magic == UDPTrackerClient.MAGIC_CONNECTION_ID
    assert action == 0
    assert tx == 0x12345678

    ann_pkt = client.build_announce_request(
        connection_id=0xAABBCCDDEEFF0011,
        transaction_id=0x87654321,
        left=1048576,
        port=6881
    )
    assert len(ann_pkt) == 98


def test_udp_tracker_full_local_handshake():
    info_hash = b"T" * 20
    peer_id = b"-PY0001-999999999999"
    expected_peers = [("203.0.113.15", 6881), ("198.51.100.88", 51413)]
    compact_blob = PeerExchangeProtocol.encode_compact_peers(expected_peers)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    server_port = sock.getsockname()[1]
    sock.settimeout(2.0)

    def mock_udp_tracker_server():
        try:
            data1, addr1 = sock.recvfrom(1024)
            _, action1, tx1 = struct.unpack(">QII", data1[:16])
            assert action1 == UDPTrackerClient.ACTION_CONNECT
            conn_id = 0x0102030405060708
            reply1 = struct.pack(">IIQ", UDPTrackerClient.ACTION_CONNECT, tx1, conn_id)
            sock.sendto(reply1, addr1)

            data2, addr2 = sock.recvfrom(1024)
            rx_conn_id, action2, tx2 = struct.unpack(">QII", data2[:16])
            assert rx_conn_id == conn_id
            assert action2 == UDPTrackerClient.ACTION_ANNOUNCE

            reply2 = struct.pack(">IIIII", UDPTrackerClient.ACTION_ANNOUNCE, tx2, 1800, 12, 45) + compact_blob
            sock.sendto(reply2, addr2)
        finally:
            sock.close()

    t = threading.Thread(target=mock_udp_tracker_server, daemon=True)
    t.start()

    # Test unified TrackerClient routing for udp:// scheme
    unified_tracker = TrackerClient(info_hash=info_hash, peer_id=peer_id, timeout=1.5)
    result = unified_tracker.announce(f"udp://127.0.0.1:{server_port}/announce", port=6881, left=4096)

    assert result["peers"] == expected_peers
    assert result["seeders"] == 45
    assert result["leechers"] == 12
    assert result["interval"] == 1800