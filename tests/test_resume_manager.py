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

    # Mismatched piece count must return None
    assert manager.load_state(expected_num_pieces=4) is None

    # Corrupted JSON must safely return None
    manager.state_file.write_text("{corrupted_json", encoding="utf-8")
    assert manager.load_state(expected_num_pieces=3) is None