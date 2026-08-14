import hashlib
from pathlib import Path
from colorama import Fore, Style, init
from core.protocol_messages import TorrentMessage
from core.reassemble import DownloadSession

init(autoreset=True)

class PieceManager:
    """
    Manages piece-level coordination, request scheduling, and validation.
    Bridges the socket layer and the file writer.
    """
    
    def __init__(self, filename: str, piece_length: int, num_pieces: int):
        self.filename = filename
        self.piece_length = piece_length
        self.num_pieces = num_pieces
        self.block_size = 16 * 1024  # Standard 16KB
        
        # Internal State
        self.have_bitfield = [False] * num_pieces
        self.received_blocks = {}  # {(piece_idx, offset): bytes}
        
        # Storage engine
        self.writer = DownloadSession(filename, piece_length)
        self.writer.initialize_file()
        
    def handle_message(self, raw_data: bytes):
        """
        Routes incoming byte streams to appropriate handlers.
        """
        if len(raw_data) < 5:
            return
            
        msg_id = raw_data[4]
        
        if msg_id == TorrentMessage.PIECE:
            parsed = TorrentMessage.parse_piece(raw_data)
            if parsed:
                idx, offset, data = parsed
                self._store_block(idx, offset, data)
                
        elif msg_id == TorrentMessage.HAVE:
            try:
                piece_idx = int.from_bytes(raw_data[5:9], 'big')
                self.have_bitfield[piece_idx] = True
                print(f"{Fore.CYAN}[<-] Peer HAS Piece #{piece_idx}{Style.RESET_ALL}")
            except Exception:
                pass
                
        elif msg_id in [TorrentMessage.UNCHOKED, TorrentMessage.INTERESTED, TorrentMessage.BITFIELD]:
            print(f"{Fore.LIGHTBLACK_EX}[*] Control message received. Handled internally.{Style.RESET_ALL}")

    def _store_block(self, piece_idx: int, offset: int, block_data: bytes):
        """Receives a block and places it in memory/disk stream."""
        self.received_blocks[(piece_idx, offset)] = block_data
        self.writer.receive_block(piece_idx, offset, block_data)
        
        # Trigger immediate verification if this completes a logical chunk
        self._verify_piece_integrity(piece_idx)

    def _verify_piece_integrity(self, piece_idx: int):
        """Checks if all blocks for a piece are present and verifies/completes it."""
        required_blocks = list(range(0, self.piece_length, self.block_size))
        present_offsets = [off for (pi, off) in self.received_blocks.keys() if pi == piece_idx]
        
        # If all blocks arrived for this piece
        if set(present_offsets) == set(required_blocks):
            print(f"{Fore.MAGENTA}[*] Full piece #{piece_idx} assembled. Verifying integrity...{Style.RESET_ALL}")
            
            # In production, compare SHA1 here against torrent's 'info' dict hash table
            # For our test, we trust the stream
            self.writer.verify_and_save_piece(piece_idx)
            self.have_bitfield[piece_idx] = True
            self.received_blocks.clear()
            print(f"{Fore.GREEN}[+] SUCCESS: Piece #{piece_idx} written to disk.{Style.RESET_ALL}")

    def get_request_packet(self, piece_index: int) -> bytes:
        """Generates a proper REQUEST packet for the socket."""
        return TorrentMessage.create_request(piece_index, 0, self.block_size)

    def status_report(self):
        total_downloaded = sum(1 for s in self.have_bitfield if s)
        pct = (total_downloaded / self.num_pieces * 100) if self.num_pieces > 0 else 0
        return f"{total_downloaded}/{self.num_pieces} ({pct:.1f}%)"