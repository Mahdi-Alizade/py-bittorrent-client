import hashlib
import struct
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest

from core.peer_guard import PeerGuard
from core.piece_manager import PieceManager
from core.protocol_messages import TorrentMessage
from core.session_manager import MultiTorrentSessionManager
from core.torrent_creator import TorrentCreator
from core.webseed_client import WebSeedClient


def test_peer_guard_cidr_and_anti_poisoning_ban():
    guard = PeerGuard()
    guard.add_cidr_block("192.168.100.0/24")

    assert guard.is_ip_allowed("192.168.100.45") is False
    assert guard.is_ip_allowed("10.0.0.5") is True

    banned_first = guard.record_corrupt_data("203.0.113.99")
    assert banned_first is False
    assert guard.is_ip_allowed("203.0.113.99") is True

    banned_second = guard.record_corrupt_data("203.0.113.99")
    assert banned_second is True
    assert guard.is_ip_allowed("203.0.113.99") is False


@pytest.mark.asyncio
async def test_webseed_bep19_http_range_download(tmp_path):
    full_file_content = b"W" * 16384 + b"Z" * 8192
    h0 = hashlib.sha1(b"W" * 16384).digest()
    h1 = hashlib.sha1(b"Z" * 8192).digest()

    class RangeHTTPHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            range_hdr = self.headers.get("Range", "")
            assert range_hdr.startswith("bytes=")
            start_s, end_s = range_hdr.replace("bytes=", "").split("-")
            start_i, end_i = int(start_s), int(end_s)
            slice_bytes = full_file_content[start_i:end_i + 1]

            self.send_response(206)
            self.send_header("Content-Length", str(len(slice_bytes)))
            self.end_headers()
            self.wfile.write(slice_bytes)

        def log_message(self, format, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), RangeHTTPHandler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    pm = PieceManager("webseed_iso.bin", piece_length=16384, num_pieces=2, total_length=len(full_file_content))
    pm.writer.output_dir = tmp_path
    pm.writer.final_path = tmp_path / "webseed_iso.bin"
    pm.writer.initialize_file()
    pm.writer.piece_hashes = [h0, h1]

    ws_client = WebSeedClient([f"http://127.0.0.1:{port}/files/"])
    ok0 = await ws_client.download_piece_from_webseed(pm, 0)
    ok1 = await ws_client.download_piece_from_webseed(pm, 1)

    assert ok0 is True
    assert ok1 is True
    assert all(pm.have_pieces) is True
    assert (tmp_path / "webseed_iso.bin").read_bytes() == full_file_content

    httpd.shutdown()


@pytest.mark.asyncio
async def test_watch_folder_and_corrupt_contributor_attribution(tmp_path):
    # 1. Verify PieceManager attributes corrupt pieces to the sending peer
    valid_hash = hashlib.sha1(b"V" * 16384).digest()
    pm = PieceManager("guard_test.bin", piece_length=16384, num_pieces=1, total_length=16384)
    pm.writer.output_dir = tmp_path
    pm.writer.final_path = tmp_path / "guard_test.bin"
    pm.writer.initialize_file()
    pm.writer.piece_hashes = [valid_hash]

    corrupt_pkt = struct.pack(">IBII", 9 + 16384, TorrentMessage.MSG_PIECE, 0, 0) + (b"X" * 16384)
    pm.handle_message(corrupt_pkt, source_peer_id="198.51.100.77:6881")
    assert pm.last_corrupt_peers == ["198.51.100.77:6881"]

    # 2. Verify Hot Watch-Folder automatically ingests dropped .torrent files
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    src_file = tmp_path / "auto_item.bin"
    src_file.write_bytes(b"M" * 16384)
    TorrentCreator(str(src_file), piece_length=16384).save_torrent_file(str(watch_dir / "auto_item.torrent"))

    session_mgr = MultiTorrentSessionManager(
        peer_id=b"-PY0001-111122223333",
        listen_port=0,
        enable_dht=False,
        enable_lpd=False,
        watch_dir=str(watch_dir)
    )
    ingested = await session_mgr.scan_watch_folder_once(auto_start=False)
    assert ingested == 1
    assert len(session_mgr.sessions) == 1