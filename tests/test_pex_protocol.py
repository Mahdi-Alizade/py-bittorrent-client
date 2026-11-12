import asyncio
import hashlib
import struct
import pytest
from core.async_peer import PROTOCOL_IDENTIFIER
from core.client_logic import BitTorrentClient
from core.extension_protocol import ExtensionProtocol
from core.parser import TorrentEncoder
from core.pex_protocol import PeerExchangeProtocol
from core.piece_manager import PieceManager
from core.protocol_messages import TorrentMessage


def test_pex_compact_encode_and_decode():
    sample_peers = [("10.0.0.1", 6881), ("192.168.1.50", 51413)]
    compact_bytes = PeerExchangeProtocol.encode_compact_peers(sample_peers)
    assert len(compact_bytes) == 12

    decoded = PeerExchangeProtocol.decode_compact_peers(compact_bytes)
    assert decoded == sample_peers


def test_pex_message_roundtrip():
    added = [("203.0.113.10", 6881), ("198.51.100.42", 8999)]
    dropped = [("192.0.2.5", 6882)]

    msg_packet = PeerExchangeProtocol.create_pex_message(
        peer_ut_pex_id=PeerExchangeProtocol.LOCAL_PEX_ID,
        added_peers=added,
        dropped_peers=dropped
    )

    payload = msg_packet[4:]
    parsed_added, parsed_dropped = PeerExchangeProtocol.parse_pex_message(payload)

    assert parsed_added == added
    assert parsed_dropped == dropped


def test_extended_capabilities_detection():
    hs_pkt = ExtensionProtocol.create_extension_handshake()
    caps = ExtensionProtocol.parse_extended_capabilities(hs_pkt[4:])

    assert caps["ut_metadata"] == ExtensionProtocol.LOCAL_UT_METADATA_ID
    assert caps["ut_pex"] == ExtensionProtocol.LOCAL_UT_PEX_ID


@pytest.mark.asyncio
async def test_client_spawns_worker_on_pex_message(tmp_path):
    payload_data = b"P" * 16384
    piece_hash = hashlib.sha1(payload_data).digest()

    info_dict = {
        "name": "pex_test.bin",
        "piece length": 16384,
        "length": 16384,
        "pieces": piece_hash
    }
    raw_info = TorrentEncoder.encode(info_dict)
    info_hash = hashlib.sha1(raw_info).digest()
    download_complete_event = asyncio.Event()

    async def peer_seeder_handler(reader, writer):
        try:
            await reader.readexactly(68)
            reserved = ExtensionProtocol.build_reserved_bytes()
            hs = struct.pack(">B19s8s20s20s", 19, PROTOCOL_IDENTIFIER, reserved, info_hash, b"-SEED02-000000000002")
            writer.write(hs)
            writer.write(TorrentMessage.create_unchoke())
            writer.write(TorrentMessage.create_have(0))
            await writer.drain()

            while not download_complete_event.is_set():
                hdr = await asyncio.wait_for(reader.readexactly(4), timeout=2.0)
                msg_len = struct.unpack(">I", hdr)[0]
                if msg_len == 0:
                    continue
                body = await reader.readexactly(msg_len)
                if body[0] == TorrentMessage.MSG_REQUEST:
                    p_idx, off, length = struct.unpack(">III", body[1:13])
                    piece_msg = struct.pack(">IBII", 9 + length, TorrentMessage.MSG_PIECE, p_idx, off) + payload_data
                    writer.write(piece_msg)
                    await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    seeder_server = await asyncio.start_server(peer_seeder_handler, "127.0.0.1", 0)
    seeder_port = seeder_server.sockets[0].getsockname()[1]

    async def peer_introducer_handler(reader, writer):
        try:
            await reader.readexactly(68)
            reserved = ExtensionProtocol.build_reserved_bytes()
            hs = struct.pack(">B19s8s20s20s", 19, PROTOCOL_IDENTIFIER, reserved, info_hash, b"-INTR01-000000000001")
            writer.write(hs)
            await writer.drain()

            # Read client's extension handshake before sending PEX
            hdr = await asyncio.wait_for(reader.readexactly(4), timeout=2.0)
            msg_len = struct.unpack(">I", hdr)[0]
            if msg_len > 0:
                await reader.readexactly(msg_len)

            pex_msg = PeerExchangeProtocol.create_pex_message(
                peer_ut_pex_id=ExtensionProtocol.LOCAL_UT_PEX_ID,
                added_peers=[("127.0.0.1", seeder_port)]
            )
            writer.write(pex_msg)
            await writer.drain()

            await asyncio.wait_for(download_complete_event.wait(), timeout=3.0)
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    intro_server = await asyncio.start_server(peer_introducer_handler, "127.0.0.1", 0)
    intro_port = intro_server.sockets[0].getsockname()[1]

    metadata = {"info": info_dict}
    client = BitTorrentClient(metadata, enable_dht=False)

    manager = PieceManager("pex_test.bin", 16384, 1, total_length=16384)
    manager.writer.output_dir = tmp_path
    manager.writer.final_path = tmp_path / "pex_test.bin"
    manager.writer.initialize_file()
    manager.writer.piece_hashes = [piece_hash]

    client._spawn_peer_worker_if_new(
        ip="127.0.0.1",
        port=intro_port,
        raw_info_hash=info_hash,
        my_peer_id=b"-PY0001-999999999999",
        manager=manager,
        max_peers=10
    )

    for _ in range(40):
        if all(manager.have_pieces):
            download_complete_event.set()
            break
        await asyncio.sleep(0.05)

    download_complete_event.set()
    assert all(manager.have_pieces) is True
    assert ("127.0.0.1", seeder_port) in client.known_peers

    for t in client.worker_tasks:
        if not t.done():
            t.cancel()

    intro_server.close()
    await intro_server.wait_closed()
    seeder_server.close()
    await seeder_server.wait_closed()