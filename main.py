import sys
from pathlib import Path
from colorama import Fore, Style, init
from core.parser import BDecoder
from core.utils import calculate_info_hash
from core.client_logic import BitTorrentClient
from core.protocol_messages import TorrentMessage
from core.tracker_client import TrackerClient

# راه‌اندازی رنگ‌ها برای خروجی تمیز
init(autoreset=True)

CLIENT_ID = "AvestaClient-0.1"

def load_torrent(file_path: str):
    try:
        print(f"{Fore.CYAN}[*] Loading torrent metadata: {file_path}{Style.RESET_ALL}")
        path_obj = Path(file_path)
        
        if not path_obj.exists():
            print(f"{Fore.RED}[!] Error: File not found at {path_obj.absolute()}{Style.RESET_ALL}")
            return None

        with open(path_obj, 'rb') as f:
            data = f.read()

        decoder = BDecoder(data)
        metadata = decoder.decode()
        
        print(f"{Fore.GREEN}[+] Metadata decoded successfully.{Style.RESET_ALL}")
        return metadata

    except Exception as e:
        print(f"{Fore.RED}[!] Failed to decode torrent: {e}{Style.RESET_ALL}")
        return None

def contact_tracker(metadata: dict):
    """
    Connects to a public tracker to fetch peer IPs.
    """
    if not metadata:
        return
    
    info_block = metadata.get(b'info') or metadata.get('info')
    announce = metadata.get(b'announce') or metadata.get('announce')
    
    if isinstance(announce, bytes):
        announce = announce.decode('utf-8', errors='ignore')
        
    if not announce:
        print(f"{Fore.RED}[-] No announce URL found in torrent.{Style.RESET_ALL}")
        return

    hash_hex = calculate_info_hash(info_block)
    tracker = TrackerClient(hash_hex, CLIENT_ID)
    
    # Test with a real public tracker
    result = tracker.announce(announce)
    
    if result:
        print(f"\n{Fore.GREEN}{'='*40}\n{Fore.WHITE}TRACKER RESPONSE\n{Fore.GREEN}{'='*40}{Style.RESET_ALL}")
        print(f"[+] Complete Seeds : {result.get('complete')}")
        print(f"[+] Incomplete Leeches: {result.get('incomplete')}")
        print(f"[+] Peer Data Length : {len(result.get('peers_raw', ''))}")

def run_protocol_tests():
    """Verifies our custom protocol engine works correctly."""
    print(f"\n{Fore.LIGHTBLACK_EX}Running Internal Protocol Diagnostics...{Style.RESET_ALL}")
    
    req_bytes = TorrentMessage.create_request(5, 0, 16384)
    print(f"{Fore.CYAN}[*] Generated Request Packet Size: {len(req_bytes)} bytes")
    
    result = TorrentMessage.parse_piece(b'\x00\x00\x00\x0f\x07\x00\x00\x00\x00\x00\x00\x00\x00test_block_data')
    if result:
        idx, offset, data = result
        print(f"{Fore.GREEN}[+] Piece Parser Verified: Index={idx}, Offset={offset}, DataLen={len(data)}{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}[-] Test Failed{Style.RESET_ALL}")

def main():
    if len(sys.argv) < 2:
        print(f"[!] Usage: python main.py <torrent_file> [peer_ip] [peer_port]")
        sys.exit(1)

    clean_args = [arg for arg in sys.argv[2:] if not arg.startswith("--")]
    target_file = sys.argv[1]
    run_tests_mode = "--tests" in sys.argv
    
    print(f"{Fore.MAGENTA}Initializing Py-BitTorrent Client v0.4...{Style.RESET_ALL}")
    
    metadata = load_torrent(target_file)
    contact_tracker(metadata)
    
    if run_tests_mode:
        run_protocol_tests()
    
    print(f"\n{Fore.GREEN}Process Finished.{Style.RESET_ALL}")
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}Interrupted by user.{Style.RESET_ALL}")
        sys.exit(1)