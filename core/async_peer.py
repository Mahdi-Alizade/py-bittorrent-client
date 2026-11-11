import asyncio
import struct
from typing import Optional, Tuple
from colorama import Fore, Style

from core.protocol_messages import TorrentMessage

PROTOCOL_IDENTIFIER = b"BitTorrent protocol"


class AsyncPeerConnection:
    """
    Manages an asynchronous TCP connection and BEP-3 message loop for a single peer.
    """

    def __init__(self, ip: str, port: int, info_hash: bytes, peer_id: bytes, timeout: float = 6.0):
        self.ip = ip
        self.port = port
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.timeout = timeout

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.is_choked = True
        self.is_connected = False
        self.peer_id_str = f"{ip}:{port}"

    async def connect_and_handshake(self) -> bool:
        try:
            connect_task = asyncio.open_connection(self.ip, self.port)
            reader, writer = await asyncio.wait_for(connect_task, timeout=self.timeout)
            self.reader = reader
            self.writer = writer

            # Build standard 68-byte handshake payload
            pstrlen = len(PROTOCOL_IDENTIFIER)
            reserved = b"\x00" * 8
            handshake_payload = struct.pack(
                ">B19s8s20s20s",
                pstrlen,
                PROTOCOL_IDENTIFIER,
                reserved,
                self.info_hash,
                self.peer_id
            )

            self.writer.write(handshake_payload)
            await self.writer.drain()

            # Read exactly 68 bytes response
            read_task = self.reader.readexactly(68)
            response = await asyncio.wait_for(read_task, timeout=self.timeout)

            resp_pstrlen = response[0]
            resp_pstr = response[1:1 + resp_pstrlen]
            resp_hash = response[1 + resp_pstrlen + 8:1 + resp_pstrlen + 8 + 20]

            if resp_pstr == PROTOCOL_IDENTIFIER and resp_hash == self.info_hash:
                self.is_connected = True
                return True
            else:
                await self.close()
                return False

        except Exception:
            await self.close()
            return False

    async def send_message(self, message_data: bytes) -> bool:
        if not self.is_connected or self.writer is None:
            return False
        try:
            self.writer.write(message_data)
            await self.writer.drain()
            return True
        except Exception:
            self.is_connected = False
            return False

    async def read_message(self) -> Optional[bytes]:
        """Reads a single BEP-3 message framed with 4-byte length prefix."""
        if not self.is_connected or self.reader is None:
            return None
        try:
            length_bytes = await self.reader.readexactly(4)
            msg_length = struct.unpack(">I", length_bytes)[0]

            if msg_length == 0:
                # Keep-alive
                return b"\x00\x00\x00\x00"

            payload = await self.reader.readexactly(msg_length)
            return length_bytes + payload
        except Exception:
            self.is_connected = False
            return None

    async def close(self):
        self.is_connected = False
        if self.writer is not None:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
            self.writer = None
            self.reader = None