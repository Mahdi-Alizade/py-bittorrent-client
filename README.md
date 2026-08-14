# Py-BitTorrent Client 🔥

A zero-dependency, modular BitTorrent client implementation in Python 3. 
Designed for educational purposes and low-level network engineering interviews.

## 🚀 Features

- **Zero External Dependencies**: Pure Python implementation of the Bencoding format parser.
- **Raw Socket Networking**: Implements BEP-00 (Handshake) and BEP-03 (Tracker Protocol) from scratch.
- **Modular Architecture**: Decoupled components for Parsing, Transport (TCP), Session Management, and Persistence.
- **Memory-Mapped Streaming**: Handles block-level reassembly and verification efficiently.

## 🛠️ Architecture

The project follows a layered design pattern:

1. **Core Parser (`parser.py`)**: Recursive Bencoding decoder/encoder for binary metadata.
2. **Protocol Engine (`protocol_messages.py`)**: Structured message packing (Request, Piece, Have).
3. **Transport Layer (`socket_handler.py`)**: TCP connection management and Handshake verification.
4. **Session Manager (`client_logic.py`)**: Orchestrates the download loop, tracker interaction, and peer selection.

## 💻 Installation & Usage

### Prerequisites
- Python 3.10+
- Windows (PowerShell) / Linux / macOS

```powershell
git clone https://github.com/MahdiAlizade/py-bittorrent-client.git
cd py-bittorrent-client
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install colorama requests

Run Local Demo
To simulate a full download session with mock data:


python main.py data/sample.txt.torrent --tests
Real-world Torrents
Provide a valid .torrent file path. The client will attempt to connect to the swarm via the embedded Tracker URL.


python main.py my-movie.torrent
📂 Project Structure

├── core/                  # Core library modules
│   ├── __init__.py
│   ├── parser.py          # Bencoding logic
│   ├── protocol_messages.py # BEP-03 Message formats
│   ├── socket_handler.py  # TCP Handshake logic
│   ├── piece_manager.py   # Download assembly
│   └── tracker_client.py  # Tracker API communication
├── downloads/             # Output directory
├── main.py                # Application entrypoint
└── README.md              # This file
⚙️ License
MIT