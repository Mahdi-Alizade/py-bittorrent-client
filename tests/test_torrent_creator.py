import hashlib
import sys
from unittest.mock import patch
from core.extension_protocol import ExtensionProtocol
from core.magnet_parser import MagnetURIParser
from core.parser import BDecoder
from core.torrent_creator import TorrentCreator
from main import main


def _extract_raw_info_slice(torrent_bytes: bytes) -> bytes:
    marker = b"4:info"
    pos = torrent_bytes.find(marker)
    assert pos != -1
    info_start = pos + len(marker)
    dict_len = ExtensionProtocol._find_bencoded_dict_end(torrent_bytes[info_start:])
    assert dict_len != -1
    return torrent_bytes[info_start:info_start + dict_len]


def test_create_single_file_torrent_and_magnet(tmp_path):
    source_file = tmp_path / "linux_distro.iso"
    payload = b"X" * 40000
    source_file.write_bytes(payload)

    output_torrent = tmp_path / "out" / "linux_distro.torrent"
    trackers = ["udp://tracker.opentrackr.org:1337/announce", "http://tracker.local:8080/announce"]

    creator = TorrentCreator(
        source_path=str(source_file),
        trackers=trackers,
        piece_length=16384,
        comment="Test release"
    )
    saved_path, info_hash, magnet_uri = creator.save_torrent_file(str(output_torrent))

    assert saved_path.exists()
    raw_torrent_bytes = saved_path.read_bytes()
    decoded_meta = BDecoder(raw_torrent_bytes).decode()
    info = decoded_meta["info"]

    assert info["name"] == "linux_distro.iso"
    assert info["length"] == 40000
    assert info["piece length"] == 16384
    assert len(info["pieces"]) == 60

    raw_info_slice = _extract_raw_info_slice(raw_torrent_bytes)
    assert hashlib.sha1(raw_info_slice).digest() == info_hash

    parsed_magnet = MagnetURIParser.parse(magnet_uri)
    assert parsed_magnet.info_hash == info_hash
    assert parsed_magnet.display_name == "linux_distro.iso"
    assert parsed_magnet.trackers == trackers


def test_create_multi_file_torrent(tmp_path):
    bundle_dir = tmp_path / "game_assets"
    (bundle_dir / "textures").mkdir(parents=True)
    (bundle_dir / "readme.txt").write_bytes(b"Hello World" * 500)
    (bundle_dir / "textures" / "sky.png").write_bytes(b"\x89PNG" * 3000)

    output_torrent = tmp_path / "game_assets.torrent"
    creator = TorrentCreator(source_path=str(bundle_dir), piece_length=8192)
    saved_path, info_hash, _ = creator.save_torrent_file(str(output_torrent))

    raw_torrent_bytes = saved_path.read_bytes()
    decoded_meta = BDecoder(raw_torrent_bytes).decode()
    info = decoded_meta["info"]

    assert info["name"] == "game_assets"
    assert "files" in info
    assert len(info["files"]) == 2

    raw_info_slice = _extract_raw_info_slice(raw_torrent_bytes)
    assert hashlib.sha1(raw_info_slice).digest() == info_hash


def test_cli_create_torrent_flag(tmp_path):
    sample_file = tmp_path / "video.mp4"
    sample_file.write_bytes(b"V" * 20000)
    out_torrent = tmp_path / "video.torrent"

    test_args = [
        "main.py",
        "--create",
        str(sample_file),
        "--out",
        str(out_torrent),
        "--tracker",
        "http://tracker.example.org/announce",
        "--piece-size",
        "16"
    ]

    with patch.object(sys, "argv", test_args):
        main()

    assert out_torrent.exists()