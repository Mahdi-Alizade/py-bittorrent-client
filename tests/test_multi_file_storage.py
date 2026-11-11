from pathlib import Path
from core.multi_file_storage import MultiFileStorageManager


def test_multi_file_initialization_and_preallocation(tmp_path):
    file_entries = [
        {"length": 100, "path": ["subfolder", "file_a.txt"]},
        {"length": 250, "path": ["subfolder", "nested", "file_b.bin"]},
    ]

    manager = MultiFileStorageManager(base_directory=tmp_path, file_entries=file_entries)
    assert manager.total_length == 350

    manager.initialize_storage()

    file_a = tmp_path / "subfolder" / "file_a.txt"
    file_b = tmp_path / "subfolder" / "nested" / "file_b.bin"

    assert file_a.exists()
    assert file_a.stat().st_size == 100
    assert file_b.exists()
    assert file_b.stat().st_size == 250


def test_write_and_read_across_file_boundary(tmp_path):
    # Two files of 10 bytes each (Total 20 bytes)
    file_entries = [
        {"length": 10, "path": ["doc1.txt"]},
        {"length": 10, "path": ["doc2.txt"]},
    ]

    manager = MultiFileStorageManager(base_directory=tmp_path, file_entries=file_entries)
    manager.initialize_storage()

    # Write a 12-byte piece starting at global offset 4 (spans 6 bytes into doc1 and 6 bytes into doc2)
    sample_payload = b"ABCDEF123456"
    success = manager.write_piece(global_offset=4, piece_bytes=sample_payload)
    assert success is True

    # Check contents inside individual files
    doc1 = tmp_path / "doc1.txt"
    doc2 = tmp_path / "doc2.txt"

    # doc1: 4 zeros followed by 'ABCDEF'
    assert doc1.read_bytes() == b"\x00" * 4 + b"ABCDEF"
    # doc2: '123456' followed by 4 zeros
    assert doc2.read_bytes() == b"123456" + b"\x00" * 4

    # Verify reading back the entire continuous piece
    read_back = manager.read_piece(global_offset=4, piece_length=12)
    assert read_back == sample_payload