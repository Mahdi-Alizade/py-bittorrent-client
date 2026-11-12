import hashlib
import math
import struct
from typing import Dict, Optional, Tuple
from core.parser import BDecoder, TorrentEncoder


class ExtensionProtocol:
    """
    Implements BEP-0010 (Extension Protocol) and BEP-0009 (ut_metadata)
    to fetch the torrent 'info' dictionary directly from peers via magnet links.
    """

    MSG_EXTENDED = 20
    HANDSHAKE_EXT_ID = 0
    LOCAL_UT_METADATA_ID = 1

    # ut_metadata message types (BEP-0009)
    META_REQUEST = 0
    META_DATA = 1
    META_REJECT = 2

    METADATA_PIECE_SIZE = 16384

    @staticmethod
    def build_reserved_bytes() -> bytes:
        """
        Builds 8-byte handshake reserved field with bit 20 set (byte[5] |= 0x10)
        indicating support for BEP-0010 Extension Protocol.
        """
        reserved = bytearray(8)
        reserved[5] |= 0x10
        return bytes(reserved)

    @staticmethod
    def peer_supports_extensions(reserved_bytes: bytes) -> bool:
        if len(reserved_bytes) < 8:
            return False
        return (reserved_bytes[5] & 0x10) != 0

    @classmethod
    def create_extension_handshake(cls) -> bytes:
        """
        Creates BEP-0010 Extended Handshake payload advertising ut_metadata support.
        Format: <len><id=20><ext_id=0><bencoded_dict>
        """
        handshake_dict = {
            "m": {
                "ut_metadata": cls.LOCAL_UT_METADATA_ID
            }
        }
        encoded_payload = TorrentEncoder.encode(handshake_dict)
        total_len = 2 + len(encoded_payload)
        header = struct.pack(">IBB", total_len, cls.MSG_EXTENDED, cls.HANDSHAKE_EXT_ID)
        return header + encoded_payload

    @classmethod
    def parse_extension_handshake(cls, payload_bytes: bytes) -> Tuple[Optional[int], Optional[int]]:
        """
        Parses peer's extended handshake payload (excluding 4-byte length prefix).
        Returns (peer_ut_metadata_id, metadata_size).
        """
        if len(payload_bytes) < 2:
            return None, None

        msg_id = payload_bytes[0]
        ext_id = payload_bytes[1]

        if msg_id != cls.MSG_EXTENDED or ext_id != cls.HANDSHAKE_EXT_ID:
            return None, None

        bencoded_body = payload_bytes[2:]
        try:
            decoded = BDecoder(bencoded_body).decode()
            if not isinstance(decoded, dict):
                return None, None

            m_dict = decoded.get(b"m") or decoded.get("m") or {}
            peer_meta_id = m_dict.get(b"ut_metadata") or m_dict.get("ut_metadata")
            meta_size = decoded.get(b"metadata_size") or decoded.get("metadata_size")

            if peer_meta_id is not None:
                peer_meta_id = int(peer_meta_id)
            if meta_size is not None:
                meta_size = int(meta_size)

            return peer_meta_id, meta_size
        except Exception:
            return None, None

    @classmethod
    def create_metadata_request(cls, peer_ut_metadata_id: int, piece_index: int) -> bytes:
        """
        Builds a BEP-0009 metadata piece request message.
        """
        req_dict = {
            "msg_type": cls.META_REQUEST,
            "piece": piece_index
        }
        encoded_dict = TorrentEncoder.encode(req_dict)
        total_len = 2 + len(encoded_dict)
        header = struct.pack(">IBB", total_len, cls.MSG_EXTENDED, peer_ut_metadata_id)
        return header + encoded_dict

    @classmethod
    def parse_metadata_message(cls, payload_bytes: bytes) -> Optional[Tuple[int, int, bytes]]:
        """
        Parses an incoming ut_metadata message (excluding 4-byte length prefix).
        Returns (msg_type, piece_index, raw_metadata_chunk).
        """
        if len(payload_bytes) < 2:
            return None

        msg_id = payload_bytes[0]
        ext_id = payload_bytes[1]

        if msg_id != cls.MSG_EXTENDED or ext_id != cls.LOCAL_UT_METADATA_ID:
            return None

        body = payload_bytes[2:]
        try:
            decoder = BDecoder(body)
            header_dict = decoder.decode()
            if not isinstance(header_dict, dict):
                return None

            msg_type = int(header_dict.get(b"msg_type") if b"msg_type" in header_dict else header_dict.get("msg_type", -1))
            piece_idx = int(header_dict.get(b"piece") if b"piece" in header_dict else header_dict.get("piece", -1))

            # Remaining bytes after the bencoded dictionary represent the raw metadata piece
            raw_chunk = body[decoder.index:]
            return msg_type, piece_idx, raw_chunk
        except Exception:
            return None


class MetadataAssembler:
    """
    Collects 16KB metadata pieces from peers and verifies the assembled 'info'
    dictionary against the target magnet info-hash.
    """

    def __init__(self, expected_info_hash: bytes, metadata_size: int):
        self.expected_info_hash = expected_info_hash
        self.metadata_size = metadata_size
        self.piece_size = ExtensionProtocol.METADATA_PIECE_SIZE
        self.num_pieces = max(1, math.ceil(metadata_size / self.piece_size))
        self.pieces: Dict[int, bytes] = {}

    def add_piece(self, piece_index: int, chunk: bytes):
        if 0 <= piece_index < self.num_pieces:
            self.pieces[piece_index] = chunk

    def is_complete(self) -> bool:
        return len(self.pieces) == self.num_pieces

    def get_missing_pieces(self) -> list:
        missing = []
        for idx in range(self.num_pieces):
            if idx not in self.pieces:
                missing.append(idx)
        return missing

    def assemble_and_verify(self) -> Optional[dict]:
        if not self.is_complete():
            return None

        ordered_buffer = bytearray()
        for idx in range(self.num_pieces):
            ordered_buffer.extend(self.pieces[idx])

        raw_info_bytes = bytes(ordered_buffer)
        calculated_hash = hashlib.sha1(raw_info_bytes).digest()

        if calculated_hash != self.expected_info_hash:
            return None

        decoded_info = BDecoder(raw_info_bytes).decode()
        if isinstance(decoded_info, dict):
            return decoded_info
        return None