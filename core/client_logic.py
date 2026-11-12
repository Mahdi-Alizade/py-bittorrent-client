import asyncio
from typing import Dict, List, Optional, Set, Tuple
from colorama import Fore, Style, init

from core.async_peer import AsyncPeerConnection
from core.dht_client import DHTCrawler
from core.extension_protocol import ExtensionProtocol, MetadataAssembler
from core.magnet_parser import MagnetLinkData
from core.pex_protocol import PeerExchangeProtocol
from core.piece_manager import PieceManager
from core.protocol_messages import TorrentMessage
from core.tracker_client import TrackerClient

init(autoreset=True)


class BitTorrentClient:
    """
    Asynchronous BitTorrent client orchestrating parallel peer workers,
    pipelined block downloads, rarest-first scheduling, End-Game mode,
    Magnet link metadata resolution, live Peer Exchange (PEX), and Kademlia DHT.
    """

    def __init__(self, torrent_metadata: dict, enable_dht: bool = True):
        self.metadata = torrent_metadata
        self.enable_dht = enable_dht
        self.info_block = torrent_metadata.get(b"info") or torrent_metadata.get("info")

        if not self.info_block:
            raise ValueError("Invalid torrent metadata: Missing 'info' dictionary")

        raw_name = self.info_block.get(b"name") or self.info_block.get("name")
        if isinstance(raw_name, bytes):
            self.target_filename = raw_name.decode("utf-8", errors="ignore")
        elif isinstance(raw_name, str):
            self.target_filename = raw_name
        else:
            self.target_filename = "downloaded_payload.bin"

        self.piece_length = int(
            self.info_block.get(b"piece length") or self.info_block.get("piece length", 16384)
        )

        self.file_entries: List[Dict] = []
        raw_files = self.info_block.get(b"files") or self.info_block.get("files")

        if raw_files and isinstance(raw_files, list):
            total_sum = 0
            for item in raw_files:
                file_len = int(item.get(b"length") or item.get("length", 0))
                path_list = item.get(b"path") or item.get("path", [])
                self.file_entries.append({
                    "length": file_len,
                    "path": path_list
                })
                total_sum += file_len
            self.total_length = total_sum
        elif b"length" in self.info_block:
            self.total_length = int(self.info_block[b"length"])
        elif "length" in self.info_block:
            self.total_length = int(self.info_block["length"])
        else:
            self.total_length = self.piece_length

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

        self.active_connections: Dict[str, AsyncPeerConnection] = {}
        self.known_peers: Set[Tuple[str, int]] = set()
        self.worker_tasks: List[asyncio.Task] = []

    @classmethod
    async def fetch_metadata_from_magnet(
        cls,
        magnet_data: MagnetLinkData,
        my_peer_id: bytes,
        peer_list: Optional[List] = None,
        use_dht: bool = True
    ) -> Optional[dict]:
        """
        Resolves full torrent metadata dictionary by contacting peers over BEP-0010/BEP-0009,
        combining peers from both Trackers and Kademlia DHT.
        """
        print(f"{Fore.CYAN}[*] Resolving metadata for magnet: {magnet_data.display_name}{Style.RESET_ALL}")

        peers_to_try = list(peer_list) if peer_list else []

        if not peers_to_try and magnet_data.trackers:
            tracker = TrackerClient(magnet_data.info_hash, my_peer_id)
            for tr_url in magnet_data.trackers:
                res = tracker.announce(tr_url, left=1000)
                found = res.get("peers", [])
                for p in found:
                    if p not in peers_to_try:
                        peers_to_try.append(p)
                if len(peers_to_try) >= 15:
                    break

        # Fallback or supplement via Kademlia DHT if needed
        if len(peers_to_try) < 5 and use_dht:
            print(f"{Fore.CYAN}[*] Querying Kademlia DHT network for peers...{Style.RESET_ALL}")
            dht_crawler = DHTCrawler(local_id=my_peer_id)
            dht_peers = await asyncio.to_thread(
                dht_crawler.discover_peers_sync,
                magnet_data.info_hash,
                None,
                2,
                2.0
            )
            for p in dht_peers:
                if p not in peers_to_try:
                    peers_to_try.append(p)

        for ip, port in peers_to_try:
            conn = AsyncPeerConnection(ip, port, magnet_data.info_hash, my_peer_id, timeout=5.0)
            ok = await conn.connect_and_handshake()
            if not ok:
                continue

            if not conn.supports_extensions:
                await conn.close()
                continue

            try:
                ext_handshake = ExtensionProtocol.create_extension_handshake()
                await conn.send_message(ext_handshake)

                assembler: Optional[MetadataAssembler] = None

                for _ in range(25):
                    raw_msg = await asyncio.wait_for(conn.read_message(), timeout=4.0)
                    if raw_msg is None:
                        break
                    if len(raw_msg) <= 4:
                        continue

                    msg_id = raw_msg[4]
                    if msg_id == ExtensionProtocol.MSG_EXTENDED:
                        payload_body = raw_msg[4:]
                        ext_sub_id = payload_body[1]

                        if ext_sub_id == ExtensionProtocol.HANDSHAKE_EXT_ID:
                            peer_ut_meta_id, meta_size = ExtensionProtocol.parse_extension_handshake(payload_body)
                            if peer_ut_meta_id is not None and meta_size is not None and meta_size > 0:
                                assembler = MetadataAssembler(magnet_data.info_hash, meta_size)
                                for p_idx in assembler.get_missing_pieces():
                                    req = ExtensionProtocol.create_metadata_request(peer_ut_meta_id, p_idx)
                                    await conn.send_message(req)

                        elif ext_sub_id == ExtensionProtocol.LOCAL_UT_METADATA_ID and assembler is not None:
                            parsed_meta = ExtensionProtocol.parse_metadata_message(payload_body)
                            if parsed_meta is not None:
                                m_type, p_idx, chunk = parsed_meta
                                if m_type == ExtensionProtocol.META_DATA:
                                    assembler.add_piece(p_idx, chunk)
                                    if assembler.is_complete():
                                        verified_info = assembler.assemble_and_verify()
                                        if verified_info is not None:
                                            print(f"{Fore.GREEN}[+] Metadata fetched and verified via ut_metadata!{Style.RESET_ALL}")
                                            await conn.close()
                                            result_meta = {"info": verified_info}
                                            if magnet_data.trackers:
                                                result_meta["announce"] = magnet_data.trackers[0]
                                                result_meta["announce-list"] = [[t] for t in magnet_data.trackers]
                                            return result_meta
            except Exception:
                pass
            finally:
                await conn.close()

        return None

    def _spawn_peer_worker_if_new(
        self,
        ip: str,
        port: int,
        raw_info_hash: bytes,
        my_peer_id: bytes,
        manager: PieceManager,
        max_peers: int
    ):
        peer_addr = (ip, port)
        if peer_addr in self.known_peers:
            return
        if len(self.known_peers) >= max_peers:
            return

        self.known_peers.add(peer_addr)
        task = asyncio.create_task(
            self._peer_worker(
                ip=ip,
                port=port,
                raw_info_hash=raw_info_hash,
                my_peer_id=my_peer_id,
                manager=manager,
                max_peers=max_peers
            )
        )
        self.worker_tasks.append(task)

    async def _peer_worker(
        self,
        ip: str,
        port: int,
        raw_info_hash: bytes,
        my_peer_id: bytes,
        manager: PieceManager,
        max_peers: int = 25,
        pipeline_depth: int = 4
    ):
        peer_tag = f"{ip}:{port}"
        peer_conn = AsyncPeerConnection(ip, port, raw_info_hash, my_peer_id, timeout=5.0)

        connected = await peer_conn.connect_and_handshake()
        if not connected:
            return

        self.active_connections[peer_tag] = peer_conn
        manager.register_peer(peer_tag)
        print(f"{Fore.GREEN}[+] Worker active for peer {peer_tag}{Style.RESET_ALL}")

        try:
            if peer_conn.supports_extensions:
                ext_hs = ExtensionProtocol.create_extension_handshake()
                await peer_conn.send_message(ext_hs)

            await peer_conn.send_message(TorrentMessage.create_interested())

            while not all(manager.have_pieces):
                if not peer_conn.is_choked:
                    for _ in range(pipeline_depth):
                        req_packet = manager.get_next_request_for_peer(peer_tag)
                        if req_packet is not None:
                            sent = await peer_conn.send_message(req_packet)
                            if not sent:
                                break
                        else:
                            break

                try:
                    read_coro = peer_conn.read_message()
                    raw_msg = await asyncio.wait_for(read_coro, timeout=3.0)
                except asyncio.TimeoutError:
                    await peer_conn.send_message(TorrentMessage.create_keep_alive())
                    continue

                if raw_msg is None:
                    break

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
                    cancel_tasks = manager.handle_message(raw_msg, source_peer_id=peer_tag)
                    for target_peer, cancel_pkt in cancel_tasks:
                        target_conn = self.active_connections.get(target_peer)
                        if target_conn is not None:
                            await target_conn.send_message(cancel_pkt)

                elif msg_id == ExtensionProtocol.MSG_EXTENDED:
                    payload_body = raw_msg[4:]
                    if len(payload_body) >= 2:
                        ext_sub_id = payload_body[1]
                        if ext_sub_id == ExtensionProtocol.LOCAL_UT_PEX_ID:
                            added_peers, _ = PeerExchangeProtocol.parse_pex_message(payload_body)
                            for new_ip, new_port in added_peers:
                                self._spawn_peer_worker_if_new(
                                    ip=new_ip,
                                    port=new_port,
                                    raw_info_hash=raw_info_hash,
                                    my_peer_id=my_peer_id,
                                    manager=manager,
                                    max_peers=max_peers
                                )

        except Exception as err:
            print(f"{Fore.RED}[!] Peer worker error ({peer_tag}): {err}{Style.RESET_ALL}")
        finally:
            self.active_connections.pop(peer_tag, None)
            manager.unregister_peer(peer_tag)
            await peer_conn.close()

    async def start_async_download(
        self,
        raw_info_hash: bytes,
        my_peer_id: bytes,
        max_peers: int = 25
    ):
        mode_label = "Multi-File" if len(self.file_entries) > 0 else "Single-File"
        print(f"\n{Fore.YELLOW}[*] Launching Async Engine ({mode_label}) for '{self.target_filename}'...{Style.RESET_ALL}")
        print(f"[*] Total Bytes: {self.total_length} | Total Pieces: {self.num_pieces}")

        manager = PieceManager(
            filename=self.target_filename,
            piece_length=self.piece_length,
            num_pieces=self.num_pieces,
            total_length=self.total_length,
            file_entries=self.file_entries
        )
        manager.writer.piece_hashes = self.piece_hashes

        tracker_url = self.metadata.get(b"announce") or self.metadata.get("announce")
        if isinstance(tracker_url, bytes):
            tracker_url = tracker_url.decode("utf-8", errors="ignore")

        discovered_peers: List[Tuple[str, int]] = []
        if tracker_url:
            tracker = TrackerClient(raw_info_hash, my_peer_id)
            announce_data = tracker.announce(tracker_url, left=self.total_length)
            discovered_peers = announce_data.get("peers", [])

        # Supplement peer pool with Kademlia DHT lookup if enabled
        if self.enable_dht and len(discovered_peers) < max_peers:
            print(f"{Fore.CYAN}[*] Searching Kademlia DHT for additional swarm peers...{Style.RESET_ALL}")
            dht_crawler = DHTCrawler(local_id=my_peer_id)
            dht_peers = await asyncio.to_thread(
                dht_crawler.discover_peers_sync,
                raw_info_hash,
                None,
                2,
                2.0
            )
            for p in dht_peers:
                if p not in discovered_peers:
                    discovered_peers.append(p)

        if not discovered_peers:
            print(f"{Fore.YELLOW}[*] No external peers found. Setting local swarm test entry (127.0.0.1:6881)...{Style.RESET_ALL}")
            discovered_peers = [("127.0.0.1", 6881)]

        self.known_peers.clear()
        self.worker_tasks.clear()

        for peer_ip, peer_port in discovered_peers[:max_peers]:
            self._spawn_peer_worker_if_new(
                ip=peer_ip,
                port=peer_port,
                raw_info_hash=raw_info_hash,
                my_peer_id=my_peer_id,
                manager=manager,
                max_peers=max_peers
            )

        while not all(manager.have_pieces):
            all_done = True
            for t in list(self.worker_tasks):
                if not t.done():
                    all_done = False
                    break

            if all_done:
                print(f"{Fore.RED}[-] All active workers finished or disconnected.{Style.RESET_ALL}")
                break

            await asyncio.sleep(1.0)
            status_tag = " [END-GAME]" if manager.is_endgame_active() else ""
            print(f"{Fore.CYAN}[*] Download Progress{status_tag} (Swarm: {len(self.known_peers)} peers): {manager.status_report()}{Style.RESET_ALL}")

        for t in self.worker_tasks:
            if not t.done():
                t.cancel()

        print(f"\n{Fore.GREEN}=== DOWNLOAD SESSION COMPLETED ==={Style.RESET_ALL}")
        print(f"Status: {manager.status_report()}")
        print(f"Output Path: {manager.writer.final_path.resolve()}")

    def start_download_loop(self, raw_info_hash: bytes, my_peer_id: bytes, max_peers: int = 25):
        asyncio.run(
            self.start_async_download(
                raw_info_hash=raw_info_hash,
                my_peer_id=my_peer_id,
                max_peers=max_peers
            )
        )