import struct
from core.protocol_messages import TorrentMessage


class TestTorrentMessage:
    def test_keep_alive_message(self):
        msg = TorrentMessage.create_keep_alive()
        assert msg == b"\x00\x00\x00\x00"

    def test_choke_and_unchoke_messages(self):
        choke = TorrentMessage.create_choke()
        assert choke == struct.pack('>IB', 1, TorrentMessage.MSG_CHOKE)

        unchoke = TorrentMessage.create_unchoke()
        assert unchoke == struct.pack('>IB', 1, TorrentMessage.MSG_UNCHOKE)

    def test_interested_and_not_interested_messages(self):
        interested = TorrentMessage.create_interested()
        assert interested == struct.pack('>IB', 1, TorrentMessage.MSG_INTERESTED)

        not_interested = TorrentMessage.create_not_interested()
        assert not_interested == struct.pack('>IB', 1, TorrentMessage.MSG_NOT_INTERESTED)

    def test_create_and_parse_have(self):
        piece_idx = 42
        msg = TorrentMessage.create_have(piece_idx)
        assert len(msg) == 9
        assert TorrentMessage.parse_have(msg) == piece_idx

    def test_create_bitfield(self):
        payload = b"\xff\x00\xaa"
        msg = TorrentMessage.create_bitfield(payload)
        assert msg[:4] == struct.pack('>I', 1 + len(payload))
        assert msg[4] == TorrentMessage.MSG_BITFIELD
        assert msg[5:] == payload

    def test_create_request_message(self):
        msg = TorrentMessage.create_request(piece_index=2, block_offset=16384, block_length=16384)
        assert len(msg) == 17
        length, msg_id, idx, offset, size = struct.unpack('>IBIII', msg)
        assert length == 13
        assert msg_id == TorrentMessage.MSG_REQUEST
        assert idx == 2
        assert offset == 16384
        assert size == 16384

    def test_create_cancel_message(self):
        msg = TorrentMessage.create_cancel(piece_index=2, block_offset=16384, block_length=16384)
        assert len(msg) == 17
        length, msg_id, idx, offset, size = struct.unpack('>IBIII', msg)
        assert length == 13
        assert msg_id == TorrentMessage.MSG_CANCEL
        assert idx == 2
        assert offset == 16384
        assert size == 16384

    def test_parse_piece_valid(self):
        block = b"hello bittorrent payload"
        header = struct.pack('>IBII', 9 + len(block), TorrentMessage.MSG_PIECE, 1, 0)
        full_msg = header + block

        parsed = TorrentMessage.parse_piece(full_msg)
        assert parsed is not None
        idx, offset, data = parsed
        assert idx == 1
        assert offset == 0
        assert data == block

    def test_parse_piece_invalid_id_or_length(self):
        assert TorrentMessage.parse_piece(b"\x00\x00\x00\x01\x00") is None
        assert TorrentMessage.parse_piece(b"\x00\x00\x00") is None