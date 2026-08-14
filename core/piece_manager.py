import sys
from pathlib import Path
from colorama import Fore, Style, init

# اصلاح مسیرها برای اینکه همیشه بتونه پکیج‌های core رو پیدا کنه
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.protocol_messages import TorrentMessage
from core.reassemble import DownloadSession

init(autoreset=True)

class PieceManager:
    """
    قلب تپنده مدیریت دانلود. هماهنگی بین درخواست تکه‌ها، دریافت داده و ذخیره روی دیسک.
    """
    
    def __init__(self, filename: str, piece_length: int, num_pieces: int):
        self.filename = filename
        self.piece_length = piece_length
        self.num_pieces = num_pieces
        self.block_size = 16 * 1024  # سایز استاندارد هر بلاک (۱۶ کیلوبایت)
        
        # وضعیت داخلی
        self.have_bitfield = [False] * num_pieces
        self.received_blocks = {}  # ذخیره موقت تکه‌ها: {نقطه شروع: دیتا}
        
        # موتور ذخیره‌سازی
        self.writer = DownloadSession(filename, piece_length)
        self.writer.initialize_file()
        
    def handle_message(self, raw_data: bytes):
        """تحلیل پیام‌های ورودی و فرستادن به بخش‌های مناسب."""
        if len(raw_data) < 5:
            return
            
        msg_id = raw_data[4]
        
        if msg_id == TorrentMessage.PIECE:
            parsed = TorrentMessage.parse_piece(raw_data)
            if parsed:
                idx, offset, data = parsed
                self._store_block(idx, offset, data)
                
        elif msg_id == TorrentMessage.HAVE:
            try:
                # خواندن ایندکس تکه از پیام HAVE
                piece_idx = int.from_bytes(raw_data[5:9], 'big')
                self.have_bitfield[piece_idx] = True
                print(f"{Fore.CYAN}[<-] Peer HAS Piece #{piece_idx}{Style.RESET_ALL}")
            except Exception:
                pass
                
    def _store_block(self, piece_idx: int, offset: int, block_data: bytes):
        """دریافت یک بلاک داده و نوشتن آن در استریم."""
        self.received_blocks[(piece_idx, offset)] = block_data
        self.writer.receive_block(piece_idx, offset, block_data)
        
        # تلاش برای بررسی صحت و تکمیل تکه
        self._verify_piece_integrity(piece_idx)

    def _verify_piece_integrity(self, piece_idx: int):
        """اگر تمام بلاک‌های یک تکه کامل شد، عملیات تایید را انجام میدهد."""
        # محاسبه تعداد بلاک‌های مورد نیاز برای پر کردن یک تکه
        required_blocks = list(range(0, self.piece_length, self.block_size))
        present_offsets = [off for (pi, off) in self.received_blocks.keys() if pi == piece_idx]
        
        # اگر همه بلاک‌های این تکه رسیدند (در نسخه واقعی هش SHA1 چک میشه)
        if set(present_offsets) == set(required_blocks):
            print(f"{Fore.MAGENTA}[*] Full piece #{piece_idx} assembled. Writing to disk...{Style.RESET_ALL}")
            
            self.writer.verify_and_save_piece(piece_idx)
            self.have_bitfield[piece_idx] = True
            self.received_blocks.clear()
            print(f"{Fore.GREEN}[+] SUCCESS: Piece #{piece_idx} saved successfully.{Style.RESET_ALL}")

    def get_request_packet(self, piece_index: int) -> bytes:
        """ساخت پکت درخواست رسمی برای ارسال به ساکت."""
        return TorrentMessage.create_request(piece_index, 0, self.block_size)

    def status_report(self):
        """گزارش وضعیت دانلود."""
        total_downloaded = sum(1 for s in self.have_bitfield if s)
        pct = (total_downloaded / self.num_pieces * 100) if self.num_pieces > 0 else 0
        return f"{total_downloaded}/{self.num_pieces} ({pct:.1f}%)"