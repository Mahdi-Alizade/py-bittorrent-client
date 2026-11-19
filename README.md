# Py-BitTorrent Enterprise Engine

A production-grade, asynchronous BitTorrent client, seeder, torrent creator, and multi-torrent daemon written entirely in Python 3.10+. No external BitTorrent libraries are used — every protocol detail is implemented from the ground up with `asyncio` and the Python standard library.

The engine supports eight official BitTorrent Enhancement Proposals (BEPs), a live Web Control Dashboard, a JSON REST API, Prometheus metrics, and an active anti-poisoning security layer.

---

## Supported Standards

| BEP | Description |
| :--- | :--- |
| **BEP-0003** | Core protocol, Bencode, TCP wire messages, SHA-1 piece verification |
| **BEP-0005** | Kademlia DHT for trackerless peer discovery |
| **BEP-0009** | `ut_metadata` – fetch torrent metadata from peers (magnet links) |
| **BEP-0010** | Extension Protocol handshake |
| **BEP-0011** | Peer Exchange (`ut_pex`) |
| **BEP-0014** | Local Peer Discovery over IPv4 multicast |
| **BEP-0015** | UDP Tracker Protocol |
| **BEP-0019** | HTTP/HTTPS WebSeeding |

---

## Architecture

The codebase is organized under `core/` and is deliberately modular:

### Protocol & Parsing
- `parser.py` – recursive Bencode decoder and strict canonical encoder
- `protocol_messages.py` – all standard wire messages (`CHOKE`, `UNCHOKE`, `INTERESTED`, `NOT_INTERESTED`, `HAVE`, `BITFIELD`, `REQUEST`, `PIECE`, `CANCEL`, `KEEP_ALIVE`)
- `magnet_parser.py` – full magnet URI support (hex and base32 info-hashes)
- `extension_protocol.py` – BEP-10 handshake + BEP-9 metadata assembler

### Peer Discovery & Networking
- `async_peer.py` – non-blocking TCP connections and handshake validation
- `tracker_client.py` / `udp_tracker.py` – unified HTTP and binary UDP trackers
- `dht_client.py` – Kademlia DHT node and iterative crawler
- `pex_protocol.py` – compact peer list encoding/decoding
- `lpd_service.py` – multicast Local Peer Discovery
- `webseed_client.py` – HTTP Range requests against web seeds

### Transfer Logic
- `piece_selector.py` – rarest-first selection
- `block_picker.py` – 16 KiB block tracking with pipelining
- `piece_manager.py` – block requests, end-game mode, seeding, contributor tracking
- `choking_manager.py` – tit-for-tat + optimistic unchoke (every 10 s)
- `rate_limiter.py` – token-bucket download/upload limits and throughput monitoring

### Storage & Creation
- `reassemble.py` / `multi_file_storage.py` – random-access disk I/O for single- and multi-file torrents
- `resume_manager.py` – atomic fast-resume state
- `torrent_creator.py` – generate `.torrent` files and magnet links from files or directories

### Security & Control Plane
- `peer_guard.py` – CIDR blocklists, trust scoring, automatic bans for peers that send corrupt pieces
- `session_manager.py` – concurrent multi-torrent management, shared LPD/PeerGuard, hot watch folder
- `web_dashboard.py` – zero-dependency async HTTP server providing:
  - Live HTML/JS dashboard (`GET /`)
  - JSON REST API (`/api/torrents`, `/api/torrents/pause`, `/api/torrents/resume`)
  - Prometheus metrics (`GET /metrics`)

---

## CLI Modes

### Single torrent / magnet download

```bash
python main.py file.torrent --port 6881 --seed --max-down 500 --max-up 200
python main.py "magnet:?xt=urn:btih:..." --max-peers 40
Multi-torrent daemon + web UI
Bash
python main.py --daemon --web-port 8080 --port 6881 --watch-dir ./watch --blocklist 192.0.2.0/24
Open http://127.0.0.1:8080 in your browser for the live dashboard.

Create a torrent
Bash
python main.py --create ./source_folder \
               --out ./release.torrent \
               --tracker udp://tracker.opentrackr.org:1337/announce \
               --piece-size 256
Installation
Bash
git clone [https://github.com/Mahdi-Alizade/py-bittorrent-client.git](https://github.com/Mahdi-Alizade/py-bittorrent-client.git)
cd py-bittorrent-client
python -m venv venv
source venv/bin/activate          # Windows PowerShell: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Python 3.10 or newer is required. External dependencies are deliberately minimal: colorama, pytest, and pytest-asyncio.

Testing
The project ships with 81 automated unit and integration tests covering Bencode, wire framing, async sockets, DHT, PEX, LPD, WebSeed, choking, rate limiting, fast-resume, PeerGuard, and the web control plane.

Bash
python -m pytest -v
Design Notes
Every protocol byte is handled in pure Python. There are no bindings to libtorrent or similar libraries.

The client is fully bidirectional — it both leeches and seeds.

Fast-resume state is written atomically after every verified piece.

PeerGuard actively tracks which peers contributed to each piece and bans those that send bad data.

The web dashboard and metrics endpoint require no extra frameworks; they are implemented with the standard library only.

License
MIT

Built by Mahdi Alizade.