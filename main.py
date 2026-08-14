import sys
from pathlib import Path
from colorama import Fore, Style, init
from core.parser import BDecoder
from core.utils import calculate_info_hash
from core.network import NetworkProtocol

# راه‌اندازی رنگ‌ها برای خروجی تمیز
init(autoreset=True)

# Global Client Identifier (Must be <= 20 characters)
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

    print(f"\n{Fore.GREEN}{'='*40}\n{Fore.WHITE}METADATA ANALYSIS & NETWORK SETUP\n{Fore.GREEN}{'='*40}{Style.RESET_ALL}")
    
    # --- Step 1: Identify the File ---
    info_block = metadata.get(b'info') or metadata.get('info')
    if not info_block:
        print(f"{Fore.RED}[!] Missing 'info' block. Cannot proceed.{Style.RESET_ALL}")
        return

    name = info_block.get(b'name') or info_block.get('name')
    if isinstance(name, bytes):
        name = name.decode('utf-8', errors='ignore')
    
    print(f"{Fore.WHITE}[-] Target File : {name}")
    
    # --- Step 2: Calculate Info Hash ---
    print(f"{Fore.YELLOW}[*] Calculating unique SWARM ID (Info Hash)...{Style.RESET_ALL}")
    try:
        info_hash_hex = calculate_info_hash(info_block)
        print(f"{Fore.MAGENTA}[-] Info Hash   : {info_hash_hex}{Style.RESET_ALL}")
        
        # --- Step 3: Generate Handshake Payload ---
        print(f"{Fore.GREEN}[*] Building Handshake Packet for Peer Connection...{Style.RESET_ALL}")
        handshake_packet = NetworkProtocol.build_handshake(info_hash_hex, CLIENT_ID)
        
        print(f"{Fore.LIGHTWHITE_EX}[-] Packet Size : {len(handshake_packet)} bytes")
        print(f"{Fore.LIGHTWHITE_EX}[-] Payload     : {handshake_packet[:20]}... {handshake_packet[-5:]}{Style.RESET_ALL}")
        
        print(f"\n{Fore.GREEN}System Ready: The handshake packet is now waiting in memory.{Style.RESET_ALL}")

    except Exception as calc_err:
        print(f"{Fore.RED}[!] Critical failure during hash generation: {calc_err}{Style.RESET_ALL}")

def main():
    if len(sys.argv) < 2:
        print(f"{Fore.RED}[!] Usage: python main.py <path_to_torrent_file>{Style.RESET_ALL}")
        sys.exit(1)

    target_file = sys.argv[1]
    
    print(f"{Fore.MAGENTA}Initializing Py-BitTorrent Client...{Style.RESET_ALL}")
    
    raw_data = load_torrent(target_file)
    analyze_metadata(raw_data)
    
    print(f"\n{Fore.GREEN}Execution Complete.{Style.RESET_ALL}")
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}Process interrupted by user.{Style.RESET_ALL}")
        sys.exit(1)