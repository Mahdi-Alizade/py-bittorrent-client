import hashlib
import pytest
from core.client_logic import BitTorrentClient
from core.parser import TorrentEncoder


@pytest.mark.asyncio
async def test_async_client_single_file_flow():
    piece_payload = b"Z" * 16384
    piece_hash = hashlib.sha1(piece_payload).digest()

    info_dict = {
        "name": "sample_async.bin",
        "piece length": 16384,
        "length": 16384,
        "pieces": piece_hash
    }

    metadata = {
        "announce": "http://127.0.0.1:0/announce",
        "info": info_dict
    }

    client = BitTorrentClient(metadata)

    assert client.target_filename == "sample_async.bin"
    assert client.total_length == 16384
    assert client.num_pieces == 1
    assert len(client.file_entries) == 0


@pytest.mark.asyncio
async def test_async_client_multi_file_metadata():
    piece_hash = hashlib.sha1(b"X" * 300).digest()

    info_dict = {
        "name": "release_bundle",
        "piece length": 300,
        "files": [
            {"length": 120, "path": ["readme.md"]},
            {"length": 180, "path": ["bin", "app.exe"]}
        ],
        "pieces": piece_hash
    }

    metadata = {
        "announce": "http://127.0.0.1:0/announce",
        "info": info_dict
    }

    client = BitTorrentClient(metadata)

    assert client.target_filename == "release_bundle"
    assert client.total_length == 300
    assert len(client.file_entries) == 2
    assert client.file_entries[1]["length"] == 180