import argparse
import asyncio
import hashlib
import random
import string
import sys
from pathlib import Path
from colorama import Fore, Style, init

from core.client_logic import BitTorrentClient
from core.magnet_parser import MagnetURIParser
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
    parser = argparse.ArgumentParser(description="Py-BitTorrent Client Engine.")
    parser.add_argument("target", help="Path to a .torrent file or a magnet:? URI.")
    parser.add_argument("--max-peers", type=int, default=25, help="Max peers to contact concurrently.")
    parser.add_argument("--port", type=int, default=6881, help="TCP port to listen for incoming peers.")
    parser.add_argument("--max-down", type=int, default=0, help="Max download speed limit in KB/s (0 = unlimited).")
    parser.add_argument("--max-up", type=int, default=0, help="Max upload speed limit in KB/s (0 = unlimited).")
    parser.add_argument("--seed", action="store_true", help="Continue seeding after download completes.")
    parser.add_argument("--no-dht", action="store_true", help="Disable decentralized Kademlia DHT peer discovery.")
    args = parser.parse_args()

    target_input = args.target.strip()
    peer_id = generate_peer_id()
    use_dht = not args.no_dht

    max_down_bytes = args.max_down * 1024 if args.max_down > 0 else None
    max_up_bytes = args.max_up * 1024 if args.max_up > 0 else None

    print(f"{Fore.CYAN}=== Py-BitTorrent Client ==={Style.RESET_ALL}")
    print(f"[*] Peer ID: {peer_id.decode('latin-1', errors='replace')}")
    print(f"[*] Listen Port: {args.port} | Kademlia DHT: {'ENABLED' if use_dht else 'DISABLED'}")
    if max_down_bytes or max_up_bytes:
        down_label = f"{args.max_down} KB/s" if args.max_down > 0 else "Unlimited"
        up_label = f"{args.max_up} KB/s" if args.max_up > 0 else "Unlimited"
        print(f"[*] Bandwidth Limits -> Down: {down_label} | Up: {up_label}")

    if target_input.startswith("magnet:?"):
        try:
            magnet_data = MagnetURIParser.parse(target_input)
        except ValueError as err:
            print(f"{Fore.RED}[-] Magnet link error: {err}{Style.RESET_ALL}")
            sys.exit(1)

        info_hash = magnet_data.info_hash
        print(f"{Fore.GREEN}[+] Magnet URI parsed successfully!{Style.RESET_ALL}")
        print(f"[*] Target Name: {magnet_data.display_name}")
        print(f"[*] Info Hash (Hex): {info_hash.hex()}")

        metadata = asyncio.run(
            BitTorrentClient.fetch_metadata_from_magnet(
                magnet_data,
                peer_id,
                use_dht=use_dht
            )
        )
        if not metadata:
            print(f"{Fore.RED}[-] Could not fetch torrent metadata from swarm peers.{Style.RESET_ALL}")
            sys.exit(1)
    else:
        torrent_file = Path(target_input)
        if not torrent_file.exists():
            print(f"{Fore.RED}[-] Torrent file not found: {torrent_file}{Style.RESET_ALL}")
            sys.exit(1)

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
        print(f"{Fore.GREEN}[+] Torrent parsed successfully!{Style.RESET_ALL}")
        print(f"[*] Info Hash (Hex): {info_hash.hex()}")

    client = BitTorrentClient(
        metadata,
        enable_dht=use_dht,
        listen_port=args.port,
        max_download_rate=max_down_bytes,
        max_upload_rate=max_up_bytes
    )
    client.start_download_loop(
        raw_info_hash=info_hash,
        my_peer_id=peer_id,
        max_peers=args.max_peers,
        seed_after_download=args.seed
    )


if __name__ == "__main__":
    main()