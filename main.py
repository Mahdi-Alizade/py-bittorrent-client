import argparse
import hashlib
import os
import random
import string
import sys
from pathlib import Path
from colorama import Fore, Style, init

from core.client_logic import BitTorrentClient
from core.parser import BDecoder, TorrentEncoder

init(autoreset=True)


def generate_peer_id() -> bytes:
    """Generates a standard 20-byte client identifier: -PY0001-xxxxxxxxxxxx"""
    random_digits = "".join(random.choices(string.ascii_letters + string.digits, k=12))
    return f"-PY0001-{random_digits}".encode("ascii")


def calculate_info_hash(info_dict: dict) -> bytes:
    """Computes exact 20-byte SHA-1 hash of the bencoded info dictionary."""
    encoded_info = TorrentEncoder.encode(info_dict)
    return hashlib.sha1(encoded_info).digest()


def main():
    parser = argparse.ArgumentParser(description="Py-BitTorrent Client Engine from scratch.")
    parser.add_argument("torrent_path", help="Path to the .torrent file.")
    parser.add_argument("--max-peers", type=int, default=10, help="Max peers to contact concurrently.")
    args = parser.parse_args()

    torrent_file = Path(args.torrent_path)
    if not torrent_file.exists():
        print(f"{Fore.RED}[-] Torrent file not found: {torrent_file}{Style.RESET_ALL}")
        sys.exit(1)

    print(f"{Fore.CYAN}=== Py-BitTorrent Client ==={Style.RESET_ALL}")
    print(f"[*] Reading torrent file: {torrent_file.name}")

    try:
        raw_torrent_data = torrent_file.read_bytes()
        metadata = BDecoder(raw_torrent_data).decode()
    except Exception as e:
        print(f"{Fore.RED}[-] Failed to parse torrent metainfo: {e}{Style.RESET_ALL}")
        sys.exit(1)

    info = metadata.get(b"info") or metadata.get("info")
    if not info:
        print(f"{Fore.RED}[-] Malformed torrent: missing info dictionary{Style.RESET_ALL}")
        sys.exit(1)

    info_hash = calculate_info_hash(info)
    peer_id = generate_peer_id()

    print(f"{Fore.GREEN}[+] Torrent parsed successfully!{Style.RESET_ALL}")
    print(f"[*] Info Hash (Hex): {info_hash.hex()}")
    print(f"[*] Peer ID: {peer_id.decode('latin-1', errors='replace')}")

    client = BitTorrentClient(metadata)
    client.start_download_loop(raw_info_hash=info_hash, my_peer_id=peer_id, max_peers=args.max_peers)


if __name__ == "__main__":
    main()