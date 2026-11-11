import enum
import time
from typing import Dict, List, Optional, Tuple


class BlockState(enum.Enum):
    PENDING = 0
    REQUESTED = 1
    COMPLETED = 2


class BlockRequestInfo:
    def __init__(self, piece_index: int, block_offset: int, block_length: int):
        self.piece_index = piece_index
        self.block_offset = block_offset
        self.block_length = block_length
        self.state = BlockState.PENDING
        self.requested_timestamp = 0.0

    def mark_requested(self):
        current_time = time.time()
        self.state = BlockState.REQUESTED
        self.requested_timestamp = current_time

    def mark_completed(self):
        self.state = BlockState.COMPLETED
        self.requested_timestamp = 0.0

    def reset(self):
        self.state = BlockState.PENDING
        self.requested_timestamp = 0.0


class PieceBlockTracker:
    """
    Manages block lifecycle for a specific piece to enable request pipelining.
    """

    def __init__(self, piece_index: int, piece_size: int, standard_block_size: int = 16384):
        self.piece_index = piece_index
        self.piece_size = piece_size
        self.standard_block_size = standard_block_size

        self.blocks: List[BlockRequestInfo] = []
        self._initialize_blocks()

    def _initialize_blocks(self):
        current_offset = 0
        while current_offset < self.piece_size:
            remaining_bytes = self.piece_size - current_offset
            if remaining_bytes > self.standard_block_size:
                length = self.standard_block_size
            else:
                length = remaining_bytes

            block_info = BlockRequestInfo(
                piece_index=self.piece_index,
                block_offset=current_offset,
                block_length=length
            )
            self.blocks.append(block_info)
            current_offset += length

    def get_next_pending_block(self) -> Optional[BlockRequestInfo]:
        for block in self.blocks:
            if block.state == BlockState.PENDING:
                return block
        return None

    def get_stale_requests(self, timeout_seconds: float = 15.0) -> List[BlockRequestInfo]:
        stale_list = []
        now = time.time()
        for block in self.blocks:
            if block.state == BlockState.REQUESTED:
                elapsed = now - block.requested_timestamp
                if elapsed > timeout_seconds:
                    stale_list.append(block)
        return stale_list

    def mark_block_received(self, offset: int) -> bool:
        for block in self.blocks:
            if block.block_offset == offset:
                block.mark_completed()
                return True
        return False

    def is_piece_complete(self) -> bool:
        for block in self.blocks:
            if block.state != BlockState.COMPLETED:
                return False
        return True