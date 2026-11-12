import struct
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

        req_bytes = pm.get_next_request_for_peer(peer_name)
        assert req_bytes is not None

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

    @patch("core.piece_manager.DownloadSession")
    def test_endgame_mode_broadcast_and_cancel(self, mock_session):
        # 10 pieces total, 9 completed -> 90% -> End-Game active
        pm = PieceManager("endgame.bin", piece_length=16384, num_pieces=10, total_length=163840)
        for idx in range(9):
            pm.have_pieces[idx] = True

        assert pm.is_endgame_active() is True

        pm.register_peer("peer_A")
        pm.register_peer("peer_B")
        pm.handle_peer_have("peer_A", 9)
        pm.handle_peer_have("peer_B", 9)

        # Both peers should receive request for piece 9, offset 0
        req_a = pm.get_next_request_for_peer("peer_A")
        req_b = pm.get_next_request_for_peer("peer_B")
        assert req_a is not None
        assert req_b is not None

        # Simulate peer_A fulfilling the block
        block_payload = b"X" * 16384
        piece_msg = struct.pack(">IBII", 9 + len(block_payload), TorrentMessage.MSG_PIECE, 9, 0) + block_payload

        cancel_list = pm.handle_message(piece_msg, source_peer_id="peer_A")

        # peer_B must receive a CANCEL message
        assert len(cancel_list) == 1
        target_peer, cancel_pkt = cancel_list[0]
        assert target_peer == "peer_B"
        assert cancel_pkt[4] == TorrentMessage.MSG_CANCEL