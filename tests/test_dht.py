import os
import socket
import threading
from core.dht_client import DHTCrawler, KRPCProtocol
from core.dht_routing import DHTNode, KademliaRoutingTable
from core.parser import BDecoder, TorrentEncoder
from core.pex_protocol import PeerExchangeProtocol


def test_xor_distance_and_bucket_routing():
    local_id = b"\x00" * 20
    table = KademliaRoutingTable(local_node_id=local_id)

    close_id = b"\x00" * 19 + b"\x01"
    far_id = b"\x80" + b"\x00" * 19

    node_close = DHTNode(close_id, "10.0.0.1", 6881)
    node_far = DHTNode(far_id, "10.0.0.2", 6882)

    assert table.add_node(node_close) is True
    assert table.add_node(node_far) is True

    closest = table.find_closest_nodes(close_id, count=1)
    assert len(closest) == 1
    assert closest[0].node_id == close_id


def test_compact_26_byte_node_encoding():
    raw_id = b"12345678901234567890"
    node = DHTNode(raw_id, "192.168.1.100", 51413)
    compact = node.to_compact()
    assert len(compact) == 26

    restored = DHTNode.from_compact(compact)
    assert restored == node


def test_krpc_get_peers_query_and_response():
    tx_id = b"aa"
    sender_id = b"S" * 20
    info_hash = b"H" * 20

    query_bytes = KRPCProtocol.build_get_peers_query(tx_id, sender_id, info_hash)
    decoded_q = BDecoder(query_bytes).decode()
    assert decoded_q["q"] == "get_peers"
    assert decoded_q["t"] == "aa"

    # Simulate response with compact peers
    peer_compact = PeerExchangeProtocol.encode_compact_peers([("203.0.113.5", 6881)])
    resp_dict = {
        "t": tx_id,
        "y": "r",
        "r": {
            "id": b"R" * 20,
            "token": b"tok1",
            "values": [peer_compact]
        }
    }
    resp_bytes = TorrentEncoder.encode(resp_dict)
    parsed = KRPCProtocol.parse_response(resp_bytes)

    assert parsed is not None
    assert parsed["peers"] == [("203.0.113.5", 6881)]


def test_dht_crawler_local_udp_simulation():
    target_hash = b"T" * 20
    expected_peer = ("198.51.100.77", 6889)
    peer_compact = PeerExchangeProtocol.encode_compact_peers([expected_peer])

    # Spin up local UDP responder acting as DHT node
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.bind(("127.0.0.1", 0))
    server_port = server_sock.getsockname()[1]
    server_sock.settimeout(2.0)

    def udp_responder():
        try:
            data, client_addr = server_sock.recvfrom(2048)
            req = BDecoder(data).decode()
            tx = req.get("t") or req.get(b"t")
            reply = {
                "t": tx,
                "y": "r",
                "r": {
                    "id": b"N" * 20,
                    "token": b"xyz",
                    "values": [peer_compact]
                }
            }
            server_sock.sendto(TorrentEncoder.encode(reply), client_addr)
        except Exception:
            pass
        finally:
            server_sock.close()

    t = threading.Thread(target=udp_responder, daemon=True)
    t.start()

    crawler = DHTCrawler(local_id=b"L" * 20)
    peers = crawler.discover_peers_sync(
        info_hash=target_hash,
        bootstrap_nodes=[("127.0.0.1", server_port)],
        max_rounds=1,
        timeout=1.5
    )

    assert expected_peer in peers