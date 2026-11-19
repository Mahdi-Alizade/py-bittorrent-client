import asyncio
import json
from typing import Optional, Tuple

from core.session_manager import MultiTorrentSessionManager


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Py-BitTorrent Enterprise Control Plane</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }
  .container { max-width: 1100px; margin: 0 auto; }
  header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 16px; margin-bottom: 24px; }
  h1 { margin: 0; font-size: 1.5rem; color: #38bdf8; }
  .badge { background: #0284c7; padding: 4px 10px; border-radius: 999px; font-size: 0.8rem; font-weight: 600; }
  .add-bar { display: flex; gap: 10px; margin-bottom: 24px; }
  input { flex: 1; padding: 10px 14px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #f8fafc; font-size: 0.95rem; }
  button { padding: 10px 18px; border-radius: 8px; border: none; background: #0ea5e9; color: white; font-weight: 600; cursor: pointer; }
  button:hover { background: #0284c7; }
  button.secondary { background: #475569; padding: 6px 12px; font-size: 0.82rem; }
  table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 10px; overflow: hidden; }
  th, td { padding: 14px 16px; text-align: left; border-bottom: 1px solid #334155; font-size: 0.9rem; }
  th { background: #0f172a; color: #94a3b8; text-transform: uppercase; font-size: 0.78rem; letter-spacing: 0.05em; }
  .progress-wrap { background: #334155; border-radius: 6px; height: 10px; width: 140px; overflow: hidden; }
  .progress-fill { background: #22c55e; height: 100%; transition: width 0.3s ease; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Py-BitTorrent Engine</h1>
    <span class="badge">BEP-3 / BEP-5 DHT / BEP-9 / BEP-11 PEX / BEP-14 LPD / BEP-15 UDP / BEP-19</span>
  </header>
  <div class="add-bar">
    <input id="targetInput" type="text" placeholder="Paste magnet:?xt=urn:btih:... URI or local .torrent file path">
    <button onclick="addTorrent()">Add Torrent</button>
  </div>
  <table>
    <thead>
      <tr>
        <th>Name</th>
        <th>Status</th>
        <th>Progress</th>
        <th>Down / Up</th>
        <th>Peers</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody id="torrentRows"></tbody>
  </table>
</div>
<script>
function fmtSpeed(bps) {
  if (bps >= 1048576) return (bps / 1048576).toFixed(2) + ' MB/s';
  if (bps >= 1024) return (bps / 1024).toFixed(1) + ' KB/s';
  return bps + ' B/s';
}
async function fetchStats() {
  const res = await fetch('/api/torrents');
  const data = await res.json();
  const tbody = document.getElementById('torrentRows');
  tbody.innerHTML = '';
  for (const t of data.torrents) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${t.name}</strong><br><small style="color:#94a3b8">${t.info_hash.slice(0, 16)}...</small></td>
      <td>${t.status.toUpperCase()}</td>
      <td>
        <div class="progress-wrap"><div class="progress-fill" style="width:${t.progress_percent}%"></div></div>
        <small>${t.progress_percent}% (${t.completed_pieces}/${t.total_pieces})</small>
      </td>
      <td>${fmtSpeed(t.download_speed_bps)} / ${fmtSpeed(t.upload_speed_bps)}</td>
      <td>${t.connected_peers} / ${t.known_swarm_peers}</td>
      <td>
        <button class="secondary" onclick="controlTorrent('${t.info_hash}', 'pause')">Pause</button>
        <button class="secondary" onclick="controlTorrent('${t.info_hash}', 'resume')">Resume</button>
      </td>
    `;
    tbody.appendChild(tr);
  }
}
async function addTorrent() {
  const val = document.getElementById('targetInput').value.trim();
  if (!val) return;
  await fetch('/api/torrents', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({target: val})
  });
  document.getElementById('targetInput').value = '';
  fetchStats();
}
async function controlTorrent(hash, action) {
  await fetch('/api/torrents/' + action, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({info_hash: hash})
  });
  fetchStats();
}
setInterval(fetchStats, 1500);
fetchStats();
</script>
</body>
</html>
"""


class WebControlServer:
    """
    Lightweight zero-dependency asynchronous HTTP/JSON REST API, Prometheus metrics
    exporter, and Web Dashboard for real-time multi-torrent orchestration.
    """

    def __init__(self, session_manager: MultiTorrentSessionManager, host: str = "127.0.0.1", port: int = 8080):
        self.session_manager = session_manager
        self.host = host
        self.port = port
        self._server: Optional[asyncio.AbstractServer] = None
        self.bound_port: Optional[int] = None

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle_http_client, self.host, self.port)
        if self._server.sockets:
            self.bound_port = self._server.sockets[0].getsockname()[1]
        return self.bound_port or self.port

    async def stop(self):
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def render_prometheus_metrics(self) -> str:
        """
        Exports engine telemetry in standard Prometheus text exposition format.
        """
        telemetry = self.session_manager.get_all_telemetry()
        total_torrents = len(telemetry)
        total_down_bps = sum(item["download_speed_bps"] for item in telemetry)
        total_up_bps = sum(item["upload_speed_bps"] for item in telemetry)
        total_connected_peers = sum(item["connected_peers"] for item in telemetry)
        banned_peers_count = len(self.session_manager.peer_guard.get_banned_summary())

        lines = [
            "# HELP bittorrent_managed_torrents Total number of managed torrent sessions",
            "# TYPE bittorrent_managed_torrents gauge",
            f"bittorrent_managed_torrents {total_torrents}",
            "# HELP bittorrent_download_speed_bytes_per_sec Aggregate download throughput in bytes/sec",
            "# TYPE bittorrent_download_speed_bytes_per_sec gauge",
            f"bittorrent_download_speed_bytes_per_sec {total_down_bps}",
            "# HELP bittorrent_upload_speed_bytes_per_sec Aggregate upload throughput in bytes/sec",
            "# TYPE bittorrent_upload_speed_bytes_per_sec gauge",
            f"bittorrent_upload_speed_bytes_per_sec {total_up_bps}",
            "# HELP bittorrent_connected_peers Total active TCP peer connections",
            "# TYPE bittorrent_connected_peers gauge",
            f"bittorrent_connected_peers {total_connected_peers}",
            "# HELP bittorrent_banned_peers Total hostile IPs currently banned by PeerGuard",
            "# TYPE bittorrent_banned_peers gauge",
            f"bittorrent_banned_peers {banned_peers_count}",
            ""
        ]
        return "\n".join(lines)

    @staticmethod
    def _build_http_response(status_code: int, content_type: str, body_bytes: bytes) -> bytes:
        status_text = {
            200: "OK",
            201: "Created",
            400: "Bad Request",
            404: "Not Found",
            500: "Internal Server Error"
        }.get(status_code, "OK")

        headers = [
            f"HTTP/1.1 {status_code} {status_text}",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(body_bytes)}",
            "Connection: close",
            "",
            ""
        ]
        return "\r\n".join(headers).encode("ascii") + body_bytes

    async def _read_http_request(self, reader: asyncio.StreamReader) -> Tuple[str, str, bytes]:
        raw_head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5.0)
        head_text = raw_head.decode("utf-8", errors="ignore")
        lines = head_text.split("\r\n")
        request_line = lines[0].split(" ")
        method = request_line[0].upper() if len(request_line) >= 1 else "GET"
        path = request_line[1] if len(request_line) >= 2 else "/"

        content_length = 0
        for line in lines[1:]:
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())

        body_bytes = b""
        if content_length > 0:
            body_bytes = await asyncio.wait_for(reader.readexactly(content_length), timeout=5.0)

        return method, path, body_bytes

    async def _handle_http_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            method, path, body_bytes = await self._read_http_request(reader)

            if method == "GET" and path == "/":
                resp = self._build_http_response(200, "text/html; charset=utf-8", DASHBOARD_HTML.encode("utf-8"))
                writer.write(resp)
                await writer.drain()
                return

            if method == "GET" and path == "/metrics":
                metrics_text = self.render_prometheus_metrics()
                resp = self._build_http_response(200, "text/plain; version=0.0.4", metrics_text.encode("utf-8"))
                writer.write(resp)
                await writer.drain()
                return

            if method == "GET" and path == "/api/torrents":
                payload = {
                    "torrents": self.session_manager.get_all_telemetry(),
                    "banned_peers": self.session_manager.peer_guard.get_banned_summary()
                }
                resp = self._build_http_response(200, "application/json", json.dumps(payload).encode("utf-8"))
                writer.write(resp)
                await writer.drain()
                return

            if method == "POST" and path == "/api/torrents":
                data = json.loads(body_bytes.decode("utf-8"))
                target = str(data.get("target", "")).strip()
                if not target:
                    err = self._build_http_response(400, "application/json", b'{"error":"Missing target"}')
                    writer.write(err)
                    await writer.drain()
                    return

                if target.startswith("magnet:?"):
                    session = await self.session_manager.add_magnet_uri(target)
                else:
                    session = await self.session_manager.add_torrent_file(target)

                out = json.dumps({"info_hash": session.info_hash_hex, "name": session.name}).encode("utf-8")
                writer.write(self._build_http_response(201, "application/json", out))
                await writer.drain()
                return

            if method == "POST" and path in ("/api/torrents/pause", "/api/torrents/resume"):
                data = json.loads(body_bytes.decode("utf-8"))
                info_hash = str(data.get("info_hash", "")).strip()
                if path.endswith("/pause"):
                    ok = await self.session_manager.pause_torrent(info_hash)
                else:
                    ok = await self.session_manager.resume_torrent(info_hash)

                code = 200 if ok else 404
                out = json.dumps({"success": ok}).encode("utf-8")
                writer.write(self._build_http_response(code, "application/json", out))
                await writer.drain()
                return

            writer.write(self._build_http_response(404, "application/json", b'{"error":"Not Found"}'))
            await writer.drain()
        except Exception as exc:
            err_json = json.dumps({"error": str(exc)}).encode("utf-8")
            try:
                writer.write(self._build_http_response(500, "application/json", err_json))
                await writer.drain()
            except Exception:
                pass
        finally:
            writer.close()
            await writer.wait_closed()