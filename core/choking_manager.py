import random
import time
from typing import Dict, List, Optional, Set


class PeerTrafficStats:
    def __init__(self, peer_id: str):
        self.peer_id = peer_id
        self.bytes_downloaded_from = 0
        self.bytes_uploaded_to = 0
        self.is_interested_in_us = False
        self.am_choking_peer = True
        self.last_reset_time = time.time()

    def record_download(self, num_bytes: int):
        self.bytes_downloaded_from += num_bytes

    def record_upload(self, num_bytes: int):
        self.bytes_uploaded_to += num_bytes

    def get_download_rate(self) -> float:
        elapsed = max(0.1, time.time() - self.last_reset_time)
        return self.bytes_downloaded_from / elapsed

    def get_upload_rate(self) -> float:
        elapsed = max(0.1, time.time() - self.last_reset_time)
        return self.bytes_uploaded_to / elapsed

    def reset_window(self):
        self.bytes_downloaded_from = 0
        self.bytes_uploaded_to = 0
        self.last_reset_time = time.time()


class TitForTatChoker:
    """
    Implements BitTorrent's Tit-for-Tat choking strategy with Optimistic Unchoking.
    Unchokes top N peers providing highest download throughput, plus 1 random peer
    every 30 seconds to discover faster swarm neighbors.
    """

    def __init__(self, max_unchoked_slots: int = 4):
        self.max_unchoked_slots = max_unchoked_slots
        self.peer_stats: Dict[str, PeerTrafficStats] = {}
        self.optimistic_peer_id: Optional[str] = None
        self.last_optimistic_rotation = 0.0

    def register_peer(self, peer_id: str):
        if peer_id not in self.peer_stats:
            self.peer_stats[peer_id] = PeerTrafficStats(peer_id)

    def unregister_peer(self, peer_id: str):
        self.peer_stats.pop(peer_id, None)
        if self.optimistic_peer_id == peer_id:
            self.optimistic_peer_id = None

    def set_peer_interested(self, peer_id: str, interested: bool):
        if peer_id in self.peer_stats:
            self.peer_stats[peer_id].is_interested_in_us = interested

    def record_bytes_from_peer(self, peer_id: str, byte_count: int):
        if peer_id in self.peer_stats:
            self.peer_stats[peer_id].record_download(byte_count)

    def record_bytes_to_peer(self, peer_id: str, byte_count: int):
        if peer_id in self.peer_stats:
            self.peer_stats[peer_id].record_upload(byte_count)

    def evaluate_choke_decisions(self, is_seeding_mode: bool = False) -> Dict[str, bool]:
        """
        Recalculates which peers should be unchoked (False) vs choked (True).
        Returns {peer_id: should_be_choked}.
        """
        now = time.time()
        interested_peers: List[PeerTrafficStats] = []

        for stats in self.peer_stats.values():
            if stats.is_interested_in_us:
                interested_peers.append(stats)

        # Sort candidates: if seeding, prioritize peers we uploaded fastest to;
        # if leeching, prioritize peers we downloaded fastest from (Tit-for-Tat).
        if is_seeding_mode:
            interested_peers.sort(key=lambda s: s.get_upload_rate(), reverse=True)
        else:
            interested_peers.sort(key=lambda s: s.get_download_rate(), reverse=True)

        regular_slots = max(1, self.max_unchoked_slots - 1)
        selected_unchoked: Set[str] = set()

        for stats in interested_peers[:regular_slots]:
            selected_unchoked.add(stats.peer_id)

        # Rotate optimistic unchoke peer every 30 seconds
        if (now - self.last_optimistic_rotation) >= 30.0 or self.optimistic_peer_id not in self.peer_stats:
            choked_candidates = [
                s.peer_id for s in interested_peers if s.peer_id not in selected_unchoked
            ]
            if choked_candidates:
                self.optimistic_peer_id = random.choice(choked_candidates)
            else:
                self.optimistic_peer_id = None
            self.last_optimistic_rotation = now

        if self.optimistic_peer_id is not None:
            selected_unchoked.add(self.optimistic_peer_id)

        decisions: Dict[str, bool] = {}
        for p_id, stats in self.peer_stats.items():
            should_choke = p_id not in selected_unchoked
            stats.am_choking_peer = should_choke
            decisions[p_id] = should_choke
            stats.reset_window()

        return decisions