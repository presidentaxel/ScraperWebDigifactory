"""Rate limiter per domain."""
import asyncio
import logging
import time
from collections import defaultdict
from typing import Dict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter that tracks requests per domain."""

    def __init__(self, rate_per_second: float):
        self.rate_per_second = rate_per_second
        self.min_interval = 1.0 / rate_per_second if rate_per_second > 0 else 0
        self._last_request: Dict[str, float] = defaultdict(lambda: 0.0)
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    async def acquire(self, url: str) -> None:
        """Wait if necessary to respect rate limit."""
        domain = self._get_domain(url)
        async with self._locks[domain]:
            last = self._last_request[domain]
            now = time.time()
            elapsed = now - last

            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                await asyncio.sleep(wait_time)

            self._last_request[domain] = time.time()

