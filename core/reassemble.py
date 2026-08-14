import struct
from pathlib import Path
from colorama import Fore, Style, init
import os

init(autoreset=True)

class DownloadSession:
    """
    Manages the lifecycle of downloading and reassembling pieces into a final file.
    Handles memory buffering, block accumulation, and atomic file writing.
    """
    
    def __init__(self, filename: str, piece_length: int, output_dir: str = "downloads"):
        self.filename = filename
        self.piece_length = piece_length
        self.output_dir = Path(output_dir)
        self.final_path = self.output_dir / self.filename
        
        # Internal Buffers
        self.pending_blocks = {} # Stores chunks as they arrive: {piece_idx: bytearray}
        self.completed_pieces = [] # Order of completion
        self.total_data_received = 0
        
    def initialize_file(self):
        """Pre-allocates the file space so the OS knows how big it is."""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            if not self.final_path.exists():
                print(f"{Fore.CYAN}[*] Initializing {self.final_path.name} ({self.piece_length} bytes)...{Style.RESET_ALL}")
                
                # For testing small files, we just write one chunk. 
                # In production, you'd use ftruncate here if piece_length was known globally.
                self.final_path.touch() 
            
            return True
        except Exception as e:
            print(f"{Fore.RED}[!] Failed to initialize file: {e}{Style.RESET_ALL}")
            return False

    def receive_block(self, piece_index: int, block_offset: int, block_data: bytes):
        """
        Receives a data block and places it into the internal stream buffer.
        """
        if piece_index not in self.pending_blocks:
            # Initialize a full buffer for this piece when the first block arrives
            self.pending_blocks[piece_index] = bytearray(self.piece_length)
            print(f"{Fore.LIGHTWHITE_EX}[*] Allocating buffer for Piece #{piece_index}{Style.RESET_ALL}")
        
        # Write data to the exact byte offset
        end_pos = min(block_offset + len(block_data), self.piece_length)
        self.pending_blocks[piece_index][block_offset:end_pos] = block_data
        
        self.total_data_received += len(block_data)
        
        # Optimization: Log block arrival
        print(f"{Fore.WHITE}[-] Block #{block_offset} stored for Piece #{piece_index}")

    def verify_and_save_piece(self, piece_index: int):
        """
        Checks if a specific piece is complete and flushes it to disk.
        In a real implementation, SHA1 verification would happen here.
        """
        if piece_index in self.pending_blocks:
            buffer = self.pending_blocks.pop(piece_index)
            self.completed_pieces.append(piece_index)
            
            # Write directly to file at the correct offset
            # Note: Real torrent calculation uses 'index * piece_length'
            # Here we simplify for our 1-piece test
            
            print(f"{Fore.GREEN}[+] Completed Piece #{piece_index}. Flushing to disk...{Style.RESET_ALL}")
            
            try:
                with open(self.final_path, 'ab') as f: # Append binary mode
                    f.write(bytes(buffer))
                
                # Calculate progress percentage
                if hasattr(self, 'total_pieces'):
                     pct = (len(self.completed_pieces) / self.total_pieces) * 100
                     print(f"{Fore.YELLOW}Progress: {pct:.1f}%{Style.RESET_ALL}")
                    
            except IOError as e:
                print(f"{Fore.RED}[-] Write error: {e}{Style.RESET_ALL}")

    def get_status(self):
        """Returns current download metrics."""
        return {
            "received": self.total_data_received,
            "pieces_done": len(self.completed_pieces)
        }

def run_demo_write_session(torrent_metadata: dict):
    """
    Standalone demo of the Reassembly Engine.
    Simulates writing blocks to simulate a completed download.
    """
    if not torrent_metadata:
        return

    # Extract info block
    info = torrent_metadata.get(b'info') or torrent_metadata.get('info')
    
    name = info.get(b'name', b'test').decode('utf-8', errors='ignore')
    piece_len = info.get(b'piece length', 16384)
    
    # Initialize Session
    session = DownloadSession(name, piece_len)
    session.initialize_file()
    
    print(f"\n{Fore.MAGENTA}Simulating Stream Data Arrival...{Style.RESET_ALL}")
    
    # Mock Data Simulation (In reality this comes from socket.recv)
    fake_block_1 = b'\xAA\xBB' * 8192 # First 16k block
    fake_block_2 = b'\xCC\xDD' * 8192 # Second 16k block
    
    session.receive_block(0, 0, fake_block_1)
    session.receive_block(0, 16384, fake_block_2) # Offset matches piece length
    
    session.verify_and_save_piece(0)
    
    status = session.get_status()
    print(f"\n{Fore.GREEN}=== SESSION REPORT ==={Style.RESET_ALL}")
    print(f"Total Bytes: {status['received']}")
    print(f"Path: {session.final_path}")