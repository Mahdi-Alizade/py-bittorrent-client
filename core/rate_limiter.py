import asyncio
import time
from typing import Optional


class TokenBucketRateLimiter:
    """
    Asynchronous Token Bucket rate limiter for controlling download/upload bandwidth.
    A rate of 0 or None disables throttling (unlimited bandwidth).
    """

    def __init__(self, max_bytes_per_sec: Optional[int] = None):
        self.max_rate = max_bytes_per_sec if (max_bytes_per_sec and max_bytes_per_sec > 0) else 0
        self.capacity = float(self.max_rate)
        self.tokens = float(self.max_rate)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def set_rate_limit(self, max_bytes_per_sec: Optional[int]):
        self.max_rate = max_bytes_per_sec if (max_bytes_per_sec and max_bytes_per_sec > 0) else 0
        self.capacity = float(self.max_rate)
        self.tokens = float(self.max_rate)
        self.last_refill = time.monotonic()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed > 0:
            added = elapsed * self.max_rate
            self.tokens = min(self.capacity, self.tokens + added)
            self.last_refill = now

    async def acquire(self, num_bytes: int):
        """
        Consumes `num_bytes` tokens from the bucket, sleeping asynchronously
        until enough tokens are replenished if the rate limit is exceeded.
        """
        if self.max_rate <= 0 or num_bytes <= 0:
            return

        async with self._lock:
            while True:
                self._refill()
                if self.tokens >= num_bytes:
                    self.tokens -= num_bytes
                    return

                deficit = num_bytes - self.tokens
                wait_time = deficit / self.max_rate
                await asyncio.sleep(min(wait_time, 0.25))


class BandwidthMonitor:
    """
    Tracks moving-window download and upload throughput (bytes/sec) and calculates ETA.
    """

    def __init__(self, total_bytes: int):
        self.total_bytes = max(1, total_bytes)
        self.total_downloaded = 0
        self.total_uploaded = 0
        self._window_downloaded = 0
        self._window_uploaded = 0
        self._last_sample_time = time.monotonic()
        self.current_down_speed = 0.0
        self.current_up_speed = 0.0

    def record_download(self, num_bytes: int):
        self.total_downloaded += num_bytes
        self._window_downloaded += num_bytes

    def record_upload(self, num_bytes: int):
        self.total_uploaded += num_bytes
        self._window_uploaded += num_bytes

    def sample(self) -> dict:
        now = time.monotonic()
        elapsed = max(0.05, now - self._last_sample_time)

        self.current_down_speed = self._window_downloaded / elapsed
        self.current_up_speed = self._window_uploaded / elapsed

        self._window_downloaded = 0
        self._window_uploaded = 0
        self._last_sample_time = now

        remaining_bytes = max(0, self.total_bytes - self.total_downloaded)
        if self.current_down_speed > 0:
            eta_seconds = int(remaining_bytes / self.current_down_speed)
        else:
            eta_seconds = -1

        return {
            "down_bps": self.current_down_speed,
            "up_bps": self.current_up_speed,
            "downloaded": self.total_downloaded,
            "uploaded": self.total_uploaded,
            "eta_seconds": eta_seconds
        }

    @staticmethod
    def format_speed(bytes_per_sec: float) -> str:
        if bytes_per_sec >= 1024 * 1024:
            return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"
        elif bytes_per_sec >= 1024:
            return f"{bytes_per_sec / 1024:.1f} KB/s"
        return f"{bytes_per_sec:.0f} B/s"

    @staticmethod
    def format_eta(seconds: int) -> str:
        if seconds < 0:
            return "∞"
        mins, secs = divmod(seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}h {mins:02d}m"
        return f"{mins:02d}m {secs:02d}s"