import hashlib
from core.magnet_parser import MagnetURIParser
from core.parser import BDecoder, TorrentEncoder
from core.torrent_creator import TorrentCreator


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
    decoded_meta = BDecoder(saved_path.read_bytes()).decode()
    info = decoded_meta["info"]

    assert info["name"] == "linux_distro.iso"
    assert info["length"] == 40000
    assert info["piece length"] == 16384
    # 40000 bytes / 16384 = 3 pieces -> 60 bytes of SHA-1 hashes
    assert len(info["pieces"]) == 60

    # Verify info_hash matches re-encoded info dictionary
    recomputed_hash = hashlib.sha1(TorrentEncoder.encode(info)).digest()
    assert recomputed_hash == info_hash

    # Verify generated magnet URI parses cleanly back to identical info_hash and trackers
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

    decoded_meta = BDecoder(saved_path.read_bytes()).decode()
    info = decoded_meta["info"]

    assert info["name"] == "game_assets"
    assert "files" in info
    assert len(info["files"]) == 2
    assert hashlib.sha1(TorrentEncoder.encode(info)).digest() == info_hash