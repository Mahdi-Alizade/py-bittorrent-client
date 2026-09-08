# Py-BitTorrent Client Engine

A modular BitTorrent client engine built from scratch in Python 3, adhering directly to the official BitTorrent specifications (BEP-3, BEP-15, and BEP-23) without external torrent libraries.

---

## Features

- **Pure Bencode Parser (`core/parser.py`)**: Implements strict encoding and decoding for byte strings, integers, lists, and ordered dictionaries with canonical serialization.
- **Binary Wire Protocol (`core/protocol_messages.py`)**: Complete implementation of BEP-3 peer framing, supporting `keep-alive`, `choke`, `unchoke`, `interested`, `not_interested`, `have`, `bitfield`, `request`, `piece`, and `cancel`.
- **Dual Tracker Engine (`core/tracker_client.py`)**:
  - **HTTP/HTTPS (BEP-3)**: Handles Bencoded tracker announcements and compact peer extraction.
  - **UDP Tracker (BEP-15)**: Implements binary packet flow (`connect` handshake, transaction verification, and `announce` exchange).
  - **Compact Peer Representation (BEP-23)**: Parses network byte order 6-byte chunks (4-byte IPv4 + 2-byte port).
- **Seek-based Block Storage (`core/reassemble.py`)**: Uses random-access pre-allocated file structures and SHA-1 cryptographic validation per piece.
- **Edge Piece & Block Management (`core/piece_manager.py`)**: Accurately computes variable boundaries for the final truncated piece and tracks block offsets.

---

## Architecture Overview

.torrent Metainfo
│
▼
Bencode Parser (BDecoder)
│
▼
Info Hash (SHA-1) & Peer ID
│
▼
Tracker Client (HTTP / UDP Tracker Protocol)
│
▼
Discovered Swarm Peers
│
▼
TCP Binary Handshake & Framed Wire Protocol
│
▼
Piece / Block Offset Manager
│
▼
SHA-1 Hash Verification
│
▼
Pre-allocated Seek-based Persistent File


---

## Getting Started

### Prerequisites

- Python 3.10+
- Virtual environment (`venv`)

### Installation

1. Clone repository:
   ```bash
   git clone [https://github.com/MahdiAlizade/py-bittorrent-client.git](https://github.com/MahdiAlizade/py-bittorrent-client.git)
   cd py-bittorrent-client
Activate virtual environment:

Windows (PowerShell):

PowerShell
.\venv\Scripts\Activate.ps1
Linux / macOS:

Bash
source venv/bin/activate
Install dependencies:

Bash
pip install -r requirements.txt
Usage
1. Generate Local Test Torrent
Create an authentic test payload and corresponding .torrent file:

PowerShell
python generate_test_torrent.py
2. Run the Download Engine
Start the engine by providing a path to any valid .torrent file:

PowerShell
python main.py data/sample.txt.torrent --max-peers 10
Automated Test Suite
The engine includes 29 unit and integration tests covering parser bounds, protocol framing, tracker responses, and storage integrity:

PowerShell
python -m pytest
License
MIT License.