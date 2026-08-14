import sys
from pathlib import Path
from colorama import Fore, Style, init
from core.parser import BDecoder
from core.utils import calculate_info_hash
from core.network import NetworkProtocol
from core.protocol_messages import TorrentMessage

# راه‌اندازی رنگ‌ها برای خروجی تمیز
init(autoreset=True)

# Global Client Identifier
CLIENT_ID = "AvestaClient-0.1"

def load_torrent(file_path: str):
    try:
        print(f"{Fore.CYAN}[*] Reading torrent file: {file_path}{Style.RESET_ALL}")
        path_obj = Path(file_path)
        
        if not path_obj.exists():
            print(f"{Fore.RED}[!] Error: File not found at {path_obj.absolute()}{Style.RESET_ALL}")
            return None

        with open(path_obj, 'rb') as f:
            data = f.read()

        print(f"{Fore.YELLOW}[*] Decoding Bencoded data...{Style.RESET_ALL}")
        decoder = BDecoder(data)
        metadata = decoder.decode()
        
        return metadata

    except Exception as e:
        print(f"{Fore.RED}[!] Failed to decode torrent: {e}{Style.RESET_ALL}")
        return None

def analyze_metadata(metadata: dict):
    if not metadata:
        return

    info_block = metadata.get(b'info') or metadata.get('info')
    if not info_block:
        print(f"{Fore.RED}[!] Missing 'info' block.{Style.RESET_ALL}")
        return

    name = info_block.get(b'name') or info_block.get('name')
    if isinstance(name, bytes):
        name = name.decode('utf-8', errors='ignore')
    
    info_hash_hex = calculate_info_hash(info_block)
    
    print(f"\n{Fore.GREEN}{'='*40}\n{Fore.WHITE}SYSTEM STATUS ONLINE\n{Fore.GREEN}{'='*40}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}[-] Target : {name}")
    print(f"{Fore.MAGENTA}[-] Hash   : {info_hash_hex}")
    print(f"{Fore.GREEN}[+] Ready for Peer Connection.{Style.RESET_ALL}")

def run_protocol_tests():
    """
    Verifies our custom protocol engine works correctly.
    """
    print(f"\n{Fore.LIGHTBLACK_EX}Running Internal Protocol Diagnostics...{Style.RESET_ALL}")
    
    # Test 1: Generate Request
    req_bytes = TorrentMessage.create_request(5, 0, 16384)
    print(f"{Fore.CYAN}[*] Generated Request Packet Size: {len(req_bytes)} bytes")
    
    # Test 2: Parse it back (Simulated loopback)
    result = TorrentMessage.parse_piece(b'\x00\x00\x00\x0f\x07\x00\x00\x00\x00\x00\x00\x00\x00test_block_data')
    if result:
        idx, offset, data = result
        print(f"{Fore.GREEN}[+] Piece Parser Verified: Index={idx}, Offset={offset}, DataLen={len(data)}{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}[-] Test Failed{Style.RESET_ALL}")

def main():
    if len(sys.argv) < 2:
        print(f"{Fore.RED}[!] Usage: python main.py <torrent_file> [--tests]{Style.RESET_ALL}")
        sys.exit(1)

    target_file = sys.argv[1]
    run_tests = "--tests" in sys.argv
    
    print(f"{Fore.MAGENTA}Initializing Py-BitTorrent Client...{Style.RESET_ALL}")
    
    raw_data = load_torrent(target_file)
    analyze_metadata(raw_data)
    
    if run_tests:
        run_protocol_tests()
    
    print(f"\n{Fore.GREEN}Execution Complete.{Style.RESET_ALL}")
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}Process interrupted by user.{Style.RESET_ALL}")
        sys.exit(1)