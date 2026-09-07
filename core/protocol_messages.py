import struct
from typing import Optional, Tuple


class TorrentMessage:
    """
    Handles all standard BitTorrent Protocol Messages (BEP-3).
    Message Framing: <4-byte length prefix><1-byte message ID><optional payload>
    Keep-alive message has length 0 and no message ID.
    """

    MSG_CHOKE = 0
    MSG_UNCHOKE = 1
    MSG_INTERESTED = 2
    MSG_NOT_INTERESTED = 3
    MSG_HAVE = 4
    MSG_BITFIELD = 5
    MSG_REQUEST = 6
    MSG_PIECE = 7
    MSG_CANCEL = 8

    # Alias for backwards compatibility
    MSG_CHOKED = MSG_CHOKE
    MSG_UNCHOKED = MSG_UNCHOKE

    @staticmethod
    def create_keep_alive() -> bytes:
        """Keep-alive is a 4-byte zero length with no message ID."""
        return struct.pack('>I', 0)

    @staticmethod
    def create_choke() -> bytes:
        return struct.pack('>IB', 1, TorrentMessage.MSG_CHOKE)

    @staticmethod
    def create_unchoke() -> bytes:
        return struct.pack('>IB', 1, TorrentMessage.MSG_UNCHOKE)

    @staticmethod
    def create_interested() -> bytes:
        return struct.pack('>IB', 1, TorrentMessage.MSG_INTERESTED)

    @staticmethod
    def create_not_interested() -> bytes:
        return struct.pack('>IB', 1, TorrentMessage.MSG_NOT_INTERESTED)

    @staticmethod
    def create_have(piece_index: int) -> bytes:
        """Format: [4-byte len: 5][1-byte ID: 4][4-byte piece index]"""
        return struct.pack('>IBI', 5, TorrentMessage.MSG_HAVE, piece_index)

    @staticmethod
    def create_bitfield(bitfield_bytes: bytes) -> bytes:
        """Format: [4-byte len: 1 + len(bitfield)][1-byte ID: 5][bitfield payload]"""
        length = 1 + len(bitfield_bytes)
        return struct.pack('>IB', length, TorrentMessage.MSG_BITFIELD) + bitfield_bytes

    @staticmethod
    def create_request(piece_index: int, block_offset: int, block_length: int) -> bytes:
        """
        Creates a 'Request' message payload.
        Format: [4-byte Len: 13][1-byte ID: 6][4-byte Index][4-byte Offset][4-byte Length]
        """
        payload = struct.pack('>III', piece_index, block_offset, block_length)
        length_prefix = struct.pack('>I', 1 + len(payload))
        return length_prefix + bytes([TorrentMessage.MSG_REQUEST]) + payload

    @staticmethod
    def create_cancel(piece_index: int, block_offset: int, block_length: int) -> bytes:
        """
        Cancels a previously sent block request.
        Format: [4-byte Len: 13][1-byte ID: 8][4-byte Index][4-byte Offset][4-byte Length]
        """
        payload = struct.pack('>III', piece_index, block_offset, block_length)
        length_prefix = struct.pack('>I', 1 + len(payload))
        return length_prefix + bytes([TorrentMessage.MSG_CANCEL]) + payload

    @staticmethod
    def parse_have(data: bytes) -> Optional[int]:
        """Parses a 'Have' message payload (expects 9 bytes total)."""
        if len(data) < 9 or data[4] != TorrentMessage.MSG_HAVE:
            return None
        return struct.unpack('>I', data[5:9])[0]

    @staticmethod
    def parse_piece(data: bytes) -> Optional[Tuple[int, int, bytes]]:
        """
        Parses an incoming 'Piece' message.
        Structure: [4 bytes Length][1 byte ID: 7][4 bytes Index][4 bytes Offset][Block Data]
        """
        try:
            if len(data) < 13:
                return None

            msg_id = data[4]
            if msg_id != TorrentMessage.MSG_PIECE:
                return None

            idx = struct.unpack('>I', data[5:9])[0]
            offset = struct.unpack('>I', data[9:13])[0]
            block_data = data[13:]

            return idx, offset, block_data
        except Exception:
            return None