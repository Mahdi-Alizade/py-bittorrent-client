import math
from typing import Dict, List, Optional, Tuple
from colorama import Fore, Style, init

from core.protocol_messages import TorrentMessage
from core.reassemble import DownloadSession

init(autoreset=True)


class PieceManager:
    """
    Coordinates downloading, block tracking, SHA-1 verification, and disk writes.
    Handles variable piece sizes (especially the last truncated piece).
    """

    def __init__(self, filename: str, piece_length: int, num_pieces: int, total_length: Optional[int] = None):
        self.filename = filename
        self.piece_length = piece_length
        self.num_pieces = num_pieces
        self.total_length = total_length or (piece_length * num_pieces)
        self.block_size = 16 * 1024  # Standard 16 KB block size

        # Bitfield tracking
        self.peer_bitfield: List[bool] = [False] * num_pieces
        self.have_pieces: List[bool] = [False] * num_pieces

        # Active block storage: {(piece_idx, offset): block_data}
        self.received_blocks: Dict[Tuple[int, int], bytes] = {}

        # Disk Session writer
        self.writer = DownloadSession(filename, piece_length)
        self.writer.initialize_file()

    def get_piece_size(self, piece_idx: int) -> int:
        """Calculates actual size of a piece, accounting for the last truncated piece."""
        if piece_idx < self.num_pieces - 1:
            return self.piece_length
        remainder = self.total_length % self.piece_length
        return remainder if remainder > 0 else self.piece_length

    def get_blocks_for_piece(self, piece_idx: int) -> List[Tuple[int, int]]:
        """Returns list of (offset, length) tuples for all blocks in a piece."""
        size = self.get_piece_size(piece_idx)
        blocks = []
        offset = 0
        while offset < size:
            length = min(self.block_size, size - offset)
            blocks.append((offset, length))
            offset += length
        return blocks

    def handle_message(self, raw_data: bytes):
        """Dispatches incoming peer protocol messages."""
        if len(raw_data) < 5:
            return

        msg_id = raw_data[4]

        if msg_id == TorrentMessage.MSG_PIECE:
            parsed = TorrentMessage.parse_piece(raw_data)
            if parsed:
                idx, offset, data = parsed
                self._store_block(idx, offset, data)

        elif msg_id == TorrentMessage.MSG_HAVE:
            piece_idx = TorrentMessage.parse_have(raw_data)
            if piece_idx is not None and piece_idx < self.num_pieces:
                self.peer_bitfield[piece_idx] = True
                print(f"{Fore.CYAN}[<-] Peer HAS Piece #{piece_idx}{Style.RESET_ALL}")

    def _store_block(self, piece_idx: int, offset: int, block_data: bytes):
        """Stores received block and triggers integrity verification when all blocks arrive."""
        self.received_blocks[(piece_idx, offset)] = block_data
        self.writer.receive_block(piece_idx, offset, block_data)
        self._verify_piece_integrity(piece_idx)

    def _verify_piece_integrity(self, piece_idx: int):
        """Verifies all blocks for piece_idx exist and commits to disk session."""
        expected_blocks = self.get_blocks_for_piece(piece_idx)
        received_offsets = {off for (p, off) in self.received_blocks.keys() if p == piece_idx}
        expected_offsets = {off for (off, _) in expected_blocks}

        if expected_offsets.issubset(received_offsets):
            print(f"{Fore.MAGENTA}[*] Full piece #{piece_idx} assembled. Writing to disk...{Style.RESET_ALL}")
            self.writer.verify_and_save_piece(piece_idx)
            self.have_pieces[piece_idx] = True

            # Clean stored blocks for this piece
            keys_to_delete = [k for k in self.received_blocks if k[0] == piece_idx]
            for k in keys_to_delete:
                del self.received_blocks[k]

            print(f"{Fore.GREEN}[+] SUCCESS: Piece #{piece_idx} saved successfully.{Style.RESET_ALL}")

    def get_next_request(self, piece_idx: int) -> Optional[bytes]:
        """Finds the next unreceived block in piece_idx and constructs a BEP-3 Request packet."""
        if self.have_pieces[piece_idx]:
            return None

        blocks = self.get_blocks_for_piece(piece_idx)
        for offset, length in blocks:
            if (piece_idx, offset) not in self.received_blocks:
                return TorrentMessage.create_request(piece_idx, offset, length)
        return None

    def status_report(self) -> str:
        """Returns completed pieces count and percentage."""
        total_downloaded = sum(1 for p in self.have_pieces if p)
        pct = (total_downloaded / self.num_pieces * 100) if self.num_pieces > 0 else 0.0
        return f"{total_downloaded}/{self.num_pieces} ({pct:.1f}%)"