import os
import socket
import struct
import urllib.parse
from typing import Dict, List, Tuple

from core.pex_protocol import PeerExchangeProtocol


class UDPTrackerClient:
    """
    Implements BEP-0015 (UDP Tracker Protocol for BitTorrent).
    Handles binary 16-byte connection handshakes and 98-byte announce datagrams.
    """

    MAGIC_CONNECTION_ID = 0x41727101980
    ACTION_CONNECT = 0
    ACTION_ANNOUNCE = 1
    ACTION_SCRAPE = 2
    ACTION_ERROR = 3

    def __init__(self, info_hash: bytes, peer_id: bytes, timeout: float = 4.0):
        if len(info_hash) != 20 or len(peer_id) != 20:
            raise ValueError("info_hash and peer_id must both be 20 bytes")
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.timeout = timeout

    @staticmethod
    def parse_udp_url(tracker_url: str) -> Tuple[str, int]:
        parsed = urllib.parse.urlparse(tracker_url)
        if parsed.scheme.lower() != "udp":
            raise ValueError(f"Unsupported scheme for UDPTrackerClient: {parsed.scheme}")
        host = parsed.hostname
        if not host:
            raise ValueError("Missing hostname in UDP tracker URL")
        port = parsed.port or 80
        return host, int(port)

    @classmethod
    def build_connect_request(cls, transaction_id: int) -> bytes:
        """Builds 16-byte BEP-0015 connect request packet."""
        return struct.pack(">QII", cls.MAGIC_CONNECTION_ID, cls.ACTION_CONNECT, transaction_id)

    @classmethod
    def parse_connect_response(cls, response_bytes: bytes, expected_tx_id: int) -> int:
        if len(response_bytes) < 16:
            raise ValueError("UDP connect response too short (< 16 bytes)")
        action, tx_id, connection_id = struct.unpack(">IIQ", response_bytes[:16])
        if tx_id != expected_tx_id:
            raise ValueError("Transaction ID mismatch in UDP connect response")
        if action == cls.ACTION_ERROR:
            err_msg = response_bytes[8:].decode("utf-8", errors="replace")
            raise RuntimeError(f"UDP tracker error: {err_msg}")
        if action != cls.ACTION_CONNECT:
            raise ValueError(f"Unexpected action {action} in connect response")
        return connection_id

    def build_announce_request(
        self,
        connection_id: int,
        transaction_id: int,
        downloaded: int = 0,
        left: int = 0,
        uploaded: int = 0,
        event: int = 0,
        port: int = 6881,
        num_want: int = 50
    ) -> bytes:
        """Builds 98-byte BEP-0015 announce request packet."""
        key = struct.unpack(">I", os.urandom(4))[0]
        ip_address = 0  # 0 instructs tracker to use sender's source IP

        header = struct.pack(
            ">QII20s20sQQQIIIiH",
            connection_id,
            self.ACTION_ANNOUNCE,
            transaction_id,
            self.info_hash,
            self.peer_id,
            downloaded,
            left,
            uploaded,
            event,
            ip_address,
            key,
            num_want,
            port
        )
        return header

    @classmethod
    def parse_announce_response(cls, response_bytes: bytes, expected_tx_id: int) -> Dict:
        if len(response_bytes) < 20:
            raise ValueError("UDP announce response too short (< 20 bytes)")

        action, tx_id, interval, leechers, seeders = struct.unpack(">IIIII", response_bytes[:20])
        if tx_id != expected_tx_id:
            raise ValueError("Transaction ID mismatch in UDP announce response")
        if action == cls.ACTION_ERROR:
            err_msg = response_bytes[8:].decode("utf-8", errors="replace")
            raise RuntimeError(f"UDP tracker announce error: {err_msg}")
        if action != cls.ACTION_ANNOUNCE:
            raise ValueError(f"Unexpected action {action} in announce response")

        compact_peers_blob = response_bytes[20:]
        peers_list: List[Tuple[str, int]] = PeerExchangeProtocol.decode_compact_peers(compact_peers_blob)

        return {
            "interval": interval,
            "leechers": leechers,
            "seeders": seeders,
            "peers": peers_list
        }

    def announce(
        self,
        tracker_url: str,
        port: int = 6881,
        uploaded: int = 0,
        downloaded: int = 0,
        left: int = 0,
        event: int = 0
    ) -> Dict:
        """
        Executes full BEP-0015 two-step UDP announce (Connect -> Announce).
        """
        try:
            host, tracker_port = self.parse_udp_url(tracker_url)
            resolved_ip = socket.gethostbyname(host)
        except Exception as err:
            return {"peers": [], "error": str(err)}

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)

        try:
            # Step 1: Connect handshake
            connect_tx = struct.unpack(">I", os.urandom(4))[0]
            connect_pkt = self.build_connect_request(connect_tx)
            sock.sendto(connect_pkt, (resolved_ip, tracker_port))

            conn_resp, _ = sock.recvfrom(2048)
            connection_id = self.parse_connect_response(conn_resp, connect_tx)

            # Step 2: Announce request
            announce_tx = struct.unpack(">I", os.urandom(4))[0]
            announce_pkt = self.build_announce_request(
                connection_id=connection_id,
                transaction_id=announce_tx,
                downloaded=downloaded,
                left=left,
                uploaded=uploaded,
                event=event,
                port=port
            )
            sock.sendto(announce_pkt, (resolved_ip, tracker_port))

            ann_resp, _ = sock.recvfrom(4096)
            return self.parse_announce_response(ann_resp, announce_tx)
        except Exception as err:
            return {"peers": [], "error": str(err)}
        finally:
            sock.close()