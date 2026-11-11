import asyncio
import struct
import pytest
from core.async_peer import AsyncPeerConnection, PROTOCOL_IDENTIFIER
from core.protocol_messages import TorrentMessage


@pytest.mark.asyncio
async def test_async_handshake_and_exchange():
    info_hash = b"01234567890123456789"
    client_peer_id = b"-PY0001-abcdefgh1234"
    server_peer_id = b"-PEER01-9876543210ab"

    # Start a mock peer server
    async def mock_peer_server(reader, writer):
        # 1. Read handshake from client
        client_handshake = await reader.readexactly(68)
        assert client_handshake[1:20] == PROTOCOL_IDENTIFIER
        
        # 2. Reply with valid handshake
        pstrlen = len(PROTOCOL_IDENTIFIER)
        reserved = b"\x00" * 8
        resp_handshake = struct.pack(">B19s8s20s20s", pstrlen, PROTOCOL_IDENTIFIER, reserved, info_hash, server_peer_id)
        writer.write(resp_handshake)
        
        # 3. Send Unchoke message
        writer.write(TorrentMessage.create_unchoke())
        await writer.drain()
        
        await asyncio.sleep(0.1)
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(mock_peer_server, "127.0.0.1", 0)
    server_port = server.sockets[0].getsockname()[1]

    peer_conn = AsyncPeerConnection(
        ip="127.0.0.1",
        port=server_port,
        info_hash=info_hash,
        peer_id=client_peer_id,
        timeout=3.0
    )

    success = await peer_conn.connect_and_handshake()
    assert success is True
    assert peer_conn.is_connected is True

    # Read unchoke message
    msg = await peer_conn.read_message()
    assert msg is not None
    assert msg[4] == TorrentMessage.MSG_UNCHOKE

    await peer_conn.close()
    server.close()
    await server.wait_closed()