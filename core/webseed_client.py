import asyncio
import urllib.parse
import urllib.request
from typing import List, Optional

from core.piece_manager import PieceManager


class WebSeedClient:
    """
    Implements BEP-0019 (HTTP/FTP WebSeeding - GetRight style).
    Fetches missing pieces directly from HTTP/HTTPS mirror URLs using byte-range
    requests and validates them through PieceManager's SHA-1 pipeline.
    """

    def __init__(self, webseed_urls: List[str], timeout: float = 8.0):
        self.urls = [u.strip() for u in webseed_urls if u.strip().startswith(("http://", "https://"))]
        self.timeout = timeout

    @staticmethod
    def extract_webseeds_from_metadata(metadata: dict) -> List[str]:
        raw_url_list = metadata.get(b"url-list") or metadata.get("url-list")
        extracted: List[str] = []

        if isinstance(raw_url_list, (str, bytes)):
            val = raw_url_list.decode("utf-8", errors="ignore") if isinstance(raw_url_list, bytes) else raw_url_list
            if val.strip():
                extracted.append(val.strip())
        elif isinstance(raw_url_list, list):
            for entry in raw_url_list:
                val = entry.decode("utf-8", errors="ignore") if isinstance(entry, bytes) else str(entry)
                if val.strip():
                    extracted.append(val.strip())

        return extracted

    @staticmethod
    def build_target_url(base_url: str, filename: str) -> str:
        """
        According to BEP-0019: if base_url ends with '/', append the torrent's
        root filename; otherwise use base_url directly as the file endpoint.
        """
        if base_url.endswith("/"):
            return base_url + urllib.parse.quote(filename)
        return base_url

    def _fetch_byte_range_sync(self, url: str, start_byte: int, end_byte_inclusive: int) -> Optional[bytes]:
        headers = {
            "User-Agent": "Py-BitTorrent/1.0",
            "Range": f"bytes={start_byte}-{end_byte_inclusive}"
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = getattr(resp, "status", 200)
                if status not in (200, 206):
                    return None
                data = resp.read()
                expected_len = (end_byte_inclusive - start_byte) + 1
                if len(data) == expected_len:
                    return data
                if status == 200 and len(data) > end_byte_inclusive:
                    return data[start_byte:end_byte_inclusive + 1]
                return None
        except Exception:
            return None

    async def download_piece_from_webseed(self, manager: PieceManager, piece_idx: int) -> bool:
        """
        Downloads an entire missing piece from available HTTP WebSeeds,
        feeds blocks into PieceManager, and verifies SHA-1 integrity.
        """
        if not self.urls or not (0 <= piece_idx < manager.num_pieces):
            return False
        if manager.have_pieces[piece_idx]:
            return True

        piece_size = manager.get_piece_size(piece_idx)
        start_offset = piece_idx * manager.piece_length
        end_offset = start_offset + piece_size - 1

        for base_url in self.urls:
            target_url = self.build_target_url(base_url, manager.filename)
            piece_bytes = await asyncio.to_thread(
                self._fetch_byte_range_sync,
                target_url,
                start_offset,
                end_offset
            )
            if piece_bytes is None or len(piece_bytes) != piece_size:
                continue

            # Feed into PieceManager's block tracker and SHA-1 verification pipeline
            tracker = manager.trackers[piece_idx]
            block_step = manager.block_size
            for off in range(0, piece_size, block_step):
                chunk = piece_bytes[off:off + block_step]
                tracker.mark_block_received(off)
                manager.writer.receive_block(piece_idx, off, chunk)

            if tracker.is_piece_complete():
                is_valid = manager.writer.verify_and_save_piece(piece_idx)
                if is_valid:
                    manager.have_pieces[piece_idx] = True
                    manager.selector.mark_piece_completed(piece_idx)
                    manager._persist_resume_state()
                    return True
                else:
                    for b in tracker.blocks:
                        b.reset()
                    manager.selector.mark_piece_failed(piece_idx)

        return False