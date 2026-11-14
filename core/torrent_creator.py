import hashlib
import time
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.parser import TorrentEncoder


class TorrentCreator:
    """
    Creates standard BEP-3 .torrent metainfo files and BEP-0009 magnet URIs
    from either a single file or a multi-file directory hierarchy.
    """

    DEFAULT_PIECE_LENGTH = 256 * 1024  # 256 KB

    def __init__(
        self,
        source_path: str,
        trackers: Optional[List[str]] = None,
        piece_length: int = DEFAULT_PIECE_LENGTH,
        comment: Optional[str] = None,
        created_by: str = "Py-BitTorrent-Client/1.0"
    ):
        self.source = Path(source_path)
        if not self.source.exists():
            raise FileNotFoundError(f"Source path does not exist: {self.source}")

        self.trackers = [t.strip() for t in (trackers or []) if t.strip()]
        self.piece_length = int(piece_length)
        if self.piece_length <= 0:
            raise ValueError("piece_length must be a positive integer")

        self.comment = comment
        self.created_by = created_by

    def _collect_files(self) -> Tuple[List[Path], List[Dict]]:
        """
        Collects physical file paths and builds BEP-3 'files' metadata entries
        sorted deterministically by relative path.
        """
        if self.source.is_file():
            return [self.source], []

        all_files: List[Path] = []
        for item in self.source.rglob("*"):
            if item.is_file():
                all_files.append(item)

        all_files.sort(key=lambda p: p.relative_to(self.source).as_posix())

        if not all_files:
            raise ValueError(f"Directory is empty, cannot create torrent: {self.source}")

        file_entries: List[Dict] = []
        for file_path in all_files:
            rel_parts = list(file_path.relative_to(self.source).parts)
            file_entries.append({
                "length": file_path.stat().st_size,
                "path": rel_parts
            })

        return all_files, file_entries

    def _compute_pieces_hashes(self, ordered_files: List[Path]) -> bytes:
        """
        Streams bytes across all constituent files and computes concatenated
        20-byte SHA-1 hashes for every piece boundary.
        """
        pieces_buffer = bytearray()
        current_chunk = bytearray()

        for file_path in ordered_files:
            with open(file_path, "rb") as f:
                while True:
                    needed = self.piece_length - len(current_chunk)
                    data = f.read(needed)
                    if not data:
                        break
                    current_chunk.extend(data)

                    if len(current_chunk) == self.piece_length:
                        digest = hashlib.sha1(current_chunk).digest()
                        pieces_buffer.extend(digest)
                        current_chunk.clear()

        # Hash final trailing piece if any bytes remain
        if len(current_chunk) > 0:
            digest = hashlib.sha1(current_chunk).digest()
            pieces_buffer.extend(digest)

        return bytes(pieces_buffer)

    def build_metainfo(self) -> Tuple[dict, bytes, str]:
        """
        Builds the complete metainfo dictionary, computes its 20-byte info_hash,
        and generates the corresponding magnet:? URI.
        Returns (metainfo_dict, info_hash_bytes, magnet_uri).
        """
        ordered_files, file_entries = self._collect_files()
        pieces_concat = self._compute_pieces_hashes(ordered_files)

        info_dict: Dict = {
            "name": self.source.name,
            "piece length": self.piece_length,
            "pieces": pieces_concat
        }

        if self.source.is_file():
            info_dict["length"] = self.source.stat().st_size
        else:
            info_dict["files"] = file_entries

        encoded_info = TorrentEncoder.encode(info_dict)
        info_hash = hashlib.sha1(encoded_info).digest()

        metainfo: Dict = {
            "info": info_dict,
            "creation date": int(time.time()),
            "created by": self.created_by
        }

        if self.trackers:
            metainfo["announce"] = self.trackers[0]
            metainfo["announce-list"] = [[tr] for tr in self.trackers]

        if self.comment:
            metainfo["comment"] = self.comment

        magnet_uri = self.generate_magnet_uri(
            info_hash=info_hash,
            display_name=self.source.name,
            trackers=self.trackers
        )

        return metainfo, info_hash, magnet_uri

    def save_torrent_file(self, output_path: str) -> Tuple[Path, bytes, str]:
        """
        Encodes and writes the .torrent file to disk.
        Returns (saved_path, info_hash_bytes, magnet_uri).
        """
        metainfo, info_hash, magnet_uri = self.build_metainfo()
        encoded_torrent = TorrentEncoder.encode(metainfo)

        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(encoded_torrent)

        return out_file, info_hash, magnet_uri

    @staticmethod
    def generate_magnet_uri(
        info_hash: bytes,
        display_name: Optional[str] = None,
        trackers: Optional[List[str]] = None
    ) -> str:
        params = [f"xt=urn:btih:{info_hash.hex()}"]
        if display_name:
            params.append(f"dn={urllib.parse.quote_plus(display_name)}")
        if trackers:
            for tr in trackers:
                params.append(f"tr={urllib.parse.quote(tr, safe='')}")
        return "magnet:?" + "&".join(params)