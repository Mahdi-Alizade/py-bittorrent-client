import os
import socket
import struct
import time
from typing import Dict, List, Optional, Tuple


class DHTNode:
    """
    Represents a single node in the 160-bit Kademlia DHT keyspace.
    """

    def __init__(self, node_id: bytes, ip: str, port: int):
        if len(node_id) != 20:
            raise ValueError("DHT node_id must be exactly 20 bytes")
        self.node_id = node_id
        self.ip = ip
        self.port = int(port)
        self.last_seen = time.time()

    def touch(self):
        self.last_seen = time.time()

    def distance_to(self, target_id: bytes) -> int:
        return KademliaRoutingTable.xor_distance(self.node_id, target_id)

    def to_compact(self) -> bytes:
        """Encodes node into 26-byte compact format: 20-byte ID + 4-byte IP + 2-byte Port."""
        packed_ip = socket.inet_aton(self.ip)
        packed_port = struct.pack(">H", self.port)
        return self.node_id + packed_ip + packed_port

    @classmethod
    def from_compact(cls, compact_26_bytes: bytes) -> "DHTNode":
        if len(compact_26_bytes) != 26:
            raise ValueError("Compact node info must be 26 bytes")
        n_id = compact_26_bytes[:20]
        ip_str = socket.inet_ntoa(compact_26_bytes[20:24])
        port_num = struct.unpack(">H", compact_26_bytes[24:26])[0]
        return cls(node_id=n_id, ip=ip_str, port=port_num)

    def __eq__(self, other):
        if not isinstance(other, DHTNode):
            return False
        return self.node_id == other.node_id and self.ip == other.ip and self.port == other.port

    def __hash__(self):
        return hash((self.node_id, self.ip, self.port))


class KademliaRoutingTable:
    """
    Maintains a 160-bucket Kademlia routing table ordered by XOR distance
    from the local node's 160-bit identifier.
    """

    K_BUCKET_SIZE = 8
    ID_BITS = 160

    def __init__(self, local_node_id: Optional[bytes] = None):
        if local_node_id is not None:
            if len(local_node_id) != 20:
                raise ValueError("Local node_id must be 20 bytes")
            self.local_id = local_node_id
        else:
            self.local_id = os.urandom(20)

        self.buckets: List[List[DHTNode]] = [[] for _ in range(self.ID_BITS)]

    @staticmethod
    def xor_distance(id_a: bytes, id_b: bytes) -> int:
        int_a = int.from_bytes(id_a, "big")
        int_b = int.from_bytes(id_b, "big")
        return int_a ^ int_b

    def get_bucket_index(self, target_id: bytes) -> int:
        dist = self.xor_distance(self.local_id, target_id)
        if dist == 0:
            return 0
        return dist.bit_length() - 1

    def add_node(self, node: DHTNode) -> bool:
        if node.node_id == self.local_id:
            return False

        b_idx = self.get_bucket_index(node.node_id)
        bucket = self.buckets[b_idx]

        # If node already exists, move to tail (most recently seen)
        for existing in bucket:
            if existing.node_id == node.node_id:
                bucket.remove(existing)
                node.touch()
                bucket.append(node)
                return True

        if len(bucket) < self.K_BUCKET_SIZE:
            node.touch()
            bucket.append(node)
            return True

        # Bucket full: evict oldest node if stale (> 15 mins)
        oldest = bucket[0]
        if (time.time() - oldest.last_seen) > 900:
            bucket.pop(0)
            node.touch()
            bucket.append(node)
            return True

        return False

    def find_closest_nodes(self, target_id: bytes, count: int = 8) -> List[DHTNode]:
        all_nodes: List[DHTNode] = []
        for bucket in self.buckets:
            for node in bucket:
                all_nodes.append(node)

        all_nodes.sort(key=lambda n: n.distance_to(target_id))
        return all_nodes[:count]

    @staticmethod
    def parse_compact_nodes(compact_nodes_bytes: bytes) -> List[DHTNode]:
        nodes: List[DHTNode] = []
        if not compact_nodes_bytes or len(compact_nodes_bytes) % 26 != 0:
            return nodes

        total = len(compact_nodes_bytes)
        offset = 0
        while offset < total:
            chunk = compact_nodes_bytes[offset:offset + 26]
            try:
                node = DHTNode.from_compact(chunk)
                nodes.append(node)
            except Exception:
                pass
            offset += 26
        return nodes