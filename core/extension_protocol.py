import hashlib
import math
import struct
from typing import Optional, Tuple
from core.parser import BDecoder, TorrentEncoder


class ExtensionProtocol:
    """
    Implements BEP-0010 (Extension Protocol), BEP-0009 (ut_metadata),
    and BEP-0011 (ut_pex) handshake negotiation.
    """

    MSG_EXTENDED = 20
    HANDSHAKE_EXT_ID = 0
    LOCAL_UT_METADATA_ID = 1
    LOCAL_UT_PEX_ID = 2

    # ut_metadata message types (BEP-0009)
    META_REQUEST = 0
    META_DATA = 1
    META_REJECT = 2

    METADATA_PIECE_SIZE = 16384

    @staticmethod
    def build_reserved_bytes() -> bytes:
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
        Creates BEP-0010 Extended Handshake advertising both ut_metadata and ut_pex.
        """
        handshake_dict = {
            "m": {
                "ut_metadata": cls.LOCAL_UT_METADATA_ID,
                "ut_pex": cls.LOCAL_UT_PEX_ID
            }
        }
        encoded_payload = TorrentEncoder.encode(handshake_dict)
        total_len = 2 + len(encoded_payload)
        header = struct.pack(">IBB", total_len, cls.MSG_EXTENDED, cls.HANDSHAKE_EXT_ID)
        return header + encoded_payload

    @classmethod
    def parse_extension_handshake(cls, payload_bytes: bytes) -> Tuple[Optional[int], Optional[int]]:
        """
        Parses peer's extended handshake payload.
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
    def parse_extended_capabilities(cls, payload_bytes: bytes) -> dict:
        """
        Extracts full extension dictionary capabilities (ut_metadata, ut_pex, metadata_size).
        """
        result = {
            "ut_metadata": None,
            "ut_pex": None,
            "metadata_size": None
        }
        if len(payload_bytes) < 2:
            return result

        if payload_bytes[0] != cls.MSG_EXTENDED or payload_bytes[1] != cls.HANDSHAKE_EXT_ID:
            return result

        try:
            decoded = BDecoder(payload_bytes[2:]).decode()
            if not isinstance(decoded, dict):
                return result

            m_dict = decoded.get(b"m") or decoded.get("m") or {}
            meta_id = m_dict.get(b"ut_metadata") or m_dict.get("ut_metadata")
            pex_id = m_dict.get(b"ut_pex") or m_dict.get("ut_pex")
            meta_size = decoded.get(b"metadata_size") or decoded.get("metadata_size")

            if meta_id is not None:
                result["ut_metadata"] = int(meta_id)
            if pex_id is not None:
                result["ut_pex"] = int(pex_id)
            if meta_size is not None:
                result["metadata_size"] = int(meta_size)
        except Exception:
            pass

        return result

    @classmethod
    def create_metadata_request(cls, peer_ut_metadata_id: int, piece_index: int) -> bytes:
        req_dict = {
            "msg_type": cls.META_REQUEST,
            "piece": piece_index
        }
        encoded_dict = TorrentEncoder.encode(req_dict)
        total_len = 2 + len(encoded_dict)
        header = struct.pack(">IBB", total_len, cls.MSG_EXTENDED, peer_ut_metadata_id)
        return header + encoded_dict

    @classmethod
    def _find_bencoded_dict_end(cls, data: bytes) -> int:
        if not data or data[0:1] != b"d":
            return -1

        idx = 0
        length = len(data)
        depth = 0

        while idx < length:
            token = data[idx:idx + 1]
            if token in (b"d", b"l"):
                depth += 1
                idx += 1
            elif token == b"i":
                end_int = data.find(b"e", idx + 1)
                if end_int == -1:
                    return -1
                idx = end_int + 1
            elif token == b"e":
                depth -= 1
                idx += 1
                if depth == 0:
                    return idx
            elif token.isdigit():
                colon_pos = data.find(b":", idx)
                if colon_pos == -1:
                    return -1
                str_len = int(data[idx:colon_pos])
                idx = colon_pos + 1 + str_len
            else:
                return -1

        return -1

    @classmethod
    def parse_metadata_message(cls, payload_bytes: bytes) -> Optional[Tuple[int, int, bytes]]:
        if len(payload_bytes) < 2:
            return None

        msg_id = payload_bytes[0]
        ext_id = payload_bytes[1]

        if msg_id != cls.MSG_EXTENDED or ext_id != cls.LOCAL_UT_METADATA_ID:
            return None

        body = payload_bytes[2:]
        dict_end = cls._find_bencoded_dict_end(body)
        if dict_end == -1:
            return None

        header_bytes = body[:dict_end]
        raw_chunk = body[dict_end:]

        try:
            header_dict = BDecoder(header_bytes).decode()
            if not isinstance(header_dict, dict):
                return None

            if b"msg_type" in header_dict:
                msg_type = int(header_dict[b"msg_type"])
            elif "msg_type" in header_dict:
                msg_type = int(header_dict["msg_type"])
            else:
                msg_type = -1

            if b"piece" in header_dict:
                piece_idx = int(header_dict[b"piece"])
            elif "piece" in header_dict:
                piece_idx = int(header_dict["piece"])
            else:
                piece_idx = -1

            return msg_type, piece_idx, raw_chunk
        except Exception:
            return None


class MetadataAssembler:
    def __init__(self, expected_info_hash: bytes, metadata_size: int):
        self.expected_info_hash = expected_info_hash
        self.metadata_size = metadata_size
        self.piece_size = ExtensionProtocol.METADATA_PIECE_SIZE
        self.num_pieces = max(1, math.ceil(metadata_size / self.piece_size))
        self.pieces: dict[int, bytes] = {}

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