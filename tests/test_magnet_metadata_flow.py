import asyncio
import hashlib
import struct
import pytest
from core.async_peer import PROTOCOL_IDENTIFIER
from core.client_logic import BitTorrentClient
from core.extension_protocol import ExtensionProtocol
from core.magnet_parser import MagnetURIParser
from core.parser import TorrentEncoder


@pytest.mark.asyncio
async def test_fetch_metadata_from_mock_peer():
    sample_info = {
        "name": "debian-netinst.iso",
        "piece length": 262144,
        "length": 524288,
        "pieces": b"B" * 40
    }
    raw_info_bytes = TorrentEncoder.encode(sample_info)
    target_hash = hashlib.sha1(raw_info_bytes).digest()
    peer_server_id = b"-SEED01-123456789012"

    async def mock_metadata_peer(reader, writer):
        # 1. Read client handshake
        client_hs = await reader.readexactly(68)
        assert client_hs[28:48] == target_hash

        # 2. Reply with handshake advertising BEP-0010 extension support
        reserved = ExtensionProtocol.build_reserved_bytes()
        resp_hs = struct.pack(">B19s8s20s20s", 19, PROTOCOL_IDENTIFIER, reserved, target_hash, peer_server_id)
        writer.write(resp_hs)

        # 3. Send peer's Extended Handshake with ut_metadata=2 and metadata_size
        ext_dict = {"m": {"ut_metadata": 2}, "metadata_size": len(raw_info_bytes)}
        ext_payload = TorrentEncoder.encode(ext_dict)
        ext_msg = struct.pack(">IBB", 2 + len(ext_payload), ExtensionProtocol.MSG_EXTENDED, 0) + ext_payload
        writer.write(ext_msg)
        await writer.drain()

        # 4. Read client's extended handshake
        len_bytes = await reader.readexactly(4)
        msg_len = struct.unpack(">I", len_bytes)[0]
        await reader.readexactly(msg_len)

        # 5. Read client's ut_metadata request
        req_len_bytes = await reader.readexactly(4)
        req_len = struct.unpack(">I", req_len_bytes)[0]
        req_body = await reader.readexactly(req_len)
        assert req_body[0] == ExtensionProtocol.MSG_EXTENDED
        assert req_body[1] == 2

        # 6. Send ut_metadata data response back to client (using client's advertised id=1)
        data_header = {"msg_type": ExtensionProtocol.META_DATA, "piece": 0, "total_size": len(raw_info_bytes)}
        encoded_header = TorrentEncoder.encode(data_header)
        total_data_len = 2 + len(encoded_header) + len(raw_info_bytes)
        data_msg = (
            struct.pack(">IBB", total_data_len, ExtensionProtocol.MSG_EXTENDED, ExtensionProtocol.LOCAL_UT_METADATA_ID)
            + encoded_header
            + raw_info_bytes
        )
        writer.write(data_msg)
        await writer.drain()

        await asyncio.sleep(0.1)
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(mock_metadata_peer, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    magnet_uri = f"magnet:?xt=urn:btih:{target_hash.hex()}&dn=debian-netinst.iso"
    magnet_data = MagnetURIParser.parse(magnet_uri)

    fetched_meta = await BitTorrentClient.fetch_metadata_from_magnet(
        magnet_data=magnet_data,
        my_peer_id=b"-PY0001-abcdef123456",
        peer_list=[("127.0.0.1", port)]
    )

    assert fetched_meta is not None
    info = fetched_meta.get("info")
    assert info is not None
    assert info.get("name") == "debian-netinst.iso"

    server.close()
    await server.wait_closed()