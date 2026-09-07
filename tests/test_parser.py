import pytest
from core.parser import BencodeParser


class TestBencodeParser:
    @pytest.fixture
    def parser(self):
        return BencodeParser()

    def test_decode_integer(self, parser):
        assert parser.decode(b"i42e") == 42
        assert parser.decode(b"i-42e") == -42
        assert parser.decode(b"i0e") == 0

    def test_decode_string(self, parser):
        assert parser.decode(b"4:spam") == b"spam"
        assert parser.decode(b"0:") == b""

    def test_decode_list(self, parser):
        assert parser.decode(b"l4:spami42ee") == [b"spam", 42]
        assert parser.decode(b"le") == []

    def test_decode_dict(self, parser):
        encoded = b"d3:cow3:moo4:spam4:eggse"
        expected = {b"cow": b"moo", b"spam": b"eggs"}
        assert parser.decode(encoded) == expected

    def test_encode_integer(self, parser):
        assert parser.encode(42) == b"i42e"
        assert parser.encode(-42) == b"i-42e"
        assert parser.encode(0) == b"i0e"

    def test_encode_string(self, parser):
        assert parser.encode(b"spam") == b"4:spam"
        assert parser.encode("spam") == b"4:spam"

    def test_encode_list(self, parser):
        data = [b"spam", 42]
        assert parser.encode(data) == b"l4:spami42ee"

    def test_encode_dict(self, parser):
        data = {b"cow": b"moo", b"spam": b"eggs"}
        assert parser.encode(data) == b"d3:cow3:moo4:spam4:eggse"

    def test_invalid_input_raises_error(self, parser):
        with pytest.raises(Exception):
            parser.decode(b"invalid_bencode")