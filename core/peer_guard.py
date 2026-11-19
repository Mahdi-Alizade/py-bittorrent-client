import ipaddress
import time
from typing import Dict, List, Optional, Set


class PeerReputationRecord:
    """
    Tracks behavioral metrics and trust score for a single swarm peer.
    """

    def __init__(self, ip: str):
        self.ip = ip
        self.valid_blocks = 0
        self.corrupt_strikes = 0
        self.timeout_strikes = 0
        self.banned_until: float = 0.0
        self.ban_reason: Optional[str] = None

    def is_banned(self) -> bool:
        if self.banned_until <= 0:
            return False
        if time.time() >= self.banned_until:
            self.banned_until = 0.0
            self.ban_reason = None
            return False
        return True

    @property
    def trust_score(self) -> int:
        return (self.valid_blocks * 2) - (self.corrupt_strikes * 25) - (self.timeout_strikes * 5)


class PeerGuard:
    """
    Implements IP/CIDR blocklists, anti-poisoning strike detection,
    and automatic temporary/permanent peer banning.
    """

    MAX_CORRUPT_STRIKES = 2
    DEFAULT_BAN_SECONDS = 3600.0  # 1 hour

    def __init__(self):
        self.records: Dict[str, PeerReputationRecord] = {}
        self.blocked_networks: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        self.explicit_banned_ips: Set[str] = set()

    def add_cidr_block(self, cidr_str: str):
        network = ipaddress.ip_network(cidr_str.strip(), strict=False)
        self.blocked_networks.append(network)

    def ban_ip(self, ip: str, duration_seconds: float = DEFAULT_BAN_SECONDS, reason: str = "Manual ban"):
        clean_ip = ip.strip()
        rec = self.records.setdefault(clean_ip, PeerReputationRecord(clean_ip))
        rec.banned_until = time.time() + duration_seconds
        rec.ban_reason = reason
        if duration_seconds <= 0:
            self.explicit_banned_ips.add(clean_ip)

    def is_ip_allowed(self, ip: str) -> bool:
        clean_ip = ip.strip()
        if clean_ip in self.explicit_banned_ips:
            return False

        rec = self.records.get(clean_ip)
        if rec is not None and rec.is_banned():
            return False

        if self.blocked_networks:
            try:
                addr_obj = ipaddress.ip_address(clean_ip)
                for net in self.blocked_networks:
                    if addr_obj in net:
                        return False
            except ValueError:
                return False

        return True

    def record_valid_contribution(self, ip: str, blocks: int = 1):
        rec = self.records.setdefault(ip.strip(), PeerReputationRecord(ip.strip()))
        rec.valid_blocks += blocks

    def record_corrupt_data(self, ip: str) -> bool:
        """
        Registers a SHA-1 hash failure strike against a peer IP.
        Returns True if the peer crossed the threshold and was auto-banned.
        """
        clean_ip = ip.strip()
        rec = self.records.setdefault(clean_ip, PeerReputationRecord(clean_ip))
        rec.corrupt_strikes += 1

        if rec.corrupt_strikes >= self.MAX_CORRUPT_STRIKES:
            self.ban_ip(
                clean_ip,
                duration_seconds=self.DEFAULT_BAN_SECONDS,
                reason="Anti-poisoning: repeated corrupt piece data"
            )
            return True
        return False

    def record_timeout(self, ip: str):
        clean_ip = ip.strip()
        rec = self.records.setdefault(clean_ip, PeerReputationRecord(clean_ip))
        rec.timeout_strikes += 1

    def get_banned_summary(self) -> List[dict]:
        banned_list: List[dict] = []
        for ip, rec in self.records.items():
            if rec.is_banned():
                banned_list.append({
                    "ip": ip,
                    "reason": rec.ban_reason,
                    "corrupt_strikes": rec.corrupt_strikes,
                    "remaining_seconds": int(rec.banned_until - time.time())
                })
        return banned_list