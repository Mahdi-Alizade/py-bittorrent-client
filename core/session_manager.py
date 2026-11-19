import asyncio
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from core.client_logic import BitTorrentClient
from core.extension_protocol import ExtensionProtocol
from core.lpd_service import LocalPeerDiscovery
from core.magnet_parser import MagnetURIParser
from core.parser import BDecoder, TorrentEncoder
from core.peer_guard import PeerGuard
from core.piece_manager import PieceManager


@dataclass
class ManagedTorrentSession:
    info_hash: bytes
    info_hash_hex: str
    name: str
    total_length: int
    num_pieces: int
    client: BitTorrentClient
    manager: PieceManager
    status: str = "downloading"
    task: Optional[asyncio.Task] = None
    error_message: Optional[str] = None
    trackers: List[str] = field(default_factory=list)


class MultiTorrentSessionManager:
    """
    Central orchestration engine managing multiple concurrent BitTorrent downloads
    and seeding sessions, unified Local Peer Discovery (BEP-0014), shared PeerGuard
    IP filtering, Hot Watch-Folder ingestion, and live telemetry.
    """

    def __init__(
        self,
        peer_id: bytes,
        listen_port: int = 6881,
        enable_dht: bool = True,
        enable_lpd: bool = True,
        max_peers_per_torrent: int = 25,
        watch_dir: Optional[str] = None,
        peer_guard: Optional[PeerGuard] = None
    ):
        self.peer_id = peer_id
        self.listen_port = listen_port
        self.enable_dht = enable_dht
        self.enable_lpd = enable_lpd
        self.max_peers_per_torrent = max_peers_per_torrent
        self.watch_dir = Path(watch_dir) if watch_dir else None
        self.peer_guard = peer_guard or PeerGuard()

        self.sessions: Dict[str, ManagedTorrentSession] = {}
        self.lpd = LocalPeerDiscovery(listen_port=listen_port)
        self.lpd.on_peer_discovered = self._handle_lpd_peer_found
        self._lpd_task: Optional[asyncio.Task] = None
        self._watch_task: Optional[asyncio.Task] = None
        self._ingested_watch_files: Set[str] = set()

    def start_background_services(self):
        if self.enable_lpd and self._lpd_task is None:
            try:
                self._lpd_task = asyncio.create_task(self.lpd.start_listener())
            except RuntimeError:
                pass

        if self.watch_dir is not None and self._watch_task is None:
            try:
                self._watch_task = asyncio.create_task(self._watch_folder_loop())
            except RuntimeError:
                pass

    def stop_background_services(self):
        self.lpd.stop()
        if self._lpd_task is not None and not self._lpd_task.done():
            self._lpd_task.cancel()
            self._lpd_task = None
        if self._watch_task is not None and not self._watch_task.done():
            self._watch_task.cancel()
            self._watch_task = None

    async def scan_watch_folder_once(self, auto_start: bool = True) -> int:
        """
        Scans watch_dir for new .torrent files and ingests them automatically.
        Returns the count of newly added torrents.
        """
        if self.watch_dir is None:
            return 0

        self.watch_dir.mkdir(parents=True, exist_ok=True)
        added_count = 0

        for file_path in sorted(self.watch_dir.glob("*.torrent")):
            key = str(file_path.resolve())
            if key in self._ingested_watch_files:
                continue
            try:
                await self.add_torrent_file(key, auto_start=auto_start)
                self._ingested_watch_files.add(key)
                added_count += 1
            except Exception:
                pass

        return added_count

    async def _watch_folder_loop(self, poll_interval: float = 2.0):
        try:
            while True:
                await self.scan_watch_folder_once(auto_start=True)
                await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            pass

    def _handle_lpd_peer_found(self, info_hash_hex: str, peer_ip: str, peer_port: int):
        session = self.sessions.get(info_hash_hex.lower())
        if session is None or session.status == "paused":
            return

        session.client._spawn_peer_worker_if_new(
            ip=peer_ip,
            port=peer_port,
            raw_info_hash=session.info_hash,
            my_peer_id=self.peer_id,
            manager=session.manager,
            max_peers=self.max_peers_per_torrent
        )

    @staticmethod
    def _extract_raw_info_hash(raw_torrent_bytes: bytes, fallback_info: dict) -> bytes:
        marker = b"4:info"
        pos = raw_torrent_bytes.find(marker)
        if pos != -1:
            info_start = pos + len(marker)
            dict_len = ExtensionProtocol._find_bencoded_dict_end(raw_torrent_bytes[info_start:])
            if dict_len != -1:
                return hashlib.sha1(raw_torrent_bytes[info_start:info_start + dict_len]).digest()
        return hashlib.sha1(TorrentEncoder.encode(fallback_info)).digest()

    async def add_torrent_from_metadata(
        self,
        metadata: dict,
        info_hash: bytes,
        auto_start: bool = True
    ) -> ManagedTorrentSession:
        hex_id = info_hash.hex().lower()
        if hex_id in self.sessions:
            return self.sessions[hex_id]

        client = BitTorrentClient(
            torrent_metadata=metadata,
            enable_dht=self.enable_dht,
            listen_port=self.listen_port,
            peer_guard=self.peer_guard
        )

        manager = PieceManager(
            filename=client.target_filename,
            piece_length=client.piece_length,
            num_pieces=client.num_pieces,
            total_length=client.total_length,
            file_entries=client.file_entries,
            info_hash_hex=hex_id
        )
        manager.writer.piece_hashes = client.piece_hashes

        trackers: List[str] = []
        ann = metadata.get(b"announce") or metadata.get("announce")
        if isinstance(ann, bytes):
            ann = ann.decode("utf-8", errors="ignore")
        if ann:
            trackers.append(ann)

        initial_status = "seeding" if all(manager.have_pieces) else "downloading"
        session = ManagedTorrentSession(
            info_hash=info_hash,
            info_hash_hex=hex_id,
            name=client.target_filename,
            total_length=client.total_length,
            num_pieces=client.num_pieces,
            client=client,
            manager=manager,
            status=initial_status,
            trackers=trackers
        )

        self.sessions[hex_id] = session
        self.lpd.register_info_hash(info_hash)

        if self.enable_lpd:
            self.lpd.broadcast_announce(info_hash)

        if auto_start:
            session.task = asyncio.create_task(self._run_managed_torrent(session))

        return session

    async def add_torrent_file(self, torrent_path: str, auto_start: bool = True) -> ManagedTorrentSession:
        file_obj = Path(torrent_path)
        if not file_obj.exists():
            raise FileNotFoundError(f"Torrent file not found: {torrent_path}")

        raw_bytes = file_obj.read_bytes()
        metadata = BDecoder(raw_bytes).decode()
        info = metadata.get(b"info") or metadata.get("info")
        if not info:
            raise ValueError("Invalid .torrent file: missing 'info' dictionary")

        info_hash = self._extract_raw_info_hash(raw_bytes, info)
        return await self.add_torrent_from_metadata(metadata, info_hash, auto_start=auto_start)

    async def add_magnet_uri(self, magnet_uri: str, auto_start: bool = True) -> ManagedTorrentSession:
        magnet_data = MagnetURIParser.parse(magnet_uri)
        metadata = await BitTorrentClient.fetch_metadata_from_magnet(
            magnet_data=magnet_data,
            my_peer_id=self.peer_id,
            use_dht=self.enable_dht
        )
        if not metadata:
            raise RuntimeError("Failed to resolve magnet metadata from swarm")

        return await self.add_torrent_from_metadata(
            metadata=metadata,
            info_hash=magnet_data.info_hash,
            auto_start=auto_start
        )

    async def _run_managed_torrent(self, session: ManagedTorrentSession):
        try:
            session.status = "seeding" if all(session.manager.have_pieces) else "downloading"
            await session.client.start_async_download(
                raw_info_hash=session.info_hash,
                my_peer_id=self.peer_id,
                max_peers=self.max_peers_per_torrent,
                seed_after_download=True
            )
            if all(session.manager.have_pieces):
                session.status = "completed"
        except asyncio.CancelledError:
            session.status = "paused"
        except Exception as exc:
            session.status = "error"
            session.error_message = str(exc)

    async def pause_torrent(self, info_hash_hex: str) -> bool:
        session = self.sessions.get(info_hash_hex.lower())
        if not session:
            return False

        if session.task and not session.task.done():
            session.task.cancel()
        for t in session.client.worker_tasks:
            if not t.done():
                t.cancel()
        await session.client.stop_incoming_listener()
        session.status = "paused"
        return True

    async def resume_torrent(self, info_hash_hex: str) -> bool:
        session = self.sessions.get(info_hash_hex.lower())
        if not session:
            return False

        if session.task is None or session.task.done():
            session.status = "seeding" if all(session.manager.have_pieces) else "downloading"
            session.task = asyncio.create_task(self._run_managed_torrent(session))
        return True

    def get_all_telemetry(self) -> List[dict]:
        snapshots: List[dict] = []
        for hex_id, session in self.sessions.items():
            completed = sum(1 for flag in session.manager.have_pieces if flag)
            progress_pct = round((completed / max(1, session.num_pieces)) * 100.0, 2)
            net = session.client.bandwidth_monitor.sample()

            snapshots.append({
                "info_hash": hex_id,
                "name": session.name,
                "status": session.status,
                "total_bytes": session.total_length,
                "completed_pieces": completed,
                "total_pieces": session.num_pieces,
                "progress_percent": progress_pct,
                "download_speed_bps": round(net["down_bps"], 1),
                "upload_speed_bps": round(net["up_bps"], 1),
                "eta_seconds": net["eta_seconds"],
                "connected_peers": len(session.client.active_connections),
                "known_swarm_peers": len(session.client.known_peers)
            })
        return snapshots