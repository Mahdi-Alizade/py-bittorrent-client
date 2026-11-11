import asyncio
import time
from pathlib import Path
from typing import Dict, List, Optional
from colorama import Fore, Style, init

from core.async_peer import AsyncPeerConnection
from core.piece_manager import PieceManager
from core.protocol_messages import TorrentMessage
from core.tracker_client import TrackerClient

init(autoreset=True)


class BitTorrentClient:
    """
    Asynchronous BitTorrent client orchestrating parallel peer workers,
    pipelined block downloads, and rarest-first piece scheduling.
    """

    def __init__(self, torrent_metadata: dict):
        self.metadata = torrent_metadata
        self.info_block = torrent_metadata.get(b"info") or torrent_metadata.get("info")

        if not self.info_block:
            raise ValueError("Invalid torrent metadata: Missing 'info' dictionary")

        # Extract target filename safely
        raw_name = self.info_block.get(b"name") or self.info_block.get("name")
        if isinstance(raw_name, bytes):
            self.target_filename = raw_name.decode("utf-8", errors="ignore")
        elif isinstance(raw_name, str):
            self.target_filename = raw_name
        else:
            self.target_filename = "downloaded_payload.bin"

        # Determine piece length
        self.piece_length = int(
            self.info_block.get(b"piece length") or self.info_block.get("piece length", 16384)
        )

        # Calculate total byte length
        if b"length" in self.info_block:
            self.total_length = int(self.info_block[b"length"])
        elif "length" in self.info_block:
            self.total_length = int(self.info_block["length"])
        elif b"files" in self.info_block or "files" in self.info_block:
            files_list = self.info_block.get(b"files") or self.info_block.get("files", [])
            total_sum = 0
            for item in files_list:
                file_len = item.get(b"length") or item.get("length", 0)
                total_sum += int(file_len)
            self.total_length = total_sum
        else:
            self.total_length = self.piece_length

        # Extract 20-byte SHA-1 hashes for each piece
        raw_pieces = self.info_block.get(b"pieces") or self.info_block.get("pieces", b"")
        if isinstance(raw_pieces, str):
            raw_pieces = raw_pieces.encode("latin-1")

        self.piece_hashes: List[bytes] = []
        for offset in range(0, len(raw_pieces), 20):
            self.piece_hashes.append(raw_pieces[offset:offset + 20])

        if len(self.piece_hashes) > 0:
            self.num_pieces = len(self.piece_hashes)
        else:
            self.num_pieces = 1

    async def _peer_worker(
        self,
        ip: str,
        port: int,
        raw_info_hash: bytes,
        my_peer_id: bytes,
        manager: PieceManager,
        pipeline_depth: int = 4
    ):
        """
        Independent async worker dedicated to handling bidirectional protocol
        traffic with a single peer connection.
        """
        peer_tag = f"{ip}:{port}"
        peer_conn = AsyncPeerConnection(ip, port, raw_info_hash, my_peer_id, timeout=5.0)

        connected = await peer_conn.connect_and_handshake()
        if not connected:
            return

        manager.register_peer(peer_tag)
        print(f"{Fore.GREEN}[+] Worker active for peer {peer_tag}{Style.RESET_ALL}")

        try:
            # Express interest
            await peer_conn.send_message(TorrentMessage.create_interested())

            while not all(manager.have_pieces):
                # 1. Pipeline block requests if unchoked
                if not peer_conn.is_choked:
                    for _ in range(pipeline_depth):
                        req_packet = manager.get_next_request_for_peer(peer_tag)
                        if req_packet is not None:
                            sent = await peer_conn.send_message(req_packet)
                            if not sent:
                                break
                        else:
                            break

                # 2. Read incoming wire message with timeout
                try:
                    read_coro = peer_conn.read_message()
                    raw_msg = await asyncio.wait_for(read_coro, timeout=3.0)
                except asyncio.TimeoutError:
                    # Timeout check: keep worker alive or send keep-alive
                    await peer_conn.send_message(TorrentMessage.create_keep_alive())
                    continue

                if raw_msg is None:
                    break

                # 3. Parse and update state
                if len(raw_msg) == 4 and raw_msg == b"\x00\x00\x00\x00":
                    continue

                msg_id = raw_msg[4]

                if msg_id == TorrentMessage.MSG_UNCHOKE:
                    peer_conn.is_choked = False
                    print(f"{Fore.LIGHTCYAN_EX}[<-] Unchoked by peer {peer_tag}{Style.RESET_ALL}")

                elif msg_id == TorrentMessage.MSG_CHOKE:
                    peer_conn.is_choked = True
                    print(f"{Fore.LIGHTYELLOW_EX}[<-] Choked by peer {peer_tag}{Style.RESET_ALL}")

                elif msg_id == TorrentMessage.MSG_HAVE:
                    piece_idx = TorrentMessage.parse_have(raw_msg)
                    if piece_idx is not None:
                        manager.handle_peer_have(peer_tag, piece_idx)

                elif msg_id == TorrentMessage.MSG_BITFIELD:
                    bitfield_data = raw_msg[5:]
                    manager.handle_peer_bitfield(peer_tag, bitfield_data)

                elif msg_id == TorrentMessage.MSG_PIECE:
                    manager.handle_message(raw_msg)

        except Exception as err:
            print(f"{Fore.RED}[!] Peer worker error ({peer_tag}): {err}{Style.RESET_ALL}")
        finally:
            manager.unregister_peer(peer_tag)
            await peer_conn.close()

    async def start_async_download(
        self,
        raw_info_hash: bytes,
        my_peer_id: bytes,
        max_peers: int = 15
    ):
        print(f"\n{Fore.YELLOW}[*] Launching Async Engine for '{self.target_filename}'...{Style.RESET_ALL}")
        print(f"[*] Total Bytes: {self.total_length} | Total Pieces: {self.num_pieces}")

        manager = PieceManager(
            filename=self.target_filename,
            piece_length=self.piece_length,
            num_pieces=self.num_pieces,
            total_length=self.total_length
        )
        manager.writer.piece_hashes = self.piece_hashes

        # Announce to tracker
        tracker_url = self.metadata.get(b"announce") or self.metadata.get("announce")
        if isinstance(tracker_url, bytes):
            tracker_url = tracker_url.decode("utf-8", errors="ignore")

        discovered_peers: List = []
        if tracker_url:
            tracker = TrackerClient(raw_info_hash, my_peer_id)
            announce_data = tracker.announce(tracker_url, left=self.total_length)
            discovered_peers = announce_data.get("peers", [])

        if not discovered_peers:
            print(f"{Fore.YELLOW}[*] No external peers found. Setting local swarm test entry (127.0.0.1:6881)...{Style.RESET_ALL}")
            discovered_peers = [("127.0.0.1", 6881)]

        # Spawn concurrent async workers
        active_worker_tasks = []
        for peer_ip, peer_port in discovered_peers[:max_peers]:
            worker_task = asyncio.create_task(
                self._peer_worker(
                    ip=peer_ip,
                    port=peer_port,
                    raw_info_hash=raw_info_hash,
                    my_peer_id=my_peer_id,
                    manager=manager
                )
            )
            active_worker_tasks.append(worker_task)

        # Progress monitor loop
        while not all(manager.have_pieces):
            all_done = True
            for t in active_worker_tasks:
                if not t.done():
                    all_done = False
                    break

            if all_done:
                print(f"{Fore.RED}[-] All active workers finished or disconnected.{Style.RESET_ALL}")
                break

            await asyncio.sleep(1.0)
            print(f"{Fore.CYAN}[*] Download Progress: {manager.status_report()}{Style.RESET_ALL}")

        # Cancel remaining workers once complete
        for t in active_worker_tasks:
            if not t.done():
                t.cancel()

        print(f"\n{Fore.GREEN}=== DOWNLOAD SESSION COMPLETED ==={Style.RESET_ALL}")
        print(f"Status: {manager.status_report()}")
        print(f"Output File: {manager.writer.final_path.resolve()}")

    def start_download_loop(self, raw_info_hash: bytes, my_peer_id: bytes, max_peers: int = 10):
        """Synchronous wrapper to bootstrap the asyncio event loop."""
        asyncio.run(
            self.start_async_download(
                raw_info_hash=raw_info_hash,
                my_peer_id=my_peer_id,
                max_peers=max_peers
            )
        )