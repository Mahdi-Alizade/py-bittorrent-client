from main import generate_peer_id, calculate_info_hash


def test_generate_peer_id_length_and_prefix():
    peer_id = generate_peer_id()
    assert len(peer_id) == 20
    assert peer_id.startswith(b"-PY0001-")


def test_calculate_info_hash_exact():
    test_dict = {"name": "sample.txt", "piece length": 16384}
    info_hash = calculate_info_hash(test_dict)
    assert len(info_hash) == 20
    assert isinstance(info_hash, bytes)