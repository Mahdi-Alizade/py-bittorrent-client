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