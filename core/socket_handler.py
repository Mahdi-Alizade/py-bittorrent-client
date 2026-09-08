import socket
import struct
import sys
from typing import Optional
from colorama import Fore, Style, init

init(autoreset=True)

PROTOCOL_IDENTIFIER = b"BitTorrent protocol"


class PeerConnector:
    """
    Handles TCP connections and binary protocol handshakes (BEP-3) with BitTorrent peers.
    """

    def __init__(self, ip: str, port: int, timeout: float = 6.0):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None

    def connect_and_handshake(self, info_hash: bytes, my_peer_id: bytes) -> bool:
        """
        Connects via TCP and performs BEP-3 Handshake.
        Handshake format: <pstrlen=19><pstr=BitTorrent protocol><reserved=8 bytes><info_hash=20 bytes><peer_id=20 bytes>
        Total length = 1 + 19 + 8 + 20 + 20 = 68 bytes.
        """
        try:
            print(f"{Fore.CYAN}[*] Connecting to {self.ip}:{self.port}...{Style.RESET_ALL}")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.ip, self.port))

            # Build standard 68-byte handshake payload
            pstrlen = len(PROTOCOL_IDENTIFIER)
            reserved = b"\x00" * 8
            handshake_payload = struct.pack(">B19s8s20s20s", pstrlen, PROTOCOL_IDENTIFIER, reserved, info_hash, my_peer_id)

            print(f"{Fore.YELLOW}[*] Sending Handshake ({len(handshake_payload)} bytes)...{Style.RESET_ALL}")
            self.sock.sendall(handshake_payload)

            # Receive 68-byte peer handshake response
            response = self._recv_exact(68)
            if not response:
                print(f"{Fore.RED}[-] Handshake failed: Empty response.{Style.RESET_ALL}")
                self.close()
                return False

            resp_pstrlen = response[0]
            resp_pstr = response[1:1 + resp_pstrlen]
            resp_info_hash = response[1 + resp_pstrlen + 8:1 + resp_pstrlen + 8 + 20]

            if resp_pstr == PROTOCOL_IDENTIFIER and resp_info_hash == info_hash:
                print(f"{Fore.GREEN}[+] Valid BitTorrent Handshake confirmed from {self.ip}:{self.port}!{Style.RESET_ALL}")
                return True
            else:
                print(f"{Fore.RED}[-] Invalid Handshake mismatch. Dropping peer.{Style.RESET_ALL}")
                self.close()
                return False

        except socket.timeout:
            print(f"{Fore.RED}[!] Connection timed out to {self.ip}:{self.port}{Style.RESET_ALL}")
            self.close()
            return False
        except ConnectionRefusedError:
            print(f"{Fore.RED}[!] Connection refused by {self.ip}:{self.port}{Style.RESET_ALL}")
            self.close()
            return False
        except Exception as e:
            print(f"{Fore.RED}[!] Handshake error with {self.ip}:{self.port} - {e}{Style.RESET_ALL}")
            self.close()
            return False

    def send_message(self, message_data: bytes) -> bool:
        """Sends framed message payload over open socket."""
        if not self.sock:
            return False
        try:
            self.sock.sendall(message_data)
            return True
        except Exception:
            return False

    def receive_message(self) -> Optional[bytes]:
        """Reads a single framed message: <4-byte length><payload>."""
        try:
            length_prefix = self._recv_exact(4)
            if not length_prefix:
                return None

            msg_length = struct.unpack(">I", length_prefix)[0]
            if msg_length == 0:
                # Keep-alive message
                return b"\x00\x00\x00\x00"

            payload = self._recv_exact(msg_length)
            if not payload:
                return None

            return length_prefix + payload
        except Exception:
            return None

    def _recv_exact(self, total_bytes: int) -> Optional[bytes]:
        """Guarantees reading exact number of bytes or returns None on disconnect."""
        buffer = bytearray()
        while len(buffer) < total_bytes:
            try:
                chunk = self.sock.recv(total_bytes - len(buffer))
                if not chunk:
                    return None
                buffer.extend(chunk)
            except Exception:
                return None
        return bytes(buffer)

    def close(self):
        """Closes TCP socket cleanly."""
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
            print(f"{Fore.WHITE}[*] Peer connection closed.{Style.RESET_ALL}")