"""Metrics tracking for scraping progress."""
import time
import logging
from collections import defaultdict
from typing import Dict

logger = logging.getLogger(__name__)


class Metrics:
    """Track scraping metrics and calculate ETA."""

    def __init__(self, total: int):
        self.total = total
        self.start_time = time.time()
        self.counters: Dict[str, int] = defaultdict(int)
        self.last_report_time = time.time()
        self.last_report_count = 0

    def increment(self, key: str, amount: int = 1) -> None:
        """Increment a counter."""
        self.counters[key] = self.counters.get(key, 0) + amount

    def get_rate(self) -> float:
        """Get current processing rate (items/second)."""
        elapsed = time.time() - self.start_time
        processed = self.counters.get("processed", 0)
        if elapsed > 0:
            return processed / elapsed
        return 0.0

    def get_eta(self) -> float:
        """Get estimated time remaining in seconds."""
        rate = self.get_rate()
        if rate <= 0:
            return 0.0
        remaining = self.total - self.counters.get("processed", 0)
        return remaining / rate

    def format_eta(self) -> str:
        """Format ETA as human-readable string."""
        eta_seconds = self.get_eta()
        if eta_seconds < 60:
            return f"{eta_seconds:.0f}s"
        elif eta_seconds < 3600:
            return f"{eta_seconds / 60:.1f}m"
        else:
            return f"{eta_seconds / 3600:.1f}h"

    def report(self) -> None:
        """Log current metrics."""
        now = time.time()
        elapsed = now - self.start_time
        processed = self.counters.get("processed", 0)
        rate = self.get_rate()

        # Calculate recent rate
        recent_elapsed = now - self.last_report_time
        recent_processed = processed - self.last_report_count
        recent_rate = recent_processed / recent_elapsed if recent_elapsed > 0 else 0

        logger.info(
            f"Progress: {processed}/{self.total} ({processed*100//self.total if self.total > 0 else 0}%) | "
            f"Rate: {rate:.2f}/s (recent: {recent_rate:.2f}/s) | "
            f"ETA: {self.format_eta()} | "
            f"OK: {self.counters.get('ok', 0)} | "
            f"Failed: {self.counters.get('failed', 0)} | "
            f"Not Found: {self.counters.get('not_found', 0)}"
        )

        self.last_report_time = now
        self.last_report_count = processed

    def get_summary(self) -> Dict:
        """Get summary statistics."""
        elapsed = time.time() - self.start_time
        return {
            "total": self.total,
            "processed": self.counters.get("processed", 0),
            "ok": self.counters.get("ok", 0),
            "failed": self.counters.get("failed", 0),
            "not_found": self.counters.get("not_found", 0),
            "rate": self.get_rate(),
            "eta_seconds": self.get_eta(),
            "elapsed_seconds": elapsed,
        }

