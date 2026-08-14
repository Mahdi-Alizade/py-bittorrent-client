import sys

class BDecoder:
    """
    Parses BitTorrent's Bencoding format 
    Returns: dictionary, list, integer, or string
    """
    
    def __init__(self, data):
        if isinstance(data, str):
            data = data.encode('latin-1') # Convert text back to bytes
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
        # Format: i<number>e
        end = self.data.index(ord('e'), self.pos + 1)
        number_str = self.data[self.pos + 1:end].decode('latin-1')
        self.pos = end + 1
        
        num = int(number_str)
        if num >= 0 and len(number_str) > 1 and number_str[0] == '0':
            raise ValueError("Non-canonical representation of integer")
        return num

    def _parse_string(self):
        # Format: <length>:<string>
        colon = self.data.index(ord(':'), self.pos)
        length = int(self.data[self.pos:colon].decode('latin-1'))
        self.pos = colon + 1
        
        # Safety check against garbage data
        if length > 1024 * 1024: # Max 1MB per element to avoid DoS
             raise ValueError("String size too large")
            
        string_val = bytes(self.data[self.pos:self.pos + length])
        self.pos += length
        try:
            return string_val.decode('utf-8')
        except UnicodeDecodeError:
            return string_val.decode('latin-1') # Fallback

    def _parse_list(self):
        # Format: l<elements>e
        lst = []
        self.pos += 1 # skip 'l'
        while True:
            peek = self._peek().decode('latin-1', errors='ignore')
            if peek == 'e':
                self.pos += 1
                break
            lst.append(self._parse())
        return lst

    def _parse_dict(self):
        # Format: d<key><value>...e
        dct = {}
        self.pos += 1 # skip 'd'
        while True:
            peek = self._peek().decode('latin-1', errors='ignore')
            if peek == 'e':
                self.pos += 1
                break
            
            key = self._parse()
            # Keys in torrent files must be strings
            if not isinstance(key, str):
                raise ValueError(f"Expected string key in dict, found {type(key)}")
                
            val = self._parse()
            dct[key] = val
            
        return dct