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
        Creates a 'Request' message payload.
        Client asks peer for a specific block of a piece.
        
        Args:
            piece_index: ID of the piece (integer)
            block_offset: Start position within the piece (integer)
            block_length: Number of bytes requested (must be 16KB usually)
            
        Returns:
            Byte array formatted exactly for BitTorrent transport
        """
        # Format: [Length Prefix][ID][Index][Offset][Length]
        # Using '>i' ensures network byte order (Big Endian) which is mandatory in BitTorrent
        
        msg_type = TorrentMessage.REQUEST
        header_len = 1 + 12  # 1 byte ID + 12 bytes for 3 Integers
        
        # Pack the payload (12 bytes total for 3 integers)
        payload = struct.pack('>III', piece_index, block_offset, block_length)
        
        # Combine Length Prefix + ID + Payload
        return f'{header_len}'.encode().encode() + msg_type + payload

    @staticmethod
    def parse_piece(data: bytes):
        """
        Parses an incoming 'Piece' message.
        
        Args:
            data: Raw bytes received from socket
            
        Returns:
            Tuple (piece_index, block_offset, block_data) or None
        """
        try:
            # First 4 bytes are the Length Prefix of the payload
            if len(data) < 4:
                raise ValueError("Data too short")

            payload_length = struct.unpack('>I', data[:4])[0]
            
            # Next 1 byte is Message ID (7 means PIECE)
            msg_id = data[4]
            if msg_id != TorrentMessage.PIECE:
                return None

            # Remaining bytes form the piece structure: [Index][Offset][Block]
            if len(data) < 4 + 1 + 8:
                return None

            # Skip length prefix and msg id, start reading from Index
            rest_data = data[5:] 
            
            # First 4 bytes: Piece Index
            piece_index = struct.unpack('>I', rest_data[:4])[0]
            
            # Next 4 bytes: Block Offset
            block_offset = struct.unpack('>I', rest_data[4:8])[0]
            
            # The rest: Actual Block Data
            block_data = rest_data[8:]
            
            return piece_index, block_offset, block_data

        except Exception as e:
            print(f"[!] Error parsing piece: {e}")
            return None

    @staticmethod
    def create_cancel(piece_index: int, block_offset: int, block_length: int) -> bytes:
        """
        Cancels a previously sent request.
        Used for flow control or switching priorities.
        """
        msg_type = TorrentMessage.CANCEL
        header_len = 1 + 12 
        
        payload = struct.pack('>III', piece_index, block_offset, block_length)
        return f'{header_len}'.encode().encode() + msg_type + payload