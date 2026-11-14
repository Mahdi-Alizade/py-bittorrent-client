import asyncio
import os
import socket
import struct
from typing import Callable, Dict, Optional, Set, Tuple


class LocalPeerDiscovery:
    """
    Implements BEP-0014 (Local Peer Discovery - LPD) over IPv4 UDP Multicast.
    Broadcasts BT-SEARCH announcements to 239.192.152.143:6771 and discovers
    local LAN peers sharing matching info_hashes at gigabit speed.
    """

    MULTICAST_GROUP = "239.192.152.143"
    MULTICAST_PORT = 6771

    def __init__(self, listen_port: int = 6881, cookie: Optional[str] = None):
        self.listen_port = int(listen_port)
        self.cookie = cookie or os.urandom(8).hex()
        self.tracked_hashes: Set[str] = set()
        self.on_peer_discovered: Optional[Callable[[str, str, int], None]] = None
        self._sock: Optional[socket.socket] = None
        self._running = False

    def register_info_hash(self, info_hash: bytes):
        self.tracked_hashes.add(info_hash.hex().lower())

    def unregister_info_hash(self, info_hash: bytes):
        self.tracked_hashes.discard(info_hash.hex().lower())

    def build_announce_packet(self, info_hash: bytes) -> bytes:
        """
        Formats a standard BEP-0014 BT-SEARCH HTTP-like multicast UDP payload.
        """
        hex_hash = info_hash.hex().lower()
        lines = [
            "BT-SEARCH * HTTP/1.1",
            f"Host: {self.MULTICAST_GROUP}:{self.MULTICAST_PORT}",
            f"Port: {self.listen_port}",
            f"Infohash: {hex_hash}",
            f"cookie: {self.cookie}",
            "",
            ""
        ]
        return "\r\n".join(lines).encode("ascii")

    @classmethod
    def parse_announce_packet(cls, raw_data: bytes) -> Optional[Dict[str, str]]:
        """
        Parses an incoming BT-SEARCH packet and extracts Port, Infohash, and cookie.
        """
        try:
            text = raw_data.decode("ascii", errors="ignore")
            lines = [line.strip() for line in text.split("\r\n") if line.strip()]
            if not lines or not lines[0].startswith("BT-SEARCH * HTTP/1.1"):
                return None

            headers: Dict[str, str] = {}
            for line in lines[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            if "port" not in headers or "infohash" not in headers:
                return None

            return {
                "port": headers["port"],
                "infohash": headers["infohash"].lower(),
                "cookie": headers.get("cookie", "")
            }
        except Exception:
            return None

    def broadcast_announce(self, info_hash: bytes):
        """
        Sends a multicast UDP announcement for the specified info_hash.
        """
        packet = self.build_announce_packet(info_hash)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            ttl_bin = struct.pack("b", 1)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl_bin)
            sock.sendto(packet, (self.MULTICAST_GROUP, self.MULTICAST_PORT))
        except Exception:
            pass
        finally:
            sock.close()

    async def start_listener(self):
        """
        Starts an asynchronous UDP multicast listener for incoming LPD announcements.
        """
        if self._running:
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", self.MULTICAST_PORT))
            mreq = struct.pack(
                "4sL",
                socket.inet_aton(self.MULTICAST_GROUP),
                socket.INADDR_ANY
            )
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.setblocking(False)
            self._sock = sock
            self._running = True
        except Exception:
            sock.close()
            self._sock = None
            self._running = False
            return

        loop = asyncio.get_running_loop()
        while self._running and self._sock is not None:
            try:
                data, addr = await loop.sock_recvfrom(self._sock, 2048)
                sender_ip = addr[0]
                parsed = self.parse_announce_packet(data)
                if not parsed:
                    continue

                # Ignore our own multicast broadcasts
                if parsed["cookie"] == self.cookie:
                    continue

                target_hash = parsed["infohash"]
                if target_hash in self.tracked_hashes:
                    peer_port = int(parsed["port"])
                    if self.on_peer_discovered is not None:
                        self.on_peer_discovered(target_hash, sender_ip, peer_port)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.1)

    def stop(self):
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None