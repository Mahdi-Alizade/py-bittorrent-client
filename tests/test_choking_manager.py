from core.choking_manager import TitForTatChoker


def test_tit_for_tat_unchokes_fastest_contributors():
    choker = TitForTatChoker(max_unchoked_slots=3)

    for name in ["peer_slow", "peer_mid", "peer_fast", "peer_super"]:
        choker.register_peer(name)
        choker.set_peer_interested(name, True)

    choker.record_bytes_from_peer("peer_slow", 100)
    choker.record_bytes_from_peer("peer_mid", 5000)
    choker.record_bytes_from_peer("peer_fast", 25000)
    choker.record_bytes_from_peer("peer_super", 90000)

    decisions = choker.evaluate_choke_decisions(is_seeding_mode=False)

    # Top 2 regular slots must be unchoked (choke=False)
    assert decisions["peer_super"] is False
    assert decisions["peer_fast"] is False

    # Total unchoked count must equal 3 (2 regular + 1 optimistic)
    unchoked_total = sum(1 for is_choked in decisions.values() if not is_choked)
    assert unchoked_total == 3


def test_uninterested_peers_remain_choked():
    choker = TitForTatChoker(max_unchoked_slots=2)
    choker.register_peer("idle_peer")
    choker.set_peer_interested("idle_peer", False)
    choker.record_bytes_from_peer("idle_peer", 50000)

    decisions = choker.evaluate_choke_decisions()
    assert decisions["idle_peer"] is True