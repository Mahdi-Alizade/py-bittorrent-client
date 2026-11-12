from typing import Dict, List, Optional, Tuple
from colorama import Fore, Style, init

from core.block_picker import BlockState, PieceBlockTracker
from core.piece_selector import RarestFirstSelector
from core.protocol_messages import TorrentMessage
from core.reassemble import DownloadSession

init(autoreset=True)


class PieceManager:
    """
    Coordinates piece downloading, block pipelining, rarest-first selection,
    and End-Game Mode cancellation broadcasts.
    """

    def __init__(
        self,
        filename: str,
        piece_length: int,
        num_pieces: int,
        total_length: Optional[int] = None,
        file_entries: Optional[List[Dict]] = None
    ):
        self.filename = filename
        self.piece_length = piece_length
        self.num_pieces = num_pieces

        if total_length is not None:
            self.total_length = total_length
        else:
            self.total_length = piece_length * num_pieces

        self.block_size = 16 * 1024

        # Rarest-first selector
        self.selector = RarestFirstSelector(total_pieces=num_pieces)

        # Per-piece block trackers
        self.trackers: Dict[int, PieceBlockTracker] = {}
        self._initialize_trackers()

        # Storage writer session
        self.writer = DownloadSession(
            filename=filename,
            piece_length=piece_length,
            total_length=self.total_length,
            file_entries=file_entries
        )
        self.writer.initialize_file()

        # Tracking completed status
        self.have_pieces: List[bool] = [False] * num_pieces

        # End-Game Mode tracking: {(piece_idx, offset): [peer_id_1, peer_id_2, ...]}
        self.endgame_requests: Dict[Tuple[int, int], List[str]] = {}

    def _initialize_trackers(self):
        for piece_idx in range(self.num_pieces):
            piece_size = self.get_piece_size(piece_idx)
            tracker = PieceBlockTracker(
                piece_index=piece_idx,
                piece_size=piece_size,
                standard_block_size=self.block_size
            )
            self.trackers[piece_idx] = tracker

    def get_piece_size(self, piece_idx: int) -> int:
        if piece_idx < self.num_pieces - 1:
            return self.piece_length

        remainder = self.total_length % self.piece_length
        if remainder > 0:
            return remainder
        return self.piece_length

    def register_peer(self, peer_id: str):
        self.selector.register_peer(peer_id)

    def unregister_peer(self, peer_id: str):
        self.selector.unregister_peer(peer_id)
        for key in list(self.endgame_requests.keys()):
            if peer_id in self.endgame_requests[key]:
                self.endgame_requests[key].remove(peer_id)

    def handle_peer_have(self, peer_id: str, piece_idx: int):
        self.selector.record_peer_have(peer_id, piece_idx)

    def handle_peer_bitfield(self, peer_id: str, bitfield_bytes: bytes):
        self.selector.record_peer_bitfield(peer_id, bitfield_bytes)

    def is_endgame_active(self) -> bool:
        """
        Determines if client should enter End-Game mode (when >= 90% pieces are done
        or <= 2 pieces remain incomplete).
        """
        if self.num_pieces <= 1:
            return False

        completed = sum(1 for status in self.have_pieces if status)
        remaining = self.num_pieces - completed

        if remaining == 0:
            return False

        ratio = completed / self.num_pieces
        if ratio >= 0.90 or remaining <= 2:
            return True
        return False

    def handle_message(self, raw_data: bytes, source_peer_id: Optional[str] = None) -> List[Tuple[str, bytes]]:
        """
        Processes incoming messages and returns a list of (target_peer_id, cancel_packet)
        if an End-Game block was fulfilled and other peers need to be cancelled.
        """
        cancel_notifications: List[Tuple[str, bytes]] = []

        if len(raw_data) < 5:
            return cancel_notifications

        msg_id = raw_data[4]

        if msg_id == TorrentMessage.MSG_PIECE:
            parsed = TorrentMessage.parse_piece(raw_data)
            if parsed is not None:
                piece_idx, offset, block_data = parsed
                self._store_block(piece_idx, offset, block_data)

                # Generate CANCEL messages for duplicate endgame requests
                block_key = (piece_idx, offset)
                if block_key in self.endgame_requests:
                    peers_to_cancel = self.endgame_requests.pop(block_key)
                    cancel_pkt = TorrentMessage.create_cancel(piece_idx, offset, len(block_data))
                    for target_peer in peers_to_cancel:
                        if target_peer != source_peer_id:
                            cancel_notifications.append((target_peer, cancel_pkt))

        return cancel_notifications

    def _store_block(self, piece_idx: int, offset: int, block_data: bytes):
        if piece_idx not in self.trackers:
            return

        tracker = self.trackers[piece_idx]
        marked = tracker.mark_block_received(offset)

        if marked:
            self.writer.receive_block(piece_idx, offset, block_data)

        if tracker.is_piece_complete():
            is_valid = self.writer.verify_and_save_piece(piece_idx)
            if is_valid:
                self.have_pieces[piece_idx] = True
                self.selector.mark_piece_completed(piece_idx)
                print(f"{Fore.GREEN}[+] SUCCESS: Piece #{piece_idx} validated and saved.{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}[-] Piece #{piece_idx} verification failed. Resetting blocks.{Style.RESET_ALL}")
                for b in tracker.blocks:
                    b.reset()
                self.selector.mark_piece_failed(piece_idx)

    def get_next_request_for_peer(self, peer_id: str) -> Optional[bytes]:
        # Check if End-Game mode applies
        if self.is_endgame_active():
            endgame_pkt = self._get_endgame_request(peer_id)
            if endgame_pkt is not None:
                return endgame_pkt

        # First priority: complete pieces already in progress
        for piece_idx in list(self.selector.in_progress_pieces):
            if piece_idx in self.selector.peer_inventory.get(peer_id, set()):
                tracker = self.trackers[piece_idx]
                block = tracker.get_next_pending_block()
                if block is not None:
                    block.mark_requested()
                    return TorrentMessage.create_request(piece_idx, block.block_offset, block.block_length)

        # Second priority: pick a new rarest piece
        chosen_piece = self.selector.pick_next_piece(peer_id)
        if chosen_piece is not None:
            tracker = self.trackers[chosen_piece]
            block = tracker.get_next_pending_block()
            if block is not None:
                block.mark_requested()
                return TorrentMessage.create_request(chosen_piece, block.block_offset, block.block_length)

        return None

    def _get_endgame_request(self, peer_id: str) -> Optional[bytes]:
        """Broadcasts requests for any uncompleted block across all capable peers."""
        peer_owned = self.selector.peer_inventory.get(peer_id, set())

        for piece_idx in range(self.num_pieces):
            if self.have_pieces[piece_idx]:
                continue
            if piece_idx not in peer_owned:
                continue

            tracker = self.trackers[piece_idx]
            for block in tracker.blocks:
                if block.state != BlockState.COMPLETED:
                    block_key = (piece_idx, block.block_offset)
                    requested_peers = self.endgame_requests.setdefault(block_key, [])

                    if peer_id not in requested_peers:
                        requested_peers.append(peer_id)
                        block.mark_requested()
                        return TorrentMessage.create_request(
                            piece_idx,
                            block.block_offset,
                            block.block_length
                        )
        return None

    def status_report(self) -> str:
        completed_count = sum(1 for status in self.have_pieces if status)
        if self.num_pieces > 0:
            percentage = (completed_count / self.num_pieces) * 100.0
        else:
            percentage = 0.0
        return f"{completed_count}/{self.num_pieces} ({percentage:.1f}%)"