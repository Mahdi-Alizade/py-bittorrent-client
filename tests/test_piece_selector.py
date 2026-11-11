from core.piece_selector import RarestFirstSelector


def test_peer_registration_and_have():
    selector = RarestFirstSelector(total_pieces=5)
    selector.record_peer_have("peer_A", 1)
    selector.record_peer_have("peer_B", 1)
    selector.record_peer_have("peer_B", 2)

    assert selector.piece_frequency[1] == 2
    assert selector.piece_frequency[2] == 1
    assert selector.piece_frequency[0] == 0


def test_rarest_piece_selection_order():
    selector = RarestFirstSelector(total_pieces=4)
    # Piece 0 is owned by 3 peers
    selector.record_peer_have("peer_1", 0)
    selector.record_peer_have("peer_2", 0)
    selector.record_peer_have("peer_3", 0)

    # Piece 1 is owned only by peer_1 (Rarest!)
    selector.record_peer_have("peer_1", 1)

    # When asking peer_1, it should prioritize piece 1 over piece 0
    picked = selector.pick_next_piece("peer_1")
    assert picked == 1


def test_bitfield_parsing_and_unregister():
    selector = RarestFirstSelector(total_pieces=8)
    # Bitfield 0b10000001 (0x81) means piece 0 and piece 7 are available
    selector.record_peer_bitfield("peer_x", b"\x81")

    assert selector.piece_frequency[0] == 1
    assert selector.piece_frequency[7] == 1
    assert selector.piece_frequency[1] == 0

    # Disconnecting peer should decrement frequencies
    selector.unregister_peer("peer_x")
    assert selector.piece_frequency[0] == 0
    assert selector.piece_frequency[7] == 0


def test_already_completed_piece_is_skipped():
    selector = RarestFirstSelector(total_pieces=3)
    selector.record_peer_have("peer_1", 0)
    selector.record_peer_have("peer_1", 1)

    selector.mark_piece_completed(0)

    picked = selector.pick_next_piece("peer_1")
    assert picked == 1