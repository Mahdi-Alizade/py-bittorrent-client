import hashlib
import struct
from core.piece_manager import PieceManager
from core.protocol_messages import TorrentMessage


def test_local_bitfield_and_block_serving(tmp_path):
    piece_0_data = b"S" * 16384
    hash_0 = hashlib.sha1(piece_0_data).digest()
    hash_1 = hashlib.sha1(b"P" * 16384).digest()

    pm = PieceManager("seed_test.bin", piece_length=16384, num_pieces=2, total_length=32768)
    pm.writer.output_dir = tmp_path
    pm.writer.final_path = tmp_path / "seed_test.bin"
    pm.writer.initialize_file()
    pm.writer.piece_hashes = [hash_0, hash_1]

    # Initially no pieces completed -> bitfield is None
    assert pm.build_local_bitfield_message() is None

    # Store and verify piece 0
    pm.writer.receive_block(0, 0, piece_0_data)
    assert pm.writer.verify_and_save_piece(0) is True
    pm.have_pieces[0] = True

    # Now bitfield should have bit 7 (0x80) set for piece 0
    bf_msg = pm.build_local_bitfield_message()
    assert bf_msg is not None
    assert bf_msg[4] == TorrentMessage.MSG_BITFIELD
    assert bf_msg[5] == 0x80

    # Serve a 4096-byte slice at offset 4096 from piece 0
    served_pkt = pm.serve_block_request(piece_idx=0, offset=4096, length=4096)
    assert served_pkt is not None
    assert served_pkt[4] == TorrentMessage.MSG_PIECE

    p_idx, off = struct.unpack(">II", served_pkt[5:13])
    assert p_idx == 0
    assert off == 4096
    assert served_pkt[13:] == b"S" * 4096

    # Uncompleted piece 1 must not be served
    assert pm.serve_block_request(piece_idx=1, offset=0, length=4096) is None