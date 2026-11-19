import hashlib
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest

from core.peer_guard import PeerGuard
from core.piece_manager import PieceManager
from core.webseed_client import WebSeedClient


def test_peer_guard_cidr_and_anti_poisoning_ban():
    guard = PeerGuard()
    guard.add_cidr_block("192.168.100.0/24")

    assert guard.is_ip_allowed("192.168.100.45") is False
    assert guard.is_ip_allowed("10.0.0.5") is True

    # First corrupt strike does not ban yet
    banned_first = guard.record_corrupt_data("203.0.113.99")
    assert banned_first is False
    assert guard.is_ip_allowed("203.0.113.99") is True

    # Second corrupt strike triggers automatic ban
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