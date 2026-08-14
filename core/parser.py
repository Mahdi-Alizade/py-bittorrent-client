import sys

class BDecoder:
    """
    Parses BitTorrent's Bencoding format 
    Returns: dictionary, list, integer, or string
    """
    
    def __init__(self, data):
        if isinstance(data, str):
            data = data.encode('latin-1')
        self.data = bytearray(data)
        self.pos = 0

    def decode(self):
        return self._parse()

    def _peek(self):
        return self.data[self.pos:self.pos+1]

    def _parse(self):
        key = self._peek().decode('latin-1')
        
        if key.isdigit():
            return self._parse_string()
        elif key == 'i':
            return self._parse_int()
        elif key == 'l':
            return self._parse_list()
        elif key == 'd':
            return self._parse_dict()
        else:
            raise ValueError(f"Unknown bencoding marker: {key}")

    def _parse_int(self):
        end = self.data.index(ord('e'), self.pos + 1)
        number_str = self.data[self.pos + 1:end].decode('latin-1')
        self.pos = end + 1
        
        num = int(number_str)
        if num >= 0 and len(number_str) > 1 and number_str[0] == '0':
            raise ValueError("Non-canonical representation of integer")
        return num

    def _parse_string(self):
        colon = self.data.index(ord(':'), self.pos)
        length = int(self.data[self.pos:colon].decode('latin-1'))
        self.pos = colon + 1
        
        if length > 1024 * 1024:
             raise ValueError("String size too large")
            
        string_val = bytes(self.data[self.pos:self.pos + length])
        self.pos += length
        try:
            return string_val.decode('utf-8')
        except UnicodeDecodeError:
            return string_val.decode('latin-1')

    def _parse_list(self):
        lst = []
        self.pos += 1
        while True:
            peek = self._peek().decode('latin-1', errors='ignore')
            if peek == 'e':
                self.pos += 1
                break
            lst.append(self._parse())
        return lst

    def _parse_dict(self):
        dct = {}
        self.pos += 1
        while True:
            peek = self._peek().decode('latin-1', errors='ignore')
            if peek == 'e':
                self.pos += 1
                break
            
            key = self._parse()
            if not isinstance(key, str):
                raise ValueError(f"Expected string key in dict, found {type(key)}")
                
            val = self._parse()
            dct[key] = val
            
        return dct


class TorrentEncoder:
    """
    Recursive Bencoding Encoder (Updated for str/bytes compatibility)
    """
    
    @staticmethod
    def encode(val):
        if isinstance(val, dict):
            # Sort keys strictly by their UTF-8 byte representation
            items = sorted(val.items(), key=lambda item: str(item[0]).encode('utf-8'))
            result = bytearray(b'd')
            for k, v in items:
                # Force keys to bytes for strict compliance
                k_bytes = k.encode('utf-8') if isinstance(k, str) else k
                result.extend(TorrentEncoder.encode(k_bytes))
                result.extend(TorrentEncoder.encode(v))
            result.extend(b'e')
            return bytes(result)
        
        elif isinstance(val, list):
            result = bytearray(b'l')
            for item in val:
                result.extend(TorrentEncoder.encode(item))
            result.extend(b'e')
            return bytes(result)
        
        elif isinstance(val, int):
            return f'i{val}e'.encode()
        
        elif isinstance(val, str):
            encoded = val.encode('utf-8')
            return f'{len(encoded)}:'.encode() + encoded
        
        elif isinstance(val, bytes):
            return f'{len(val)}:'.encode() + val
        
        else:
            raise ValueError(f"Unsupported type for encoding: {type(val)}")