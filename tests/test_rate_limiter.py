import asyncio
import time
import pytest
from core.rate_limiter import BandwidthMonitor, TokenBucketRateLimiter


@pytest.mark.asyncio
async def test_token_bucket_throttling():
    # Limit to 10,000 bytes/sec (bucket starts with 10,000 tokens)
    limiter = TokenBucketRateLimiter(max_bytes_per_sec=10000)

    # First 10,000 bytes consume initial capacity immediately
    await limiter.acquire(10000)

    # Next 3,000 bytes should require ~0.3 seconds of replenishment
    start = time.monotonic()
    await limiter.acquire(3000)
    elapsed = time.monotonic() - start

    assert elapsed >= 0.22


@pytest.mark.asyncio
async def test_unlimited_rate_limiter_does_not_block():
    limiter = TokenBucketRateLimiter(max_bytes_per_sec=0)
    start = time.monotonic()
    await limiter.acquire(5_000_000)
    elapsed = time.monotonic() - start

    assert elapsed < 0.05


def test_bandwidth_monitor_telemetry():
    monitor = BandwidthMonitor(total_bytes=10000)
    monitor.record_download(2500)
    monitor.record_upload(1000)

    stats = monitor.sample()
    assert stats["downloaded"] == 2500
    assert stats["uploaded"] == 1000
    assert stats["down_bps"] > 0
    assert BandwidthMonitor.format_speed(2048) == "2.0 KB/s"
    assert BandwidthMonitor.format_eta(125) == "02m 05s"