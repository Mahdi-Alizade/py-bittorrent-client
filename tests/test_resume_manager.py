import hashlib
import struct
from core.piece_manager import PieceManager
from core.protocol_messages import TorrentMessage
from core.resume_manager import ResumeStateManager


def test_save_and_load_resume_state(tmp_path):
    info_hash_hex = "abcdef1234567890abcdef1234567890abcdef12"
    manager = ResumeStateManager(info_hash_hex=info_hash_hex, state_dir=str(tmp_path))

    have_list = [True, False, True, True, False]
    saved = manager.save_state(filename="ubuntu.iso", num_pieces=5, have_pieces=have_list)
    assert saved is True

    restored = manager.load_state(expected_num_pieces=5)
    assert restored == have_list


def test_corrupted_or_mismatched_resume_returns_none(tmp_path):
    info_hash_hex = "1111111111111111111111111111111111111111"
    manager = ResumeStateManager(info_hash_hex=info_hash_hex, state_dir=str(tmp_path))

    manager.save_state(filename="test.bin", num_pieces=3, have_pieces=[True, False, True])

    assert manager.load_state(expected_num_pieces=4) is None

    manager.state_file.write_text("{corrupted_json", encoding="utf-8")
    assert manager.load_state(expected_num_pieces=3) is None


def test_piece_manager_fast_resume_integration(tmp_path):
    info_hash_hex = "9999999999999999999999999999999999999999"
    p0_data = b"A" * 16384
    p1_data = b"B" * 16384
    h0 = hashlib.sha1(p0_data).digest()
    h1 = hashlib.sha1(p1_data).digest()

    # Session 1: complete piece 0 only
    pm1 = PieceManager(
        filename="resume_file.bin",
        piece_length=16384,
        num_pieces=2,
        total_length=32768,
        info_hash_hex=info_hash_hex,
        resume_dir=str(tmp_path)
    )
    pm1.writer.output_dir = tmp_path
    pm1.writer.final_path = tmp_path / "resume_file.bin"
    pm1.writer.initialize_file()
    pm1.writer.piece_hashes = [h0, h1]

    piece_0_msg = struct.pack(">IBII", 9 + 16384, TorrentMessage.MSG_PIECE, 0, 0) + p0_data
    pm1.handle_message(piece_0_msg)
    assert pm1.have_pieces == [True, False]

    # Session 2: initialize new PieceManager with same info_hash -> should auto-restore piece 0
    pm2 = PieceManager(
        filename="resume_file.bin",
        piece_length=16384,
        num_pieces=2,
        total_length=32768,
        info_hash_hex=info_hash_hex,
        resume_dir=str(tmp_path)
    )
    assert pm2.have_pieces == [True, False]
    assert 0 in pm2.selector.downloaded_pieces