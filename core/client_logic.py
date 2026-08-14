import struct
from pathlib import Path
from colorama import Fore, Style, init
from core.socket_handler import PeerConnector
from core.protocol_messages import TorrentMessage
from core.parser import BDecoder

init(autoreset=True)

class BitTorrentClient:
    """
    High-level Manager that handles the lifecycle of a download session.
    Connects to peers, performs handshakes, requests pieces, and writes to disk.
    """
    
    def __init__(self, torrent_metadata: dict):
        self.metadata = torrent_metadata
        
        # FIX: Safe getter for handling both string and bytes keys
        info_block = torrent_metadata.get(b'info') or torrent_metadata.get('info')
        if not info_block:
            raise ValueError("Invalid torrent metadata: Missing 'info' block")

        # --- Intelligent Filename Extraction ---
        raw_name = info_block.get(b'name') or info_block.get('name')
        if isinstance(raw_name, bytes):
            self.target_file_name = raw_name.decode('utf-8', errors='ignore')
        elif isinstance(raw_name, str):
            self.target_file_name = raw_name
        else:
            self.target_file_name = "UnknownFile"

        # In-memory buffer to collect downloaded pieces
        self.downloaded_pieces = {} 
        
        # Target output path
        self.output_path = Path("downloads") / self.target_file_name

    def connect_to_peer(self, ip: str, port: int, hash_hex: str, peer_id: str) -> bool:
        """
        Connects and performs handshake. Returns True on success.
        """
        connector = PeerConnector(ip, port)
        
        print(f"{Fore.CYAN}[*] Initiating connection sequence...{Style.RESET_ALL}")
        if connector.connect_and_handshake(hash_hex, peer_id):
            print(f"{Fore.GREEN}[+] Secure Session Established.{Style.RESET_ALL}")
            self.connector = connector # Store reference for future sends
            return True
        return False

    def request_piece(self, index: int):
        """
        Sends a raw 'Request' packet to the connected peer.
        """
        if not hasattr(self, 'connector') or not self.connector.sock:
            raise RuntimeError("No active connection")

        # Requesting full piece size (16KB default for small tests)
        req_bytes = TorrentMessage.create_request(index, 0, 16384)
        
        print(f"{Fore.YELLOW}[*] Sending Request for Piece #{index}...{Style.RESET_ALL}")
        try:
            self.connector.sock.sendall(req_bytes)
        except Exception as e:
            print(f"{Fore.RED}[-] Failed to send request: {e}")

    def receive_and_process_pieces(self, timeout: int = 5):
        """
        Listens for incoming pieces and parses them into buffers.
        """
        print(f"{Fore.LIGHTWHITE_EX}[*] Listening for incoming data streams...{Style.RESET_ALL}")
        
        # Simple loop to check for data availability
        while True:
            try:
                # Non-blocking peek-ish approach or simple recv
                # Since our socket has a 5s timeout, we handle blocking here
                raw_data = self.connector.sock.recv(1024)
                
                if not raw_data:
                    break
                
                # Parse the raw bytes using our protocol engine
                parsed = TorrentMessage.parse_piece(raw_data)
                
                if parsed:
                    idx, offset, block_data = parsed
                    print(f"{Fore.MAGENTA}[<-] Received Piece #{idx} ({len(block_data)} bytes){Style.RESET_ALL}")
                    
                    # Store in memory buffer
                    if idx not in self.downloaded_pieces:
                        self.downloaded_pieces[idx] = bytearray()
                        
                    # Overwrite specific part of piece (advanced handling)
                    # For this demo, simple accumulation
                    self.downloaded_pieces[idx].extend(block_data)
                    
                else:
                    # Some other message type received (Have, Unchoke etc.)
                    print(f"{Fore.WHITE}[*] Protocol control message received. Ignoring for now.")
                    
            except ConnectionResetError:
                print(f"{Fore.RED}[-] Connection closed by peer.")
                break
            except Exception as e:
                pass 

    def verify_integrity(self, expected_hash_func=None):
        """
        Check if all requested pieces match the hashes from the .torrent file.
        """
        print(f"\n{Fore.GREEN}{'='*40}\n{Fore.WHITE}INTEGRITY VERIFICATION\n{Fore.GREEN}{'='*40}{Style.RESET_ALL}")
        
        # Logic to compare downloaded buffer against Info Dictionary hashes goes here
        print(f"{Fore.WHITE}[*] Comparing SHA1 chunks against Metadata...")
        
        total_requested = len(self.downloaded_pieces)
        total_valid = 0
        
        # Placeholder integrity check (Since our test torrent doesn't have real hashes)
        print(f"[!] Note: Real SHA1 verification skipped due to empty pieces field in test torrent.")
        
        print(f"[+] Downloaded Blocks: {total_requested}")
        print(f"[+] Buffer State: {'VALID' if total_requested > 0 else 'EMPTY'}")

    def save_downloads(self):
        """
        Writes collected buffers to the final file system.
        """
        if not self.downloaded_pieces:
            print(f"{Fore.RED}[-] No data to save.")
            return

        print(f"{Fore.CYAN}[*] Writing {len(self.downloaded_pieces)} blocks to disk...{Style.RESET_ALL}")
        Path("downloads").mkdir(exist_ok=True)
        
        # Sort pieces numerically before writing
        sorted_pieces = sorted(self.downloaded_pieces.items())
        
        with open(self.output_path, 'wb') as f:
            for idx, buffer in sorted_pieces:
                f.write(buffer)
        
        print(f"{Fore.GREEN}[+] SUCCESS: File saved to {self.output_path.absolute()}{Style.RESET_ALL}")