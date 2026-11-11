import random
from typing import Dict, List, Optional, Set


class RarestFirstSelector:
    """
    Tracks piece availability across all connected peers and selects
    the rarest pieces first to optimize swarm health and download speed.
    """

    def __init__(self, total_pieces: int):
        self.total_pieces = total_pieces
        
        # Tracks which peer has which pieces: {peer_id: set_of_piece_indices}
        self.peer_inventory: Dict[str, Set[int]] = {}
        
        # Availability count for each piece index: [count_p0, count_p1, ...]
        self.piece_frequency: List[int] = [0] * total_pieces
        
        # Local state: which pieces are already downloaded
        self.downloaded_pieces: Set[int] = set()
        
        # Pieces currently in flight (being requested)
        self.in_progress_pieces: Set[int] = set()

    def register_peer(self, peer_identifier: str):
        if peer_identifier not in self.peer_inventory:
            self.peer_inventory[peer_identifier] = set()

    def unregister_peer(self, peer_identifier: str):
        if peer_identifier in self.peer_inventory:
            owned_pieces = self.peer_inventory[peer_identifier]
            for piece_index in owned_pieces:
                if 0 <= piece_index < self.total_pieces:
                    if self.piece_frequency[piece_index] > 0:
                        self.piece_frequency[piece_index] -= 1
            del self.peer_inventory[peer_identifier]

    def record_peer_have(self, peer_identifier: str, piece_index: int):
        if not (0 <= piece_index < self.total_pieces):
            return

        if peer_identifier not in self.peer_inventory:
            self.register_peer(peer_identifier)

        if piece_index not in self.peer_inventory[peer_identifier]:
            self.peer_inventory[peer_identifier].add(piece_index)
            self.piece_frequency[piece_index] += 1

    def record_peer_bitfield(self, peer_identifier: str, bitfield_bytes: bytes):
        self.register_peer(peer_identifier)
        
        current_piece = 0
        for byte_val in bitfield_bytes:
            for bit_pos in range(7, -1, -1):
                if current_piece >= self.total_pieces:
                    break
                
                is_set = (byte_val >> bit_pos) & 1
                if is_set == 1:
                    self.record_peer_have(peer_identifier, current_piece)
                current_piece += 1

    def mark_piece_completed(self, piece_index: int):
        self.downloaded_pieces.add(piece_index)
        if piece_index in self.in_progress_pieces:
            self.in_progress_pieces.remove(piece_index)

    def mark_piece_failed(self, piece_index: int):
        if piece_index in self.in_progress_pieces:
            self.in_progress_pieces.remove(piece_index)

    def pick_next_piece(self, peer_identifier: str) -> Optional[int]:
        """
        Picks the best piece to request from a specific peer:
        - Must be owned by this peer
        - Must NOT be already downloaded
        - Must NOT be currently in progress
        - Among valid candidates, pick the one with lowest availability frequency (Rarest-First)
        """
        if peer_identifier not in self.peer_inventory:
            return None

        peer_pieces = self.peer_inventory[peer_identifier]
        candidates = []

        for p_idx in peer_pieces:
            if p_idx in self.downloaded_pieces:
                continue
            if p_idx in self.in_progress_pieces:
                continue
            candidates.append(p_idx)

        if not candidates:
            return None

        # Sort candidates primarily by lowest frequency, with a small random shuffle
        # for pieces having the exact same rarity to avoid peer lockstep
        random.shuffle(candidates)
        candidates.sort(key=lambda idx: self.piece_frequency[idx])

        chosen_piece = candidates[0]
        self.in_progress_pieces.add(chosen_piece)
        return chosen_piece