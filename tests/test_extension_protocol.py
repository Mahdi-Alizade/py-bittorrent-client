import hashlib
import struct
from core.extension_protocol import ExtensionProtocol, MetadataAssembler
from core.parser import TorrentEncoder


def test_reserved_bytes_extension_flag():
    reserved = ExtensionProtocol.build_reserved_bytes()
    assert len(reserved) == 8
    assert ExtensionProtocol.peer_supports_extensions(reserved) is True
    assert ExtensionProtocol.peer_supports_extensions(b"\x00" * 8) is False


def test_extension_handshake_roundtrip():
    handshake_pkt = ExtensionProtocol.create_extension_handshake()
    # Strip 4-byte length prefix
    payload = handshake_pkt[4:]

    peer_id, meta_size = ExtensionProtocol.parse_extension_handshake(payload)
    assert peer_id == ExtensionProtocol.LOCAL_UT_METADATA_ID
    assert meta_size is None

    # Simulate peer reply containing metadata_size
    peer_dict = {"m": {"ut_metadata": 3}, "metadata_size": 32768}
    encoded_reply = TorrentEncoder.encode(peer_dict)
    peer_payload = struct.pack(">BB", ExtensionProtocol.MSG_EXTENDED, 0) + encoded_reply

    parsed_id, parsed_size = ExtensionProtocol.parse_extension_handshake(peer_payload)
    assert parsed_id == 3
    assert parsed_size == 32768


def test_metadata_assembler_verification():
    sample_info = {
        "name": "ubuntu.iso",
        "piece length": 262144,
        "length": 1048576,
        "pieces": b"A" * 80
    }
    raw_info = TorrentEncoder.encode(sample_info)
    expected_hash = hashlib.sha1(raw_info).digest()

    assembler = MetadataAssembler(expected_info_hash=expected_hash, metadata_size=len(raw_info))
    assert assembler.num_pieces == 1
    assert assembler.get_missing_pieces() == [0]

    # Build simulated ut_metadata data response
    header_dict = {"msg_type": ExtensionProtocol.META_DATA, "piece": 0, "total_size": len(raw_info)}
    msg_payload = (
        struct.pack(">BB", ExtensionProtocol.MSG_EXTENDED, ExtensionProtocol.LOCAL_UT_METADATA_ID)
        + TorrentEncoder.encode(header_dict)
        + raw_info
    )

    parsed = ExtensionProtocol.parse_metadata_message(msg_payload)
    assert parsed is not None
    msg_type, piece_idx, chunk = parsed
    assert msg_type == ExtensionProtocol.META_DATA
    assert piece_idx == 0

    assembler.add_piece(piece_idx, chunk)
    assert assembler.is_complete() is True

    verified_info = assembler.assemble_and_verify()
    assert verified_info is not None
    assert verified_info[b"name"] == b"ubuntu.iso"