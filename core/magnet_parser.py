import base64
import urllib.parse
from typing import Dict, List, Optional


class MagnetLinkData:
    def __init__(
        self,
        info_hash: bytes,
        display_name: Optional[str] = None,
        trackers: Optional[List[str]] = None
    ):
        self.info_hash = info_hash
        self.display_name = display_name or f"magnet_{info_hash.hex()[:12]}"
        self.trackers = trackers or []

    @property
    def info_hash_hex(self) -> str:
        return self.info_hash.hex()


class MagnetURIParser:
    """
    Parses BitTorrent Magnet links according to BEP-0009.
    Supports both 40-char Hex and 32-char Base32 info-hashes.
    """

    @staticmethod
    def parse(magnet_uri: str) -> MagnetLinkData:
        if not magnet_uri or not magnet_uri.startswith("magnet:?"):
            raise ValueError("Invalid magnet URI: must start with 'magnet:?'")

        parsed_url = urllib.parse.urlparse(magnet_uri)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # 1. Extract Exact Topic (xt) containing urn:btih:<hash>
        xt_values = query_params.get("xt", [])
        raw_hash_str = None

        for xt in xt_values:
            lower_xt = xt.lower()
            if lower_xt.startswith("urn:btih:"):
                raw_hash_str = xt[9:].strip()
                break

        if not raw_hash_str:
            raise ValueError("Invalid magnet URI: missing 'urn:btih:' exact topic")

        # 2. Decode hash string (40-char hex vs 32-char base32)
        info_hash_bytes = MagnetURIParser._decode_btih_hash(raw_hash_str)

        # 3. Extract Display Name (dn)
        dn_list = query_params.get("dn", [])
        display_name = None
        if len(dn_list) > 0:
            display_name = urllib.parse.unquote_plus(dn_list[0])

        # 4. Extract Tracker URLs (tr)
        tr_list = query_params.get("tr", [])
        cleaned_trackers = []
        for tracker in tr_list:
            unquoted_tr = urllib.parse.unquote(tracker).strip()
            if unquoted_tr and unquoted_tr not in cleaned_trackers:
                cleaned_trackers.append(unquoted_tr)

        return MagnetLinkData(
            info_hash=info_hash_bytes,
            display_name=display_name,
            trackers=cleaned_trackers
        )

    @staticmethod
    def _decode_btih_hash(hash_str: str) -> bytes:
        length = len(hash_str)

        if length == 40:
            try:
                return bytes.fromhex(hash_str)
            except ValueError as err:
                raise ValueError(f"Malformed hex info-hash in magnet link: {err}")

        elif length == 32:
            try:
                upper_b32 = hash_str.upper()
                return base64.b32decode(upper_b32)
            except Exception as err:
                raise ValueError(f"Malformed base32 info-hash in magnet link: {err}")

        else:
            raise ValueError(f"Unsupported BTIH hash length: {length} (expected 40 hex or 32 base32)")