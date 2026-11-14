import json
import os
from pathlib import Path
from typing import Dict, List, Optional


class ResumeStateManager:
    """
    Persists and restores download progress (completed pieces bitmask and metadata)
    using atomic file replacement to support instant Fast-Resume across restarts.
    """

    def __init__(self, info_hash_hex: str, state_dir: str = "downloads/.resume"):
        self.info_hash_hex = info_hash_hex.lower()
        self.state_dir = Path(state_dir)
        self.state_file = self.state_dir / f"{self.info_hash_hex}.json"

    def save_state(self, filename: str, num_pieces: int, have_pieces: List[bool]) -> bool:
        """
        Atomically saves the current piece completion array to disk.
        """
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            bitmask_str = "".join("1" if flag else "0" for flag in have_pieces)

            payload = {
                "info_hash": self.info_hash_hex,
                "filename": filename,
                "num_pieces": num_pieces,
                "bitmask": bitmask_str
            }

            temp_file = self.state_dir / f"{self.info_hash_hex}.tmp"
            temp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(temp_file, self.state_file)
            return True
        except Exception:
            return False

    def load_state(self, expected_num_pieces: int) -> Optional[List[bool]]:
        """
        Loads saved piece completion flags if valid and matching expected piece count.
        """
        if not self.state_file.exists():
            return None

        try:
            raw_text = self.state_file.read_text(encoding="utf-8")
            data: Dict = json.loads(raw_text)

            if data.get("info_hash") != self.info_hash_hex:
                return None

            saved_count = int(data.get("num_pieces", -1))
            bitmask_str = str(data.get("bitmask", ""))

            if saved_count != expected_num_pieces or len(bitmask_str) != expected_num_pieces:
                return None

            restored_pieces: List[bool] = []
            for ch in bitmask_str:
                if ch == "1":
                    restored_pieces.append(True)
                elif ch == "0":
                    restored_pieces.append(False)
                else:
                    return None

            return restored_pieces
        except Exception:
            return None

    def clear_state(self):
        """Removes the resume file when no longer needed."""
        try:
            if self.state_file.exists():
                self.state_file.unlink()
        except Exception:
            pass