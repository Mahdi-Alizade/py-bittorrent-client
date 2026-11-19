import asyncio
import json
import pytest
from core.session_manager import MultiTorrentSessionManager
from core.torrent_creator import TorrentCreator
from core.web_dashboard import WebControlServer


async def _send_raw_http(port: int, method: str, path: str, json_body: dict = None) -> tuple[int, str]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    body_bytes = json.dumps(json_body).encode("utf-8") if json_body is not None else b""

    lines = [
        f"{method} {path} HTTP/1.1",
        "Host: 127.0.0.1",
        "Content-Type: application/json",
        f"Content-Length: {len(body_bytes)}",
        "",
        ""
    ]
    writer.write("\r\n".join(lines).encode("ascii") + body_bytes)
    await writer.drain()

    raw_response = await reader.read()
    writer.close()
    await writer.wait_closed()

    head, _, body = raw_response.partition(b"\r\n\r\n")
    status_line = head.decode("ascii").split("\r\n")[0]
    status_code = int(status_line.split(" ")[1])
    return status_code, body.decode("utf-8")


@pytest.mark.asyncio
async def test_multi_torrent_session_and_web_api(tmp_path):
    f1 = tmp_path / "alpha.bin"
    f1.write_bytes(b"A" * 16384)
    t1_path = tmp_path / "alpha.torrent"
    _, hash1, _ = TorrentCreator(str(f1), piece_length=16384).save_torrent_file(str(t1_path))

    f2 = tmp_path / "beta.bin"
    f2.write_bytes(b"B" * 32768)
    t2_path = tmp_path / "beta.torrent"
    _, hash2, _ = TorrentCreator(str(f2), piece_length=16384).save_torrent_file(str(t2_path))

    manager = MultiTorrentSessionManager(
        peer_id=b"-PY0001-123456789012",
        listen_port=0,
        enable_dht=False,
        enable_lpd=False
    )

    web_server = WebControlServer(session_manager=manager, host="127.0.0.1", port=0)
    web_port = await web_server.start()

    code_html, html_body = await _send_raw_http(web_port, "GET", "/")
    assert code_html == 200
    assert "Py-BitTorrent Engine" in html_body

    await manager.add_torrent_file(str(t1_path), auto_start=False)
    await manager.add_torrent_file(str(t2_path), auto_start=False)

    code_api, api_body = await _send_raw_http(web_port, "GET", "/api/torrents")
    assert code_api == 200
    parsed = json.loads(api_body)
    assert len(parsed["torrents"]) == 2

    names = {item["name"] for item in parsed["torrents"]}
    assert names == {"alpha.bin", "beta.bin"}

    # Verify Prometheus /metrics endpoint
    code_metrics, metrics_body = await _send_raw_http(web_port, "GET", "/metrics")
    assert code_metrics == 200
    assert "bittorrent_managed_torrents 2" in metrics_body

    code_pause, pause_body = await _send_raw_http(
        web_port,
        "POST",
        "/api/torrents/pause",
        {"info_hash": hash1.hex()}
    )
    assert code_pause == 200
    assert json.loads(pause_body)["success"] is True
    assert manager.sessions[hash1.hex()].status == "paused"

    await web_server.stop()