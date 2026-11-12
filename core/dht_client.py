import asyncio
import os
import socket
import struct
from typing import Dict, List, Optional, Set, Tuple
from colorama import Fore, Style

from core.dht_routing import DHTNode, KademliaRoutingTable
from core.parser import BDecoder, TorrentEncoder
from core.pex_protocol import PeerExchangeProtocol


DEFAULT_BOOTSTRAP_NODES = [
    ("router.bittorrent.com", 6881),
    ("dht.transmissionbt.com", 6881),
    ("router.utorrent.com", 6881),
]


class KRPCProtocol:
    """
    Encodes and decodes BEP-0005 KRPC UDP messages (ping, find_node, get_peers).
    """

    @staticmethod
    def build_ping_query(transaction_id: bytes, sender_id: bytes) -> bytes:
        msg = {
            "t": transaction_id,
            "y": "q",
            "q": "ping",
            "a": {"id": sender_id}
        }
        return TorrentEncoder.encode(msg)

    @staticmethod
    def build_find_node_query(transaction_id: bytes, sender_id: bytes, target_id: bytes) -> bytes:
        msg = {
            "t": transaction_id,
            "y": "q",
            "q": "find_node",
            "a": {
                "id": sender_id,
                "target": target_id
            }
        }
        return TorrentEncoder.encode(msg)

    @staticmethod
    def build_get_peers_query(transaction_id: bytes, sender_id: bytes, info_hash: bytes) -> bytes:
        msg = {
            "t": transaction_id,
            "y": "q",
            "q": "get_peers",
            "a": {
                "id": sender_id,
                "info_hash": info_hash
            }
        }
        return TorrentEncoder.encode(msg)

    @staticmethod
    def parse_response(raw_packet: bytes) -> Optional[dict]:
        try:
            decoded = BDecoder(raw_packet).decode()
            if not isinstance(decoded, dict):
                return None

            msg_type = decoded.get(b"y") or decoded.get("y")
            if msg_type not in (b"r", "r"):
                return None

            resp_dict = decoded.get(b"r") or decoded.get("r")
            if not isinstance(resp_dict, dict):
                return None

            result = {
                "transaction_id": decoded.get(b"t") or decoded.get("t"),
                "sender_id": resp_dict.get(b"id") or resp_dict.get("id"),
                "token": resp_dict.get(b"token") or resp_dict.get("token"),
                "nodes": [],
                "peers": []
            }

            raw_nodes = resp_dict.get(b"nodes") or resp_dict.get("nodes")
            if raw_nodes:
                if isinstance(raw_nodes, str):
                    raw_nodes = raw_nodes.encode("latin-1")
                result["nodes"] = KademliaRoutingTable.parse_compact_nodes(raw_nodes)

            raw_values = resp_dict.get(b"values") or resp_dict.get("values")
            if raw_values and isinstance(raw_values, list):
                extracted_peers: List[Tuple[str, int]] = []
                for item in raw_values:
                    if isinstance(item, str):
                        item = item.encode("latin-1")
                    if isinstance(item, bytes) and len(item) == 6:
                        peers = PeerExchangeProtocol.decode_compact_peers(item)
                        extracted_peers.extend(peers)
                result["peers"] = extracted_peers

            return result
        except Exception:
            return None


class DHTCrawler:
    """
    Iterative Kademlia DHT lookup engine to discover peers for a given info_hash
    without relying on centralized trackers.
    """

    def __init__(self, local_id: Optional[bytes] = None):
        self.routing_table = KademliaRoutingTable(local_node_id=local_id)

    def discover_peers_sync(
        self,
        info_hash: bytes,
        bootstrap_nodes: Optional[List[Tuple[str, int]]] = None,
        max_rounds: int = 3,
        timeout: float = 2.5
    ) -> List[Tuple[str, int]]:
        """
        Performs iterative get_peers queries over UDP starting from bootstrap routers.
        """
        routers = bootstrap_nodes if bootstrap_nodes is not None else DEFAULT_BOOTSTRAP_NODES
        discovered_peers: Set[Tuple[str, int]] = set()
        queried_addrs: Set[Tuple[str, int]] = set()
        candidate_addrs: List[Tuple[str, int]] = []

        for host, port in routers:
            try:
                resolved_ip = socket.gethostbyname(host)
                candidate_addrs.append((resolved_ip, port))
            except Exception:
                continue

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)

        try:
            for _ in range(max_rounds):
                batch = []
                for addr in candidate_addrs:
                    if addr not in queried_addrs:
                        batch.append(addr)
                        queried_addrs.add(addr)
                    if len(batch) >= 8:
                        break

                if not batch:
                    break

                for target_addr in batch:
                    tx_id = os.urandom(2)
                    query_pkt = KRPCProtocol.build_get_peers_query(
                        transaction_id=tx_id,
                        sender_id=self.routing_table.local_id,
                        info_hash=info_hash
                    )
                    try:
                        sock.sendto(query_pkt, target_addr)
                    except Exception:
                        continue

                # Collect responses within timeout window
                for _ in range(len(batch) * 2):
                    try:
                        data, _ = sock.recvfrom(4096)
                        parsed = KRPCProtocol.parse_response(data)
                        if parsed is None:
                            continue

                        for peer_tuple in parsed["peers"]:
                            discovered_peers.add(peer_tuple)

                        for node in parsed["nodes"]:
                            self.routing_table.add_node(node)
                            node_addr = (node.ip, node.port)
                            if node_addr not in queried_addrs and node_addr not in candidate_addrs:
                                candidate_addrs.append(node_addr)
                    except socket.timeout:
                        break
                    except Exception:
                        continue

                if len(discovered_peers) >= 30:
                    break
        finally:
            sock.close()

        return list(discovered_peers)