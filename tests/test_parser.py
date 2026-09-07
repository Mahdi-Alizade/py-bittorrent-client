import pytest
from core.parser import BDecoder, TorrentEncoder


class TestBDecoder:
    def test_decode_integer(self):
        assert BDecoder(b"i42e").decode() == 42
        assert BDecoder(b"i-42e").decode() == -42
        assert BDecoder(b"i0e").decode() == 0

    def test_decode_integer_non_canonical_leading_zero(self):
        with pytest.raises(ValueError, match="Non-canonical representation"):
            BDecoder(b"i03e").decode()

    def test_decode_string(self):
        assert BDecoder(b"4:spam").decode() == "spam"
        assert BDecoder(b"0:").decode() == ""

    def test_decode_list(self):
        assert BDecoder(b"l4:spami42ee").decode() == ["spam", 42]
        assert BDecoder(b"le").decode() == []

    def test_decode_dict(self):
        encoded = b"d3:cow3:moo4:spam4:eggse"
        expected = {"cow": "moo", "spam": "eggs"}
        assert BDecoder(encoded).decode() == expected

    def test_decode_invalid_marker(self):
        with pytest.raises(ValueError, match="Unknown bencoding marker"):
            BDecoder(b"x123").decode()


class TestTorrentEncoder:
    def test_encode_integer(self):
        assert TorrentEncoder.encode(42) == b"i42e"
        assert TorrentEncoder.encode(-42) == b"i-42e"
        assert TorrentEncoder.encode(0) == b"i0e"

    def test_encode_string(self):
        assert TorrentEncoder.encode("spam") == b"4:spam"
        assert TorrentEncoder.encode(b"spam") == b"4:spam"

    def test_encode_list(self):
        data = ["spam", 42]
        assert TorrentEncoder.encode(data) == b"l4:spami42ee"

    def test_encode_dict(self):
        data = {"cow": "moo", "spam": "eggs"}
        assert TorrentEncoder.encode(data) == b"d3:cow3:moo4:spam4:eggse"

    def test_encode_unsupported_type(self):
        with pytest.raises(ValueError, match="Unsupported type"):
            TorrentEncoder.encode(3.14)