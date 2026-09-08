import hashlib
from pathlib import Path
from core.reassemble import DownloadSession


class TestDownloadSession:
    def test_initialize_and_save_piece(self, tmp_path):
        payload = b"A" * 16384
        piece_hash = hashlib.sha1(payload).digest()

        session = DownloadSession(
            filename="output.bin",
            piece_length=16384,
            total_length=16384,
            piece_hashes=[piece_hash],
            output_dir=str(tmp_path)
        )

        assert session.initialize_file() is True
        session.receive_block(0, 0, payload)
        assert session.verify_and_save_piece(0) is True

        saved_file = tmp_path / "output.bin"
        assert saved_file.exists()
        assert saved_file.read_bytes() == payload

    def test_corrupted_piece_rejected(self, tmp_path):
        payload = b"A" * 16384
        wrong_hash = hashlib.sha1(b"corrupted").digest()

        session = DownloadSession(
            filename="output_bad.bin",
            piece_length=16384,
            total_length=16384,
            piece_hashes=[wrong_hash],
            output_dir=str(tmp_path)
        )

        session.initialize_file()
        session.receive_block(0, 0, payload)
        # SHA1 mismatch should return False
        assert session.verify_and_save_piece(0) is False