# Py-BitTorrent Client 🔥

A lightweight BitTorrent client written from scratch in **Python 3**, with a focus on understanding the BitTorrent protocol, low-level networking, and modular system design.

The project implements core BitTorrent functionality without relying on a dedicated BitTorrent library, making it useful for **learning, experimentation, and low-level networking practice**.

> **Status:** Educational / experimental project

---

## ✨ Features

* **Pure Python implementation** of Bencoding
* **Raw TCP socket networking**
* **BitTorrent peer handshake** implementation
* **Tracker communication**
* **BitTorrent protocol message encoding/decoding**
* **Piece and block management**
* **SHA-1 piece verification**
* **Modular architecture** with separated parsing, networking, protocol, and session logic
* Supports **Python 3.10+**

---

## 🧠 What I Built

Instead of using an existing BitTorrent client library, the protocol is implemented directly on top of Python's standard networking primitives.

The client handles the main stages of a torrent download:

```text
.torrent file
     │
     ▼
Bencode Parser
     │
     ▼
Torrent Metadata
     │
     ▼
Tracker Client
     │
     ▼
Peer Discovery
     │
     ▼
TCP Handshake
     │
     ▼
BitTorrent Messages
     │
     ▼
Piece / Block Manager
     │
     ▼
SHA-1 Verification
     │
     ▼
Downloaded File
```

This structure keeps protocol parsing, network transport, and download orchestration independent from each other.

---

## 🏗️ Architecture

The project uses a layered design to keep the individual components focused on a single responsibility.

### 1. Bencode Parser

**`core/parser.py`**

Responsible for encoding and decoding BitTorrent's Bencode data format.

It handles:

* Integers
* Byte strings
* Lists
* Dictionaries
* Nested structures

Torrent metadata is parsed directly from the `.torrent` file without using a third-party BitTorrent parser.

---

### 2. Protocol Messages

**`core/protocol_messages.py`**

Defines the BitTorrent peer protocol messages and handles their serialization/deserialization.

Examples include:

* `choke`
* `unchoke`
* `interested`
* `not interested`
* `have`
* `request`
* `piece`
* `cancel`

This layer keeps protocol-level message handling separate from the underlying TCP connection.

---

### 3. Socket / Transport Layer

**`core/socket_handler.py`**

Handles low-level TCP communication with peers.

Responsibilities include:

* TCP connection management
* Peer handshake
* Sending and receiving raw bytes
* Message framing
* Basic connection handling

No high-level torrent logic is placed in this layer.

---

### 4. Tracker Client

**`core/tracker_client.py`**

Communicates with the tracker specified by the torrent metadata and retrieves peer information.

The tracker layer is intentionally isolated from the peer communication layer so that peer networking can evolve independently.

---

### 5. Piece Manager

**`core/piece_manager.py`**

Responsible for assembling downloaded blocks into pieces and validating the resulting data.

The manager handles:

* Block assembly
* Piece boundaries
* Piece completion
* SHA-1 verification

---

### 6. Client / Session Logic

**`core/client_logic.py`**

Coordinates the complete download workflow.

It connects the different components together:

```text
Tracker
   │
   ▼
Peer Discovery
   │
   ▼
Peer Connections
   │
   ▼
Protocol Messages
   │
   ▼
Piece Manager
   │
   ▼
File Assembly
```

The goal is to keep orchestration logic out of the lower-level networking and parsing modules.

---

## 📁 Project Structure

```text
py-bittorrent-client/
│
├── core/
│   ├── __init__.py
│   ├── parser.py
│   ├── protocol_messages.py
│   ├── socket_handler.py
│   ├── piece_manager.py
│   └── tracker_client.py
│
├── downloads/
│   └── # Downloaded files
│
├── data/
│   └── # Sample torrent / test data
│
├── main.py
└── README.md
```

---

## 🚀 Getting Started

### Requirements

* Python **3.10+**
* Windows, Linux, or macOS

### Clone the repository

```bash
git clone https://github.com/MahdiAlizade/py-bittorrent-client.git
cd py-bittorrent-client
```

### Create a virtual environment

#### Windows — PowerShell

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

### Install dependencies

```bash
pip install colorama requests
```

---

## ▶️ Usage

### Local Demo

Run the included test/demo scenario:

```bash
python main.py data/sample.txt.torrent --tests
```

### Run with a Real Torrent

Provide a valid `.torrent` file:

```bash
python main.py my-torrent.torrent
```

The client will parse the torrent metadata, contact the configured tracker, discover peers, and attempt to establish peer connections.

> **Note:** Support for real-world torrents depends on the tracker type, peer behavior, protocol coverage, and the current implementation status of the client.

---

## 🔬 Why This Project?

This project was built primarily to explore what happens **under the abstraction layer** of a typical BitTorrent client.

Instead of:

```text
torrent library → download()
```

the goal is to understand and implement the underlying pieces:

```text
Bencode
   ↓
Torrent Metadata
   ↓
Tracker Protocol
   ↓
Peer Discovery
   ↓
TCP Connections
   ↓
BitTorrent Handshake
   ↓
Peer Messages
   ↓
Block Requests
   ↓
Piece Verification
```

This makes the project particularly useful for learning about:

* Network protocols
* TCP sockets
* Binary protocols
* Serialization / deserialization
* Concurrent network communication
* File I/O
* Hash-based data verification
* Modular software architecture

---

## 🧪 Testing

The project includes a local test/demo mode for exercising the client without relying entirely on a live BitTorrent swarm.

```bash
python main.py data/sample.txt.torrent --tests
```

Additional protocol and component-level tests can be added as the implementation evolves.

---

## 🛠️ Tech Stack

| Technology   | Purpose                    |
| ------------ | -------------------------- |
| Python 3.10+ | Core implementation        |
| TCP Sockets  | Peer-to-peer communication |
| Bencode      | Torrent metadata encoding  |
| SHA-1        | Piece verification         |
| `requests`   | Tracker HTTP communication |
| `colorama`   | CLI output                 |

---

## 📌 Current Limitations

This is an educational implementation rather than a production-ready BitTorrent client.

Some areas that can be expanded include:

* More complete peer protocol support
* Better peer selection and choking algorithms
* Improved connection management
* More robust error handling
* UDP tracker support
* DHT / peer discovery
* Concurrent piece downloading
* More comprehensive automated tests

---

## 🗺️ Roadmap

* [ ] Improve peer connection management
* [ ] Add more comprehensive protocol tests
* [ ] Improve concurrent downloading
* [ ] Add UDP tracker support
* [ ] Implement DHT-based peer discovery
* [ ] Improve error recovery and retry handling
* [ ] Add performance benchmarks

---

## 📄 License

MIT License
