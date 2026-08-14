import sys
from pathlib import Path
from colorama import Fore, Style, init
from core.parser import BDecoder

# راه‌اندازی رنگ‌ها برای خروجی تمیز
init(autoreset=True)

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

    print(f"\n{Fore.GREEN}{'='*40}\n{Fore.WHITE}METADATA ANALYSIS\n{Fore.GREEN}{'='*40}{Style.RESET_ALL}")
    
    # Extract Announce
    announce = metadata.get(b'announce', b'No URL').decode('utf-8', errors='ignore')
    print(f"{Fore.WHITE}[-] Tracker : {announce}")

    # Extract Files
    if 'info' in metadata:
        info = metadata[b'info']
        
        if 'name' in info:
            name = info[b'name']
            if isinstance(name, bytes):
                name = name.decode('utf-8', errors='ignore')
            print(f"{Fore.WHITE}[-] Name    : {name}")
            
        if 'piece length' in info:
            piece_len = info[b'piece length']
            print(f"{Fore.WHITE}[-] Piece Len: {piece_len} bytes")
            
        # Info Hash calculation (Real implementation requires hashing 'info' dict)
        # We'll do this strictly in the future, but for now showing structure
        info_hash_raw = metadata.get(b'meta-infohash', 'N/A') # Placeholder
        print(f"{Fore.WHITE}[-] Status  : Metadata Loaded Successfully")
    else:
        print(f"{Fore.YELLOW}[-] This looks like a multi-file torrent structure.")

    # Print raw keys for debugging
    # print(f"\nRaw Keys: {list(metadata.keys())}")

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