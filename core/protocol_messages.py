import struct

class TorrentMessage:
    """
    Handles all standard BitTorrent Protocol Messages.
    Implements BEP-3 Message formats.
    """

    # Message Type IDs
    CHOKED = b'\x00'
    UNCHOKED = b'\x01'
    INTERESTED = b'\x02'
    NOT_INTERESTED = b'\x03'
    HAVE = b'\x04'
    BITFIELD = b'\x05'
    REQUEST = b'\x06'
    PIECE = b'\x07'
    CANCEL = b'\x08'

    @staticmethod
    def create_request(piece_index: int, block_offset: int, block_length: int) -> bytes:
        """
        Creates a 'Request' message payload using Binary Struct packing.
        Format: [4-byte Length][1-byte ID][4-byte Index][4-byte Offset][4-byte Length]
        """
        # Pack the payload: Index, Offset, BlockLength
        payload = struct.pack('>III', piece_index, block_offset, block_length)
        
        # Total message size is ID (1) + Payload (12) = 13 bytes
        header_len = 1 + len(payload)
        
        # Prefix must be 4-byte Big Integer per BEP-3
        length_prefix = struct.pack('>I', header_len)
        
        # Combine: Length + ID + Data
        return length_prefix + TorrentMessage.REQUEST + payload

    @staticmethod
    def parse_piece(data: bytes):
        """
        Parses an incoming 'Piece' message.
        """
        try:
            if len(data) < 5: # Min length: 4 (prefix) + 1 (msg type)
                raise ValueError("Data too short")

            # Extract Message ID (byte index 4)
            msg_id = data[4]
            
            if msg_id != TorrentMessage.PIECE:
                return None

            # Parse payload starting from index 5
            # Structure: [4 bytes Index][4 bytes Offset][Remaining Data]
            idx = struct.unpack('>I', data[5:9])[0]
            offset = struct.unpack('>I', data[9:13])[0]
            
            block_data = data[13:]
            
            return idx, offset, block_data

        except Exception as e:
            print(f"[!] Error parsing piece: {e}")
            return None

    @staticmethod
    def create_cancel(piece_index: int, block_offset: int, block_length: int) -> bytes:
        """
        Cancels a previously sent request.
        """
        payload = struct.pack('>III', piece_index, block_offset, block_length)
        header_len = 1 + len(payload)
        length_prefix = struct.pack('>I', header_len)
        
        return length_prefix + TorrentMessage.CANCEL + payload