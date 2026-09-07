import random
import socket
import struct
import urllib.parse
from typing import List, Tuple, Dict, Any
from colorama import Fore, Style
import requests

from core.parser import BDecoder


class TrackerClient:
    """
    Handles communication with BitTorrent Trackers over both HTTP(S) and UDP.
    Implements BEP-03 (HTTP Tracker) and BEP-15 (UDP Tracker Protocol).
    """

    def __init__(self, info_hash: bytes, peer_id: bytes, port: int = 6881):
        if isinstance(info_hash, str):
            self.info_hash = info_hash.encode('latin-1')
        else:
            self.info_hash = info_hash

        if isinstance(peer_id, str):
            self.peer_id = peer_id.encode('latin-1')
        else:
            self.peer_id = peer_id

        self.port = port

    @staticmethod
    def parse_compact_peers(peers_binary: bytes) -> List[Tuple[str, int]]:
        """
        Parses compact 6-byte peer format (BEP-23):
        4 bytes IPv4 address + 2 bytes Big-Endian port.
        """
        peers = []
        if not peers_binary or len(peers_binary) % 6 != 0:
            return peers

        for i in range(0, len(peers_binary), 6):
            chunk = peers_binary[i:i + 6]
            ip_bytes = chunk[:4]
            port_bytes = chunk[4:6]
            ip = socket.inet_ntoa(ip_bytes)
            port = struct.unpack('>H', port_bytes)[0]
            peers.append((ip, port))

        return peers

    def announce(self, tracker_url: str, left: int = 1000) -> Dict[str, Any]:
        """
        Routes the announce request based on tracker protocol scheme (http/https vs udp).
        """
        parsed = urllib.parse.urlparse(tracker_url)
        scheme = parsed.scheme.lower()

        if scheme in ("http", "https"):
            return self._announce_http(tracker_url, left)
        elif scheme == "udp":
            return self._announce_udp(parsed.hostname, parsed.port or 80, left)
        else:
            print(f"{Fore.RED}[-] Unsupported tracker scheme: {scheme}{Style.RESET_ALL}")
            return {"error": f"Unsupported scheme {scheme}", "peers": []}

    def _announce_http(self, tracker_url: str, left: int) -> Dict[str, Any]:
        """
        Sends HTTP GET announce request and decodes the Bencoded response.
        """
        try:
            print(f"{Fore.CYAN}[*] Contacting HTTP Tracker: {tracker_url}{Style.RESET_ALL}")
            params = {
                'info_hash': self.info_hash,
                'peer_id': self.peer_id,
                'port': self.port,
                'uploaded': 0,
                'downloaded': 0,
                'left': left,
                'compact': 1,
                'numwant': 50
            }

            response = requests.get(tracker_url, params=params, timeout=10)
            if response.status_code != 200:
                print(f"{Fore.RED}[-] Tracker HTTP Error: Status {response.status_code}{Style.RESET_ALL}")
                return {"error": f"Status {response.status_code}", "peers": []}

            # Response is Bencoded bytes
            decoded = BDecoder(response.content).decode()
            if not isinstance(decoded, dict):
                return {"error": "Invalid tracker response format", "peers": []}

            if "failure reason" in decoded:
                reason = decoded["failure reason"]
                print(f"{Fore.RED}[-] Tracker rejected: {reason}{Style.RESET_ALL}")
                return {"error": reason, "peers": []}

            interval = decoded.get("interval", 30)
            raw_peers = decoded.get("peers", b"")

            if isinstance(raw_peers, str):
                raw_peers = raw_peers.encode('latin-1')

            peers_list = self.parse_compact_peers(raw_peers)
            print(f"{Fore.GREEN}[+] Tracker success! Peers found: {len(peers_list)}{Style.RESET_ALL}")

            return {
                "interval": int(interval),
                "peers": peers_list
            }

        except Exception as e:
            print(f"{Fore.RED}[-] HTTP Tracker exception: {e}{Style.RESET_ALL}")
            return {"error": str(e), "peers": []}

    def _announce_udp(self, host: str, port: int, left: int) -> Dict[str, Any]:
        """
        Implements BEP-15 UDP Tracker Protocol:
        1. Connect Request -> Connect Response (Get connection_id)
        2. Announce Request -> Announce Response (Get peer list)
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(8.0)

        try:
            print(f"{Fore.CYAN}[*] Contacting UDP Tracker: {host}:{port}{Style.RESET_ALL}")
            resolved_ip = socket.gethostbyname(host)

            # --- Step 1: Connect Request ---
            # protocol_id: 0x41727101980, action: 0 (connect), transaction_id
            protocol_id = 0x41727101980
            action_connect = 0
            transaction_id = random.randint(0, 0x7FFFFFFF)

            connect_packet = struct.pack('>QII', protocol_id, action_connect, transaction_id)
            sock.sendto(connect_packet, (resolved_ip, port))

            res_data, _ = sock.recvfrom(2048)
            if len(res_data) < 16:
                return {"error": "Connect response too short", "peers": []}

            action, resp_transaction_id, connection_id = struct.unpack('>IIQ', res_data[:16])
            if resp_transaction_id != transaction_id or action != 0:
                return {"error": "Invalid connect transaction or action", "peers": []}

            # --- Step 2: Announce Request ---
            action_announce = 1
            transaction_id = random.randint(0, 0x7FFFFFFF)
            downloaded = 0
            uploaded = 0
            event = 0
            ip_address = 0
            key = random.randint(0, 0xFFFF)
            num_want = 50

            announce_packet = struct.pack(
                '>QII20s20sQQQIIIiH',
                connection_id,
                action_announce,
                transaction_id,
                self.info_hash[:20],
                self.peer_id[:20],
                downloaded,
                left,
                uploaded,
                event,
                ip_address,
                key,
                num_want,
                self.port
            )
            sock.sendto(announce_packet, (resolved_ip, port))

            res_data, _ = sock.recvfrom(2048)
            if len(res_data) < 20:
                return {"error": "Announce response too short", "peers": []}

            action, resp_transaction_id, interval, leechers, seeders = struct.unpack('>IIIII', res_data[:20])
            if resp_transaction_id != transaction_id or action != 1:
                return {"error": "Invalid announce transaction or action", "peers": []}

            peers_binary = res_data[20:]
            peers_list = self.parse_compact_peers(peers_binary)

            print(f"{Fore.GREEN}[+] UDP Tracker success! Seeds: {seeders}, Peers: {len(peers_list)}{Style.RESET_ALL}")
            return {
                "interval": interval,
                "seeders": seeders,
                "leechers": leechers,
                "peers": peers_list
            }

        except socket.timeout:
            print(f"{Fore.RED}[-] UDP Tracker timeout{Style.RESET_ALL}")
            return {"error": "Tracker timeout", "peers": []}
        except Exception as e:
            print(f"{Fore.RED}[-] UDP Tracker error: {e}{Style.RESET_ALL}")
            return {"error": str(e), "peers": []}
        finally:
            sock.close()