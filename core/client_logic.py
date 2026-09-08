import hashlib
import time
from pathlib import Path
from typing import Dict, List, Optional
from colorama import Fore, Style, init

from core.piece_manager import PieceManager
from core.protocol_messages import TorrentMessage
from core.socket_handler import PeerConnector
from core.tracker_client import TrackerClient

init(autoreset=True)


class BitTorrentClient:
    """
    Coordinates torrent lifecycle:
    Announce to Trackers -> Iterate Peers -> Handshake -> Choke/Unchoke -> Download & Assemble.
    """

    def __init__(self, torrent_metadata: dict):
        self.metadata = torrent_metadata
        self.info_block = torrent_metadata.get(b"info") or torrent_metadata.get("info")

        if not self.info_block:
            raise ValueError("Invalid torrent metadata: Missing 'info' dictionary")

        # Parse target filename
        raw_name = self.info_block.get(b"name") or self.info_block.get("name")
        if isinstance(raw_name, bytes):
            self.target_filename = raw_name.decode("utf-8", errors="ignore")
        elif isinstance(raw_name, str):
            self.target_filename = raw_name
        else:
            self.target_filename = "downloaded_file.bin"

        self.piece_length = int(self.info_block.get(b"piece length") or self.info_block.get("piece length", 16384))
        
        # Calculate file total length
        if b"length" in self.info_block:
            self.total_length = int(self.info_block[b"length"])
        elif "length" in self.info_block:
            self.total_length = int(self.info_block["length"])
        elif b"files" in self.info_block or "files" in self.info_block:
            files = self.info_block.get(b"files") or self.info_block.get("files", [])
            self.total_length = sum(int(f.get(b"length") or f.get("length", 0)) for f in files)
        else:
            self.total_length = self.piece_length

        # Parse SHA-1 piece hashes (20 bytes each)
        raw_pieces = self.info_block.get(b"pieces") or self.info_block.get("pieces", b"")
        if isinstance(raw_pieces, str):
            raw_pieces = raw_pieces.encode("latin-1")
        self.piece_hashes = [raw_pieces[i:i + 20] for i in range(0, len(raw_pieces), 20)]
        self.num_pieces = len(self.piece_hashes) if self.piece_hashes else 1

    def start_download_loop(self, raw_info_hash: bytes, my_peer_id: bytes, max_peers: int = 10):
        """
        Executes download across swarm peers.
        """
        print(f"\n{Fore.YELLOW}[*] Initializing Download Sequence for '{self.target_filename}'...{Style.RESET_ALL}")
        print(f"[*] Total size: {self.total_length} bytes | Total pieces: {self.num_pieces}")

        manager = PieceManager(
            self.target_filename,
            self.piece_length,
            self.num_pieces,
            total_length=self.total_length
        )
        manager.writer.piece_hashes = self.piece_hashes

        # Fetch peers from tracker
        tracker_url = self.metadata.get(b"announce") or self.metadata.get("announce")
        if isinstance(tracker_url, bytes):
            tracker_url = tracker_url.decode("utf-8", errors="ignore")

        discovered_peers: List = []
        if tracker_url:
            tracker = TrackerClient(raw_info_hash, my_peer_id)
            announce_res = tracker.announce(tracker_url, left=self.total_length)
            discovered_peers = announce_res.get("peers", [])

        # Fallback to localhost if no peers found (useful for offline tests)
        if not discovered_peers:
            print(f"{Fore.YELLOW}[*] No remote peers discovered. Adding local fallback (127.0.0.1:6881)...{Style.RESET_ALL}")
            discovered_peers = [("127.0.0.1", 6881)]

        # Connect to peers
        for ip, port in discovered_peers[:max_peers]:
            if all(manager.have_pieces):
                break

            connector = PeerConnector(ip, port, timeout=4.0)
            if not connector.connect_and_handshake(raw_info_hash, my_peer_id):
                continue

            try:
                # Send Interested message
                connector.send_message(TorrentMessage.create_interested())

                # Read responses with short timeout
                start_time = time.time()
                while time.time() - start_time < 8.0:
                    msg = connector.receive_message()
                    if not msg:
                        break

                    manager.handle_message(msg)

                    # Send next request if available
                    for piece_idx in range(self.num_pieces):
                        if not manager.have_pieces[piece_idx]:
                            req = manager.get_next_request(piece_idx)
                            if req:
                                connector.send_message(req)
                                break

                    if all(manager.have_pieces):
                        break

            except Exception as e:
                print(f"{Fore.RED}[-] Peer interaction error: {e}{Style.RESET_ALL}")
            finally:
                connector.close()

        print(f"\n{Fore.GREEN}=== DOWNLOAD SESSION REPORT ==={Style.RESET_ALL}")
        print(f"Status: {manager.status_report()}")
        print(f"Output: {manager.writer.final_path.resolve()}")