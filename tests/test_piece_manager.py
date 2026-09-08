from unittest.mock import MagicMock, patch
from core.piece_manager import PieceManager
from core.protocol_messages import TorrentMessage


class TestPieceManager:
    @patch("core.piece_manager.DownloadSession")
    def test_piece_size_and_blocks_calculation(self, mock_session):
        # 2 pieces: piece 0 is 32KB (2 blocks of 16KB), piece 1 is 10KB (1 truncated block)
        total_length = 32768 + 10240
        pm = PieceManager("test.bin", piece_length=32768, num_pieces=2, total_length=total_length)

        assert pm.get_piece_size(0) == 32768
        assert pm.get_piece_size(1) == 10240

        blocks_p0 = pm.get_blocks_for_piece(0)
        assert len(blocks_p0) == 2
        assert blocks_p0[0] == (0, 16384)
        assert blocks_p0[1] == (16384, 16384)

        blocks_p1 = pm.get_blocks_for_piece(1)
        assert len(blocks_p1) == 1
        assert blocks_p1[0] == (0, 10240)

    @patch("core.piece_manager.DownloadSession")
    def test_get_next_request(self, mock_session):
        pm = PieceManager("test.bin", piece_length=16384, num_pieces=1, total_length=16384)
        req = pm.get_next_request(0)
        assert req is not None

        # Simulate receiving block
        block_msg = TorrentMessage.parse_piece(
            TorrentMessage.create_request(0, 0, 16384)  # placeholder layout
        )
        pm.received_blocks[(0, 0)] = b"x" * 16384
        pm.have_pieces[0] = True

        assert pm.get_next_request(0) is None