import time
from core.block_picker import PieceBlockTracker, BlockState


def test_block_initialization_regular():
    # 32KB piece -> exactly two 16KB blocks
    tracker = PieceBlockTracker(piece_index=0, piece_size=32768, standard_block_size=16384)
    assert len(tracker.blocks) == 2
    assert tracker.blocks[0].block_offset == 0
    assert tracker.blocks[0].block_length == 16384
    assert tracker.blocks[1].block_offset == 16384
    assert tracker.blocks[1].block_length == 16384


def test_block_initialization_truncated():
    # 20KB piece -> one 16KB block and one 4KB block
    tracker = PieceBlockTracker(piece_index=1, piece_size=20480, standard_block_size=16384)
    assert len(tracker.blocks) == 2
    assert tracker.blocks[0].block_length == 16384
    assert tracker.blocks[1].block_length == 4096


def test_block_state_transitions():
    tracker = PieceBlockTracker(piece_index=0, piece_size=16384, standard_block_size=16384)
    
    first_block = tracker.get_next_pending_block()
    assert first_block is not None
    assert first_block.state == BlockState.PENDING
    
    first_block.mark_requested()
    assert first_block.state == BlockState.REQUESTED
    assert tracker.get_next_pending_block() is None
    
    success = tracker.mark_block_received(0)
    assert success is True
    assert tracker.is_piece_complete() is True


def test_stale_request_detection():
    tracker = PieceBlockTracker(piece_index=0, piece_size=16384, standard_block_size=16384)
    block = tracker.get_next_pending_block()
    block.mark_requested()
    block.requested_timestamp = time.time() - 20.0
    
    stale_blocks = tracker.get_stale_requests(timeout_seconds=10.0)
    assert len(stale_blocks) == 1
    assert stale_blocks[0].block_offset == 0