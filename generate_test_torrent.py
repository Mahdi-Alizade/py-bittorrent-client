import hashlib
import os
from pathlib import Path
from core.parser import TorrentEncoder


def create_sample_torrent(
    target_file_path: Path,
    output_torrent_path: Path,
    announce_url: str = "http://127.0.0.1:6881/announce",
    piece_length: int = 16384
):
    target_file_path.parent.mkdir(parents=True, exist_ok=True)
    output_torrent_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Create a dummy test payload if not already present
    if not target_file_path.exists():
        sample_content = (b"BitTorrent Protocol Scratch Engine Test Data - Chunked Block Validation\n" * 500)
        target_file_path.write_bytes(sample_content)

    file_bytes = target_file_path.read_bytes()
    file_length = len(file_bytes)

    # 2. Slice file into piece_length segments and calculate SHA-1 for each piece
    pieces_hashes = bytearray()
    for offset in range(0, file_length, piece_length):
        chunk = file_bytes[offset:offset + piece_length]
        pieces_hashes.extend(hashlib.sha1(chunk).digest())

    # 3. Formulate standard BEP-3 metainfo dictionary
    metainfo = {
        "announce": announce_url,
        "info": {
            "name": target_file_path.name,
            "piece length": piece_length,
            "length": file_length,
            "pieces": bytes(pieces_hashes)
        }
    }

    # 4. Encode to Bencode format and save
    bencoded_data = TorrentEncoder.encode(metainfo)
    output_torrent_path.write_bytes(bencoded_data)
    print(f"[+] Successfully generated test torrent at: {output_torrent_path}")
    print(f"    File: {target_file_path.name} ({file_length} bytes)")
    print(f"    Pieces: {len(pieces_hashes) // 20} (Piece Length: {piece_length})")


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent
    data_dir = base_dir / "data"
    sample_file = data_dir / "sample.txt"
    sample_torrent = data_dir / "sample.txt.torrent"

    create_sample_torrent(sample_file, sample_torrent)