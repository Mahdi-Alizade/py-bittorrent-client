import socket
import struct
from typing import Dict, List, Optional, Tuple
from core.parser import BDecoder, TorrentEncoder


class PeerExchangeProtocol:
    """
    Implements BEP-0011 (Peer Exchange - ut_pex) over BEP-0010 Extension Protocol.
    Allows peers to directly share newly discovered and dropped peer addresses
    without querying central trackers.
    """

    EXTENSION_NAME = "ut_pex"
    LOCAL_PEX_ID = 2
    MSG_EXTENDED = 20

    @staticmethod
    def encode_compact_peers(peers: List[Tuple[str, int]]) -> bytes:
        buffer = bytearray()
        for ip_str, port_num in peers:
            try:
                packed_ip = socket.inet_aton(ip_str)
                packed_port = struct.pack(">H", int(port_num))
                buffer.extend(packed_ip)
                buffer.extend(packed_port)
            except Exception:
                continue
        return bytes(buffer)

    @staticmethod
    def decode_compact_peers(compact_bytes: bytes) -> List[Tuple[str, int]]:
        decoded_list: List[Tuple[str, int]] = []
        if not compact_bytes or len(compact_bytes) % 6 != 0:
            return decoded_list

        total_len = len(compact_bytes)
        offset = 0
        while offset < total_len:
            chunk = compact_bytes[offset:offset + 6]
            ip_raw = chunk[:4]
            port_raw = chunk[4:6]

            ip_str = socket.inet_ntoa(ip_raw)
            port_num = struct.unpack(">H", port_raw)[0]
            decoded_list.append((ip_str, port_num))
            offset += 6

        return decoded_list

    @classmethod
    def create_pex_message(
        cls,
        peer_ut_pex_id: int,
        added_peers: List[Tuple[str, int]],
        dropped_peers: Optional[List[Tuple[str, int]]] = None
    ) -> bytes:
        added_compact = cls.encode_compact_peers(added_peers)
        added_flags = b"\x00" * len(added_peers)

        pex_dict: Dict[str, bytes] = {
            "added": added_compact,
            "added.f": added_flags
        }

        if dropped_peers:
            pex_dict["dropped"] = cls.encode_compact_peers(dropped_peers)

        bencoded_body = TorrentEncoder.encode(pex_dict)
        total_length = 2 + len(bencoded_body)
        header = struct.pack(">IBB", total_length, cls.MSG_EXTENDED, peer_ut_pex_id)
        return header + bencoded_body

    @classmethod
    def parse_pex_message(cls, payload_bytes: bytes) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]]]:
        if len(payload_bytes) < 2:
            return [], []

        msg_id = payload_bytes[0]
        ext_id = payload_bytes[1]

        if msg_id != cls.MSG_EXTENDED or ext_id != cls.LOCAL_PEX_ID:
            return [], []

        raw_dict_bytes = payload_bytes[2:]
        try:
            decoded = BDecoder(raw_dict_bytes).decode()
            if not isinstance(decoded, dict):
                return [], []

            added_raw = decoded.get(b"added") or decoded.get("added") or b""
            if isinstance(added_raw, str):
                added_raw = added_raw.encode("latin-1")

            dropped_raw = decoded.get(b"dropped") or decoded.get("dropped") or b""
            if isinstance(dropped_raw, str):
                dropped_raw = dropped_raw.encode("latin-1")

            added_list = cls.decode_compact_peers(added_raw)
            dropped_list = cls.decode_compact_peers(dropped_raw)
            return added_list, dropped_list
        except Exception:
            return [], []