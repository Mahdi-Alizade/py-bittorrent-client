import asyncio
import hashlib
import struct
import pytest
from core.client_logic import BitTorrentClient
from core.parser import TorrentEncoder
from core.protocol_messages import TorrentMessage


@pytest.mark.asyncio
async def test_async_client_worker_flow(tmp_path):
    piece_payload = b"Z" * 16384
    piece_hash = hashlib.sha1(piece_payload).digest()

    info_dict = {
        "name": "sample_async.bin",
        "piece length": 16384,
        "length": 16384,
        "pieces": piece_hash
    }
    encoded_info = TorrentEncoder.encode(info_dict)
    info_hash = hashlib.sha1(encoded_info).digest()

    metadata = {
        "announce": "http://127.0.0.1:0/announce",
        "info": info_dict
    }

    client_id = b"-PY0001-112233445566"
    client = BitTorrentClient(metadata)

    # Verify attributes extracted
    assert client.target_filename == "sample_async.bin"
    assert client.total_length == 16384
    assert client.num_pieces == 1
    assert len(client.piece_hashes) == 1