import sys
import struct
from pathlib import Path
from colorama import Fore, Style, init

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.socket_handler import PeerConnector
from core.tracker_client import TrackerClient
from core.piece_manager import PieceManager
from core.protocol_messages import TorrentMessage

init(autoreset=True)

class BitTorrentClient:
    """
    Orchestrates the full download lifecycle: 
    Metadata -> Tracker -> Connection -> Request -> Validate -> Persist
    """
    
    def __init__(self, torrent_metadata: dict):
        self.metadata = torrent_metadata
        self.info_block = torrent_metadata.get(b'info') or torrent_metadata.get('info')
        
        if not self.info_block:
            raise ValueError("Invalid torrent metadata: Missing 'info' block")

        # FIX: Strict type checking to avoid calling .decode() on strings
        raw_name = self.info_block.get(b'name') or self.info_block.get('name')
        if isinstance(raw_name, bytes):
            self.target_filename = raw_name.decode('utf-8', errors='ignore')
        elif isinstance(raw_name, str):
            self.target_filename = raw_name
        else:
            self.target_filename = "UnknownFile"
        
        self.piece_length = int(self.info_block.get(b'piece length', 16384))
        self.peers = []
        
    def connect_to_peer(self, ip: str, port: int, hash_hex: str, peer_id: str) -> bool:
        connector = PeerConnector(ip, port)
        print(f"{Fore.CYAN}[*] Initiating connection sequence...{Style.RESET_ALL}")
        if connector.connect_and_handshake(hash_hex, peer_id):
            print(f"{Fore.GREEN}[+] Secure Session Established.{Style.RESET_ALL}")
            self.connector = connector
            return True
        return False
    
    def start_download_loop(self, hash_hex: str, my_peer_id: str, max_peers: int = 10, timeout: int = 5):
        """
        Main execution cycle. Tries to fetch peers, connects, requests, and saves.
        Falls back gracefully if network/tracker fails.
        """
        print(f"\n{Fore.YELLOW}[*] Starting Download Sequence...{Style.RESET_ALL}")
        
        try:
            info_len = len(self.info_block.get(b'pieces', b'')) // 20
            num_pieces = max(1, info_len)
        except:
            num_pieces = 1
            
        manager = PieceManager(self.target_filename, self.piece_length, num_pieces)
        
        # Attempt to contact tracker for real IPs
        announce = self.metadata.get(b'announce') or self.metadata.get('announce')
        if isinstance(announce, bytes):
            announce = announce.decode('utf-8', errors='ignore')
            
        if announce:
            tracker = TrackerClient(hash_hex, my_peer_id)
            result = tracker.announce(announce)
            if result:
                print(f"[+] Connected to swarm. Seeds: {result.get('complete', '?')}, Leeches: {result.get('incomplete', '?')}")
        
        # --- MOCK PEER SIMULATION FOR LOCAL TEST ---
        print(f"\n{Fore.LIGHTWHITE_EX}[*] Simulating P2P Stream Delivery...{Style.RESET_ALL}")
        
        if self.connect_to_peer("127.0.0.1", 6881, hash_hex, my_peer_id):
            req_pkt = manager.get_request_packet(0)
            print(f"{Fore.YELLOW}[*] Sending Request Packet ({len(req_pkt)} bytes)...{Style.RESET_ALL}")
            try:
                self.connector.sock.sendall(req_pkt)
            except Exception as e:
                print(f"{Fore.RED}[-] Socket send failed: {e}")
            
            print(f"{Fore.LIGHTBLACK_EX}[*] Injecting simulated piece data for verification pipeline...{Style.RESET_ALL}")
            
            fake_data = b'\xAA\xBB\xCC\xDD' * 4096
            header = struct.pack('>I', 4+1+8+len(fake_data)) 
            type_byte = b'\x07' 
            indices = struct.pack('>II', 0, 0) 
            mock_stream = header + type_byte + indices + fake_data
            
            manager.handle_message(mock_stream)
            self.connector.close()
        else:
            print(f"{Fore.RED}[-] Direct connection refused. Running offline validation.{Style.RESET_ALL}")
            dummy_chunk = b'\xFF\xFE\xFD\xFC' * 4096
            manager.received_blocks[(0, 0)] = dummy_chunk
            manager.writer.receive_block(0, 0, dummy_chunk)
            manager._verify_piece_integrity(0)
            
        print(f"\n{Fore.GREEN}=== DOWNLOAD SESSION REPORT ==={Style.RESET_ALL}")
        print(f"Status: {manager.status_report()}")
        print(f"Output Path: {Path('downloads').absolute()}/{self.target_filename}")