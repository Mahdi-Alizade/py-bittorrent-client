import urllib.parse
import urllib.request
from typing import Dict, List, Tuple
from colorama import Fore, Style

from core.parser import BDecoder
from core.pex_protocol import PeerExchangeProtocol
from core.udp_tracker import UDPTrackerClient


class TrackerClient:
    """
    Unified BitTorrent Tracker client supporting both HTTP/HTTPS (BEP-0003)
    and binary UDP (BEP-0015) announce protocols.
    """

    UDP_EVENT_MAP = {
        "": 0,
        "completed": 1,
        "started": 2,
        "stopped": 3,
    }

    def __init__(self, info_hash: bytes, peer_id: bytes, timeout: float = 5.0):
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.timeout = timeout

    @staticmethod
    def parse_compact_peers(compact_bytes: bytes) -> List[Tuple[str, int]]:
        """Decodes compact 6-byte peer chunks into (ip, port) tuples."""
        return PeerExchangeProtocol.decode_compact_peers(compact_bytes)

    def announce(
        self,
        tracker_url: str,
        port: int = 6881,
        uploaded: int = 0,
        downloaded: int = 0,
        left: int = 0,
        event: str = "started"
    ) -> Dict:
        if not tracker_url:
            return {"peers": []}

        clean_url = tracker_url.strip()
        if clean_url.lower().startswith("udp://"):
            udp_event_code = self.UDP_EVENT_MAP.get(event.lower(), 0)
            udp_client = UDPTrackerClient(
                info_hash=self.info_hash,
                peer_id=self.peer_id,
                timeout=self.timeout
            )
            return udp_client.announce(
                tracker_url=clean_url,
                port=port,
                uploaded=uploaded,
                downloaded=downloaded,
                left=left,
                event=udp_event_code
            )

        return self._announce_http(
            tracker_url=clean_url,
            port=port,
            uploaded=uploaded,
            downloaded=downloaded,
            left=left,
            event=event
        )

    def _announce_http(
        self,
        tracker_url: str,
        port: int = 6881,
        uploaded: int = 0,
        downloaded: int = 0,
        left: int = 0,
        event: str = "started"
    ) -> Dict:
        query_params = [
            ("info_hash", self.info_hash),
            ("peer_id", self.peer_id),
            ("port", str(port)),
            ("uploaded", str(uploaded)),
            ("downloaded", str(downloaded)),
            ("left", str(left)),
            ("compact", "1"),
        ]
        if event:
            query_params.append(("event", event))

        encoded_query = urllib.parse.urlencode(query_params)
        separator = "&" if "?" in tracker_url else "?"
        full_url = f"{tracker_url}{separator}{encoded_query}"

        try:
            req = urllib.request.Request(full_url, headers={"User-Agent": "Py-BitTorrent/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_body = resp.read()

            decoded = BDecoder(raw_body).decode()
            if not isinstance(decoded, dict):
                return {"peers": []}

            failure = decoded.get(b"failure reason") or decoded.get("failure reason")
            if failure:
                return {"peers": [], "error": str(failure)}

            raw_peers = decoded.get(b"peers") or decoded.get("peers")
            peers_list: List[Tuple[str, int]] = []

            if isinstance(raw_peers, bytes):
                peers_list = self.parse_compact_peers(raw_peers)
            elif isinstance(raw_peers, str):
                peers_list = self.parse_compact_peers(raw_peers.encode("latin-1"))
            elif isinstance(raw_peers, list):
                for entry in raw_peers:
                    if isinstance(entry, dict):
                        p_ip = entry.get(b"ip") or entry.get("ip")
                        p_port = entry.get(b"port") or entry.get("port")
                        if isinstance(p_ip, bytes):
                            p_ip = p_ip.decode("utf-8", errors="ignore")
                        if p_ip and p_port:
                            peers_list.append((str(p_ip), int(p_port)))

            interval = int(decoded.get(b"interval") or decoded.get("interval", 1800))
            return {
                "interval": interval,
                "peers": peers_list
            }
        except Exception as err:
            print(f"{Fore.YELLOW}[!] HTTP Tracker announce failed ({tracker_url}): {err}{Style.RESET_ALL}")
            return {"peers": [], "error": str(err)}