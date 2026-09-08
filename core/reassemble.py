import hashlib
import os
from pathlib import Path
from typing import Dict, List, Optional
from colorama import Fore, Style, init

init(autoreset=True)


class DownloadSession:
    """
    Manages piece verification via SHA-1 and random-access persistent writes.
    Uses seek-based I/O to guarantee data is placed at correct offsets regardless of arrival order.
    """

    def __init__(
        self,
        filename: str,
        piece_length: int,
        total_length: Optional[int] = None,
        piece_hashes: Optional[List[bytes]] = None,
        output_dir: str = "downloads"
    ):
        self.filename = filename
        self.piece_length = piece_length
        self.total_length = total_length or piece_length
        self.piece_hashes = piece_hashes or []
        self.output_dir = Path(output_dir)
        self.final_path = self.output_dir / self.filename

        # Buffer: {piece_idx: bytearray}
        self.pending_blocks: Dict[int, bytearray] = {}
        self.completed_pieces: List[int] = []
        self.total_data_received = 0

    def initialize_file(self) -> bool:
        """Pre-allocates the file space on disk matching total expected size."""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            if not self.final_path.exists() or self.final_path.stat().st_size != self.total_length:
                print(f"{Fore.CYAN}[*] Pre-allocating {self.final_path.name} ({self.total_length} bytes)...{Style.RESET_ALL}")
                with open(self.final_path, "wb") as f:
                    if self.total_length > 0:
                        f.seek(self.total_length - 1)
                        f.write(b"\x00")
            return True
        except Exception as e:
            print(f"{Fore.RED}[!] Failed to initialize file: {e}{Style.RESET_ALL}")
            return False

    def get_piece_size(self, piece_index: int) -> int:
        start_offset = piece_index * self.piece_length
        return min(self.piece_length, max(0, self.total_length - start_offset))

    def receive_block(self, piece_index: int, block_offset: int, block_data: bytes):
        """Places block into memory buffer for piece_index."""
        if piece_index not in self.pending_blocks:
            expected_size = self.get_piece_size(piece_index)
            self.pending_blocks[piece_index] = bytearray(expected_size)

        buffer = self.pending_blocks[piece_index]
        end_pos = min(block_offset + len(block_data), len(buffer))
        buffer[block_offset:end_pos] = block_data[:end_pos - block_offset]
        self.total_data_received += len(block_data)

    def verify_and_save_piece(self, piece_index: int) -> bool:
        """
        Validates the assembled piece using SHA-1 (if hashes are provided)
        and writes it at (piece_index * piece_length) on disk.
        """
        if piece_index not in self.pending_blocks:
            return False

        piece_bytes = bytes(self.pending_blocks[piece_index])

        # Verify SHA-1 hash if available
        if piece_index < len(self.piece_hashes):
            expected_hash = self.piece_hashes[piece_index]
            calculated_hash = hashlib.sha1(piece_bytes).digest()
            if calculated_hash != expected_hash:
                print(f"{Fore.RED}[-] SHA-1 Mismatch for piece #{piece_index}! Discarding.{Style.RESET_ALL}")
                del self.pending_blocks[piece_index]
                return False

        # Seek-based write to correct file offset
        target_offset = piece_index * self.piece_length
        try:
            with open(self.final_path, "r+b") as f:
                f.seek(target_offset)
                f.write(piece_bytes)

            del self.pending_blocks[piece_index]
            self.completed_pieces.append(piece_index)
            return True
        except IOError as e:
            print(f"{Fore.RED}[-] Write error on piece #{piece_index}: {e}{Style.RESET_ALL}")
            return False

    def get_status(self) -> dict:
        return {
            "received": self.total_data_received,
            "pieces_done": len(self.completed_pieces)
        }