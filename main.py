import sys
from pathlib import Path
from colorama import Fore, Style, init
from core.parser import BDecoder

# راه‌اندازی رنگ‌ها برای خروجی تمیز
init(autoreset=True)

def get_key_safe(data: dict, target_key_str: str, default=None):
    """
    Finds a key in dictionary regardless of it being a string or bytes.
    """
    # Try as bytes first
    key_bytes = target_key_str.encode('utf-8')
    if key_bytes in data:
        return data[key_bytes]
    
    # Try as string
    if target_key_str in data:
        return data[target_key_str]
    
    return default

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

    # --- DIAGNOSTIC LOG ---
    print(f"\n{Fore.MAGENTA}[DIAG] Available Keys: {list(metadata.keys())}{Style.RESET_ALL}")
    # ----------------------

    print(f"\n{Fore.GREEN}{'='*40}\n{Fore.WHITE}METADATA ANALYSIS\n{Fore.GREEN}{'='*40}{Style.RESET_ALL}")
    
    # Extract Announce using safe getter
    announce = get_key_safe(metadata, 'announce', b'No URL')
    # Convert bytes to string if necessary for display
    announce_str = announce.decode('utf-8', errors='ignore') if isinstance(announce, bytes) else announce
    print(f"{Fore.WHITE}[-] Tracker : {announce_str}")

    # Extract Files and Info
    # Info can also be nested inside meta-info-hash or just main keys
    # Standard torrent has 'info' at the top level
    
    # Try getting 'info' from main metadata
    info_raw = get_key_safe(metadata, 'info')
    
    if info_raw:
        print(f"{Fore.WHITE}[-] Structure: Found 'info' block!")
        
        name = get_key_safe(info_raw, 'name', 'Unknown Name')
        piece_len = get_key_safe(info_raw, 'piece length', 0)
        
        print(f"{Fore.WHITE}[-] Name    : {name}")
        print(f"{Fore.WHITE}[-] Piece Len: {piece_len} bytes")
    else:
        print(f"{Fore.RED}[-] Critical Warning: No 'info' block found in metadata!{Style.RESET_ALL}")

def main():
    """Main Entry Point"""
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