import sys
from pathlib import Path
from colorama import Fore, Style, init
from core.parser import BDecoder
from core.utils import calculate_info_hash
from core.client_logic import BitTorrentClient
from core.protocol_messages import TorrentMessage
from core.tracker_client import TrackerClient

init(autoreset=True)
CLIENT_ID = "AvestaClient-0.1"

def load_torrent(path: str):
    try:
        print(f"{Fore.CYAN}[*] Loading torrent: {path}{Style.RESET_ALL}")
        with open(path, 'rb') as f:
            meta = BDecoder(f.read()).decode()
        print(f"{Fore.GREEN}[+] OK{Style.RESET_ALL}")
        return meta
    except Exception as e:
        print(f"{Fore.RED}[-] Failed: {e}{Style.RESET_ALL}")
        return None

def run_tests():
    print(f"\n{Fore.LIGHTBLACK_EX}Running Diagnostics...{Style.RESET_ALL}")
    pkt = TorrentMessage.create_request(0, 0, 16384)
    print(f"[+] Packet Size: {len(pkt)} bytes")
    res = TorrentMessage.parse_piece(b'\x00\x00\x00\x0f\x07\x00\x00\x00\x00\x00\x00\x00\x00test_block_data')
    if res:
        print(f"{Fore.GREEN}[+] Parser Verified.{Style.RESET_ALL}")

def main():
    if len(sys.argv) < 2:
        print(f"[!] Usage: python main.py <torrent_file>")
        return

    clean_args = [a for a in sys.argv[2:] if not a.startswith("--")]
    target = sys.argv[1]
    do_tests = "--tests" in sys.argv

    print(f"{Fore.MAGENTA}Initializing Py-BitTorrent Client v0.5...{Style.RESET_ALL}")
    meta = load_torrent(target)
    
    if meta:
        info = meta.get(b'info') or meta.get('info')
        h = calculate_info_hash(info)
        print(f"Hash: {h}")
        
        client = BitTorrentClient(meta)
        client.start_download_loop(h, CLIENT_ID)

    if do_tests:
        run_tests()
        
    print(f"\n{Fore.GREEN}Done.{Style.RESET_ALL}")

if __name__ == "__main__":
    main()