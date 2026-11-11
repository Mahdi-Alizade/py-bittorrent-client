from unittest.mock import patch
from core.piece_manager import PieceManager
from core.protocol_messages import TorrentMessage


class TestPieceManager:
    @patch("core.piece_manager.DownloadSession")
    def test_initialization_and_sizes(self, mock_session):
        total_len = 32768 + 10240
        pm = PieceManager("test.bin", piece_length=32768, num_pieces=2, total_length=total_len)

        assert pm.get_piece_size(0) == 32768
        assert pm.get_piece_size(1) == 10240
        assert len(pm.trackers) == 2

    @patch("core.piece_manager.DownloadSession")
    def test_rarest_first_block_request_generation(self, mock_session):
        pm = PieceManager("sample.bin", piece_length=16384, num_pieces=2, total_length=32768)

        peer_name = "peer_test_1"
        pm.register_peer(peer_name)
        pm.handle_peer_have(peer_name, 1)

        # Peer only has piece 1, so it must generate request for piece 1
        req_bytes = pm.get_next_request_for_peer(peer_name)
        assert req_bytes is not None

        # Request header format: [4-byte len][1-byte id=6][4-byte index][4-byte offset][4-byte length]
        assert req_bytes[4] == TorrentMessage.MSG_REQUEST
        piece_idx = int.from_bytes(req_bytes[5:9], "big")
        assert piece_idx == 1

    @patch("core.piece_manager.DownloadSession")
    def test_status_report(self, mock_session):
        pm = PieceManager("sample.bin", piece_length=16384, num_pieces=4, total_length=65536)
        pm.have_pieces[0] = True
        pm.have_pieces[1] = True
        report = pm.status_report()
        assert "2/4 (50.0%)" in report