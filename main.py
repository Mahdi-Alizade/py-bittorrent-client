import sys
from pathlib import Path
from colorama import Fore, Style, init
from core.parser import BDecoder
from core.utils import calculate_info_hash
from core.client_logic import BitTorrentClient
from core.protocol_messages import TorrentMessage

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

def run_download_session(metadata: dict, peer_ip: str, peer_port: int):
    """
    Main execution loop: Hash -> Connect -> Request -> Receive -> Verify -> Save
    """
    if not metadata:
        return

    info_block = metadata.get(b'info') or metadata.get('info')
    if not info_block:
        print(f"{Fore.RED}[-] Critical: Missing 'info' dictionary.{Style.RESET_ALL}")
        return

    print(f"\n{Fore.YELLOW}[*] Calculating Swarm ID...{Style.RESET_ALL}")
    try:
        hash_hex = calculate_info_hash(info_block)
    except Exception as e:
        print(f"{Fore.RED}[-] Hash generation failed: {e}{Style.RESET_ALL}")
        return

    print(f"{Fore.MAGENTA}[-] Info Hash : {hash_hex}{Style.RESET_ALL}")
    print(f"{Fore.LIGHTWHITE_EX}[+] Initializing Download Engine...{Style.RESET_ALL}")
    
    client = BitTorrentClient(metadata)
    
    print(f"{Fore.CYAN}[*] Establishing P2P Session at {peer_ip}:{peer_port}...{Style.RESET_ALL}")
    if client.connect_to_peer(peer_ip, int(peer_port), hash_hex, CLIENT_ID):
        print(f"{Fore.GREEN}[+] Connection Secure.{Style.RESET_ALL}")
        client.request_piece(0)
        client.receive_and_process_pieces(timeout=5)
        
        print(f"\n{Fore.GREEN}{'='*40}\n{Fore.WHITE}SESSION COMPLETE\n{Fore.GREEN}{'='*40}{Style.RESET_ALL}")
        client.verify_integrity()
        client.save_downloads()
    else:
        print(f"{Fore.RED}[-] Handshake failed or peer unreachable.{Style.RESET_ALL}")

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

    # FIX: Clean arguments to avoid flags like '--tests' being parsed as IP
    clean_args = [arg for arg in sys.argv[2:] if not arg.startswith("--")]
    
    target_file = sys.argv[1]
    peer_ip = clean_args[0] if len(clean_args) > 0 else "127.0.0.1"
    peer_port = clean_args[1] if len(clean_args) > 1 else "6881"
    run_tests_mode = "--tests" in sys.argv
    
    print(f"{Fore.MAGENTA}Initializing Py-BitTorrent Client v0.3...{Style.RESET_ALL}")
    
    metadata = load_torrent(target_file)
    run_download_session(metadata, peer_ip, peer_port)
    
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