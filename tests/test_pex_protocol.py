from core.extension_protocol import ExtensionProtocol
from core.pex_protocol import PeerExchangeProtocol


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

    # Strip 4-byte length prefix
    payload = msg_packet[4:]
    parsed_added, parsed_dropped = PeerExchangeProtocol.parse_pex_message(payload)

    assert parsed_added == added
    assert parsed_dropped == dropped


def test_extended_capabilities_detection():
    hs_pkt = ExtensionProtocol.create_extension_handshake()
    caps = ExtensionProtocol.parse_extended_capabilities(hs_pkt[4:])

    assert caps["ut_metadata"] == ExtensionProtocol.LOCAL_UT_METADATA_ID
    assert caps["ut_pex"] == ExtensionProtocol.LOCAL_UT_PEX_ID