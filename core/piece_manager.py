import math
import struct
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
    End-Game Mode cancellation broadcasts, and outbound block serving (Seeding).
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

        self.selector = RarestFirstSelector(total_pieces=num_pieces)

        self.trackers: Dict[int, PieceBlockTracker] = {}
        self._initialize_trackers()

        self.writer = DownloadSession(
            filename=filename,
            piece_length=piece_length,
            total_length=self.total_length,
            file_entries=file_entries
        )
        self.writer.initialize_file()

        self.have_pieces: List[bool] = [False] * num_pieces
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

    def build_local_bitfield_message(self) -> Optional[bytes]:
        """
        Builds a BEP-3 Bitfield wire message if we have at least one completed piece.
        """
        if not any(self.have_pieces):
            return None

        num_bytes = math.ceil(self.num_pieces / 8)
        bitfield_arr = bytearray(num_bytes)

        for idx, has_it in enumerate(self.have_pieces):
            if has_it:
                byte_index = idx // 8
                bit_offset = 7 - (idx % 8)
                bitfield_arr[byte_index] |= (1 << bit_offset)

        payload_len = 1 + len(bitfield_arr)
        header = struct.pack(">IB", payload_len, TorrentMessage.MSG_BITFIELD)
        return header + bytes(bitfield_arr)

    def serve_block_request(self, piece_idx: int, offset: int, length: int) -> Optional[bytes]:
        """
        Reads a block from a completed piece and formats a wire MSG_PIECE packet.
        """
        if not (0 <= piece_idx < self.num_pieces):
            return None
        if not self.have_pieces[piece_idx]:
            return None

        block_bytes = self.writer.read_block(piece_idx, offset, length)
        if block_bytes is None:
            return None

        msg_len = 9 + len(block_bytes)
        header = struct.pack(">IBII", msg_len, TorrentMessage.MSG_PIECE, piece_idx, offset)
        return header + block_bytes

    def is_endgame_active(self) -> bool:
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
        cancel_notifications: List[Tuple[str, bytes]] = []

        if len(raw_data) < 5:
            return cancel_notifications

        msg_id = raw_data[4]

        if msg_id == TorrentMessage.MSG_PIECE:
            parsed = TorrentMessage.parse_piece(raw_data)
            if parsed is not None:
                piece_idx, offset, block_data = parsed
                self._store_block(piece_idx, offset, block_data)

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
        if self.is_endgame_active():
            endgame_pkt = self._get_endgame_request(peer_id)
            if endgame_pkt is not None:
                return endgame_pkt

        for piece_idx in list(self.selector.in_progress_pieces):
            if piece_idx in self.selector.peer_inventory.get(peer_id, set()):
                tracker = self.trackers[piece_idx]
                block = tracker.get_next_pending_block()
                if block is not None:
                    block.mark_requested()
                    return TorrentMessage.create_request(piece_idx, block.block_offset, block.block_length)

        chosen_piece = self.selector.pick_next_piece(peer_id)
        if chosen_piece is not None:
            tracker = self.trackers[chosen_piece]
            block = tracker.get_next_pending_block()
            if block is not None:
                block.mark_requested()
                return TorrentMessage.create_request(chosen_piece, block.block_offset, block.block_length)

        return None

    def _get_endgame_request(self, peer_id: str) -> Optional[bytes]:
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