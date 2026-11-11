import os
from pathlib import Path
from typing import Dict, List, Tuple


class FileSpan:
    def __init__(self, relative_path: Path, length: int, global_start: int):
        self.relative_path = relative_path
        self.length = length
        self.global_start = global_start
        self.global_end = global_start + length


class MultiFileStorageManager:
    """
    Maps a contiguous BitTorrent byte stream across multiple disk files and folders.
    Handles piece boundaries spanning across file edges.
    """

    def __init__(self, base_directory: Path, file_entries: List[Dict]):
        self.base_directory = base_directory
        self.files: List[FileSpan] = []
        self.total_length = 0

        current_offset = 0
        for entry in file_entries:
            file_len = int(entry.get("length", 0))
            raw_path_parts = entry.get("path", [])

            # Path elements can be bytes or str depending on parser
            cleaned_parts = []
            for part in raw_path_parts:
                if isinstance(part, bytes):
                    cleaned_parts.append(part.decode("utf-8", errors="ignore"))
                else:
                    cleaned_parts.append(str(part))

            rel_path = Path(*cleaned_parts)
            span = FileSpan(
                relative_path=rel_path,
                length=file_len,
                global_start=current_offset
            )
            self.files.append(span)
            current_offset += file_len

        self.total_length = current_offset

    def initialize_storage(self):
        """Creates target directory hierarchy and pre-allocates all constituent files."""
        for file_span in self.files:
            full_path = self.base_directory / file_span.relative_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if not full_path.exists() or full_path.stat().st_size != file_span.length:
                with open(full_path, "wb") as f:
                    if file_span.length > 0:
                        f.seek(file_span.length - 1)
                        f.write(b"\x00")

    def write_piece(self, global_offset: int, piece_bytes: bytes) -> bool:
        """
        Splits and writes piece bytes across one or more files according to global offsets.
        """
        piece_len = len(piece_bytes)
        piece_start = global_offset
        piece_end = global_offset + piece_len

        bytes_written = 0
        for file_span in self.files:
            # Check if this file overlaps with the piece byte range
            overlap_start = max(piece_start, file_span.global_start)
            overlap_end = min(piece_end, file_span.global_end)

            if overlap_start < overlap_end:
                slice_offset_in_piece = overlap_start - piece_start
                slice_length = overlap_end - overlap_start
                slice_data = piece_bytes[slice_offset_in_piece : slice_offset_in_piece + slice_length]

                target_file_offset = overlap_start - file_span.global_start
                full_path = self.base_directory / file_span.relative_path

                with open(full_path, "r+b") as target_file:
                    target_file.seek(target_file_offset)
                    target_file.write(slice_data)

                bytes_written += slice_length

        return bytes_written == piece_len

    def read_piece(self, global_offset: int, piece_length: int) -> bytes:
        """
        Reads piece bytes assembled across one or more files based on global offsets.
        """
        piece_start = global_offset
        piece_end = global_offset + piece_length

        output_buffer = bytearray()
        for file_span in self.files:
            overlap_start = max(piece_start, file_span.global_start)
            overlap_end = min(piece_end, file_span.global_end)

            if overlap_start < overlap_end:
                target_file_offset = overlap_start - file_span.global_start
                bytes_to_read = overlap_end - overlap_start
                full_path = self.base_directory / file_span.relative_path

                with open(full_path, "rb") as source_file:
                    source_file.seek(target_file_offset)
                    chunk = source_file.read(bytes_to_read)
                    output_buffer.extend(chunk)

        return bytes(output_buffer)