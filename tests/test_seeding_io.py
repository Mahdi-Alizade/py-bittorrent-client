import asyncio
import hashlib
import struct
import pytest
from core.client_logic import BitTorrentClient
from core.parser import TorrentEncoder
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

    assert pm.build_local_bitfield_message() is None

    pm.writer.receive_block(0, 0, piece_0_data)
    assert pm.writer.verify_and_save_piece(0) is True
    pm.have_pieces[0] = True

    bf_msg = pm.build_local_bitfield_message()
    assert bf_msg is not None
    assert bf_msg[4] == TorrentMessage.MSG_BITFIELD
    assert bf_msg[5] == 0x80

    served_pkt = pm.serve_block_request(piece_idx=0, offset=4096, length=4096)
    assert served_pkt is not None
    assert served_pkt[4] == TorrentMessage.MSG_PIECE

    p_idx, off = struct.unpack(">II", served_pkt[5:13])
    assert p_idx == 0
    assert off == 4096
    assert served_pkt[13:] == b"S" * 4096

    assert pm.serve_block_request(piece_idx=1, offset=0, length=4096) is None


@pytest.mark.asyncio
async def test_full_seeder_to_leecher_transfer(tmp_path):
    payload = b"K" * 16384
    piece_hash = hashlib.sha1(payload).digest()

    info_dict = {
        "name": "p2p_transfer.bin",
        "piece length": 16384,
        "length": 16384,
        "pieces": piece_hash
    }
    raw_info = TorrentEncoder.encode(info_dict)
    info_hash = hashlib.sha1(raw_info).digest()
    metadata = {"info": info_dict}

    # 1. Setup Seeder node with completed file on disk
    seeder_dir = tmp_path / "seeder"
    seeder_pm = PieceManager("p2p_transfer.bin", 16384, 1, total_length=16384)
    seeder_pm.writer.output_dir = seeder_dir
    seeder_pm.writer.final_path = seeder_dir / "p2p_transfer.bin"
    seeder_pm.writer.initialize_file()
    seeder_pm.writer.piece_hashes = [piece_hash]
    seeder_pm.writer.receive_block(0, 0, payload)
    assert seeder_pm.writer.verify_and_save_piece(0) is True
    seeder_pm.have_pieces[0] = True

    seeder_client = BitTorrentClient(metadata, enable_dht=False, listen_port=0)
    bound_port = await seeder_client.start_incoming_listener(
        raw_info_hash=info_hash,
        my_peer_id=b"-SEED01-111111111111",
        manager=seeder_pm,
        host="127.0.0.1",
        port=0
    )
    assert bound_port is not None

    # 2. Setup Leecher node with empty file on disk
    leecher_dir = tmp_path / "leecher"
    leecher_pm = PieceManager("p2p_transfer.bin", 16384, 1, total_length=16384)
    leecher_pm.writer.output_dir = leecher_dir
    leecher_pm.writer.final_path = leecher_dir / "p2p_transfer.bin"
    leecher_pm.writer.initialize_file()
    leecher_pm.writer.piece_hashes = [piece_hash]

    leecher_client = BitTorrentClient(metadata, enable_dht=False)
    leecher_client._spawn_peer_worker_if_new(
        ip="127.0.0.1",
        port=bound_port,
        raw_info_hash=info_hash,
        my_peer_id=b"-LEEC01-222222222222",
        manager=leecher_pm,
        max_peers=5
    )

    for _ in range(40):
        if all(leecher_pm.have_pieces):
            break
        await asyncio.sleep(0.05)

    assert all(leecher_pm.have_pieces) is True
    assert (leecher_dir / "p2p_transfer.bin").read_bytes() == payload

    for t in leecher_client.worker_tasks:
        if not t.done():
            t.cancel()
    await seeder_client.stop_incoming_listener()