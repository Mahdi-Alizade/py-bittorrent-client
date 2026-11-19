import argparse
import asyncio
import hashlib
import random
import string
import sys
from pathlib import Path
from colorama import Fore, Style, init

from core.client_logic import BitTorrentClient
from core.extension_protocol import ExtensionProtocol
from core.magnet_parser import MagnetURIParser
from core.parser import BDecoder, TorrentEncoder
from core.peer_guard import PeerGuard
from core.session_manager import MultiTorrentSessionManager
from core.torrent_creator import TorrentCreator
from core.web_dashboard import WebControlServer

init(autoreset=True)


def generate_peer_id() -> bytes:
    """Generates a standard 20-byte client identifier: -PY0001-xxxxxxxxxxxx"""
    random_digits = "".join(random.choices(string.ascii_letters + string.digits, k=12))
    return f"-PY0001-{random_digits}".encode("ascii")


def calculate_info_hash(info_dict: dict) -> bytes:
    """Computes exact 20-byte SHA-1 hash of the bencoded info dictionary."""
    encoded_info = TorrentEncoder.encode(info_dict)
    return hashlib.sha1(encoded_info).digest()


def calculate_info_hash_from_raw_torrent(raw_torrent_bytes: bytes, fallback_info: dict) -> bytes:
    """
    Computes exact 20-byte SHA-1 hash from the raw bencoded '4:info' dictionary slice
    to preserve raw binary piece hashes without UTF-8 re-encoding distortion.
    """
    marker = b"4:info"
    pos = raw_torrent_bytes.find(marker)
    if pos != -1:
        info_start = pos + len(marker)
        dict_len = ExtensionProtocol._find_bencoded_dict_end(raw_torrent_bytes[info_start:])
        if dict_len != -1:
            raw_info_slice = raw_torrent_bytes[info_start:info_start + dict_len]
            return hashlib.sha1(raw_info_slice).digest()

    return calculate_info_hash(fallback_info)


def build_peer_guard(blocklist_cidrs: list) -> PeerGuard:
    guard = PeerGuard()
    for cidr in blocklist_cidrs or []:
        try:
            guard.add_cidr_block(cidr)
        except Exception as exc:
            print(f"{Fore.YELLOW}[!] Invalid CIDR blocklist entry '{cidr}': {exc}{Style.RESET_ALL}")
    return guard


def handle_create_mode(args):
    source_path = args.create
    output_path = args.out or f"{Path(source_path).name}.torrent"
    tracker_list = args.tracker or []
    piece_size_bytes = args.piece_size * 1024

    print(f"{Fore.CYAN}=== Py-BitTorrent Creator ==={Style.RESET_ALL}")
    print(f"[*] Source Path: {source_path}")
    print(f"[*] Piece Size: {args.piece_size} KB")

    try:
        creator = TorrentCreator(
            source_path=source_path,
            trackers=tracker_list,
            piece_length=piece_size_bytes
        )
        saved_file, info_hash, magnet_uri = creator.save_torrent_file(output_path)
    except Exception as err:
        print(f"{Fore.RED}[-] Failed to create torrent: {err}{Style.RESET_ALL}")
        sys.exit(1)

    print(f"{Fore.GREEN}[+] Torrent created successfully!{Style.RESET_ALL}")
    print(f"[*] Saved File: {saved_file.resolve()}")
    print(f"[*] Info Hash (Hex): {info_hash.hex()}")
    print(f"{Fore.YELLOW}[*] Magnet URI:{Style.RESET_ALL}\n{magnet_uri}")


async def run_daemon_mode(args, peer_id: bytes, use_dht: bool, guard: PeerGuard):
    session_mgr = MultiTorrentSessionManager(
        peer_id=peer_id,
        listen_port=args.port,
        enable_dht=use_dht,
        enable_lpd=True,
        max_peers_per_torrent=args.max_peers,
        watch_dir=args.watch_dir,
        peer_guard=guard
    )
    session_mgr.start_background_services()

    web_server = WebControlServer(
        session_manager=session_mgr,
        host="127.0.0.1",
        port=args.web_port
    )
    bound_web_port = await web_server.start()

    print(f"{Fore.CYAN}=== Py-BitTorrent Multi-Torrent Daemon ==={Style.RESET_ALL}")
    print(f"{Fore.GREEN}[+] Web Control Dashboard: http://127.0.0.1:{bound_web_port}{Style.RESET_ALL}")
    print(f"[*] P2P Listen Port: {args.port} | DHT: {'ON' if use_dht else 'OFF'} | LPD: ON")
    if args.watch_dir:
        print(f"[*] Hot Watch-Folder Active: {Path(args.watch_dir).resolve()}")

    if args.target:
        target_str = args.target.strip()
        if target_str.startswith("magnet:?"):
            await session_mgr.add_magnet_uri(target_str)
        else:
            await session_mgr.add_torrent_file(target_str)

    try:
        while True:
            await asyncio.sleep(2.0)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print(f"\n{Fore.YELLOW}[*] Shutting down daemon cleanly...{Style.RESET_ALL}")
    finally:
        for hex_id in list(session_mgr.sessions.keys()):
            await session_mgr.pause_torrent(hex_id)
        session_mgr.stop_background_services()
        await web_server.stop()


def main():
    parser = argparse.ArgumentParser(description="Py-BitTorrent Enterprise Client & Creator Engine.")
    parser.add_argument("target", nargs="?", help="Path to a .torrent file or a magnet:? URI.")
    parser.add_argument("--daemon", action="store_true", help="Run multi-torrent engine with live Web Control Dashboard.")
    parser.add_argument("--web-port", type=int, default=8080, help="HTTP port for the Web Control Dashboard (default: 8080).")
    parser.add_argument("--watch-dir", type=str, help="Folder to auto-ingest new .torrent files in daemon mode.")
    parser.add_argument("--blocklist", action="append", help="CIDR IP range(s) to block (e.g., 192.0.2.0/24).")
    parser.add_argument("--create", type=str, help="Create a .torrent file and magnet URI from a file or folder.")
    parser.add_argument("--out", type=str, help="Output .torrent file path when using --create.")
    parser.add_argument("--tracker", action="append", help="Tracker announce URL(s) when using --create.")
    parser.add_argument("--piece-size", type=int, default=256, help="Piece size in KB when using --create (default: 256).")
    parser.add_argument("--max-peers", type=int, default=25, help="Max peers to contact concurrently.")
    parser.add_argument("--port", type=int, default=6881, help="TCP port to listen for incoming peers.")
    parser.add_argument("--max-down", type=int, default=0, help="Max download speed limit in KB/s (0 = unlimited).")
    parser.add_argument("--max-up", type=int, default=0, help="Max upload speed limit in KB/s (0 = unlimited).")
    parser.add_argument("--seed", action="store_true", help="Continue seeding after download completes.")
    parser.add_argument("--no-dht", action="store_true", help="Disable decentralized Kademlia DHT peer discovery.")
    args = parser.parse_args()

    if args.create:
        handle_create_mode(args)
        return

    peer_id = generate_peer_id()
    use_dht = not args.no_dht
    guard = build_peer_guard(args.blocklist)

    if args.daemon:
        try:
            asyncio.run(run_daemon_mode(args, peer_id=peer_id, use_dht=use_dht, guard=guard))
        except KeyboardInterrupt:
            pass
        return

    if not args.target:
        parser.error("the following arguments are required: target (or use --daemon / --create <path>)")

    target_input = args.target.strip()
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

        info_hash = calculate_info_hash_from_raw_torrent(raw_torrent_data, info)
        print(f"{Fore.GREEN}[+] Torrent parsed successfully!{Style.RESET_ALL}")
        print(f"[*] Info Hash (Hex): {info_hash.hex()}")

    client = BitTorrentClient(
        metadata,
        enable_dht=use_dht,
        listen_port=args.port,
        max_download_rate=max_down_bytes,
        max_upload_rate=max_up_bytes,
        peer_guard=guard
    )
    client.start_download_loop(
        raw_info_hash=info_hash,
        my_peer_id=peer_id,
        max_peers=args.max_peers,
        seed_after_download=args.seed
    )


if __name__ == "__main__":
    main()