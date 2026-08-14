import sys

class NetworkProtocol:
    """
    Handles BitTorrent Protocol Messages (Handshake, Keepalive, etc.)
    """
    
    BT_PROTOCOL_STRING = b'bittorrent protocol'
    
    @staticmethod
    def build_handshake(info_hash: str, peer_id: str) -> bytes:
        """
        Constructs the mandatory BitTorrent Handshake.
        Format: [pstrlen][pstr][reserved][info_hash][peer_id]
        
        Args:
            info_hash: Hex string of the file's SHA1 hash
            peer_id: Unique identifier for this client
            
        Returns:
            Byte array ready to be sent via Socket
        """
        # 1. Prefix Length (Length of 'bittorrent protocol')
        pstrlen = len(NetworkProtocol.BT_PROTOCOL_STRING)
        
        # 2. Reserved Bytes (Usually 8 zeros for now)
        reserved = b'\x00\x00\x00\x00\x00\x00\x00\x00'
        
        # Construct parts
        header = pstrlen.to_bytes(1, byteorder='big', signed=False) # Simple byte count
        
        # Assemble the full handshaking packet
        handshake_data = bytearray()
        handshake_data.append(len(NetworkProtocol.BT_PROTOCOL_STRING))
        handshake_data.extend(NetworkProtocol.BT_PROTOCOL_STRING)
        handshake_data.extend(reserved)
        handshake_data.extend(bytes.fromhex(info_hash)) # Decode hex back to binary
        handshake_data.extend(peer_id.encode('latin-1')) # Peer ID max 20 chars
        
        return bytes(handshake_data)

    @staticmethod
    def parse_handshake(data: bytes) -> bool:
        """
        Checks if a received handshake is valid.
        """
        try:
            pstrlen = data[0]
            pstr = data[1:pstrlen+1]
            
            if pstr == NetworkProtocol.BT_PROTOCOL_STRING:
                return True
            return False
        except IndexError:
            return False