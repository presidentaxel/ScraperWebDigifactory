"""Run control: stop conditions and limits."""
import time
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RunControl:
    """Controls run stopping conditions."""
    
    limit_gated: Optional[int] = None
    stop_after_minutes: Optional[int] = None
    max_errors: Optional[int] = None
    max_consecutive_errors: Optional[int] = None
    max_403: Optional[int] = None
    max_429: Optional[int] = None
    fail_fast: bool = False
    
    # Internal state
    start_time: float = field(default_factory=time.time)
    gated_count: int = 0
    error_count: int = 0
    consecutive_errors: int = 0
    error_403_count: int = 0
    error_429_count: int = 0
    last_error_time: Optional[float] = None
    
    def should_stop(self, reason: str = "") -> tuple[bool, Optional[str]]:
        """Check if run should stop. Returns (should_stop, reason)."""
        elapsed_minutes = (time.time() - self.start_time) / 60
        
        # Check limit_gated
        if self.limit_gated and self.gated_count >= self.limit_gated:
            return True, f"Reached limit_gated={self.limit_gated}"
        
        # Check stop_after_minutes
        if self.stop_after_minutes and elapsed_minutes >= self.stop_after_minutes:
            return True, f"Reached stop_after_minutes={self.stop_after_minutes}"
        
        # Check max_errors
        if self.max_errors and self.error_count >= self.max_errors:
            return True, f"Reached max_errors={self.max_errors}"
        
        # Check max_consecutive_errors
        if self.max_consecutive_errors and self.consecutive_errors >= self.max_consecutive_errors:
            return True, f"Reached max_consecutive_errors={self.max_consecutive_errors}"
        
        # Check max_403
        if self.max_403 and self.error_403_count >= self.max_403:
            return True, f"Reached max_403={self.max_403}"
        
        # Check max_429
        if self.max_429 and self.error_429_count >= self.max_429:
            return True, f"Reached max_429={self.max_429}"
        
        return False, None
    
    def record_gated(self) -> None:
        """Record a gated sale."""
        self.gated_count += 1
        self.consecutive_errors = 0  # Reset on success
    
    def record_error(self, status_code: Optional[int] = None) -> None:
        """Record an error."""
        self.error_count += 1
        self.consecutive_errors += 1
        self.last_error_time = time.time()
        
        if status_code == 403:
            self.error_403_count += 1
        elif status_code == 429:
            self.error_429_count += 1
    
    def record_success(self) -> None:
        """Record a successful operation."""
        self.consecutive_errors = 0
    
    def get_summary(self) -> dict:
        """Get summary statistics."""
        elapsed_minutes = (time.time() - self.start_time) / 60
        return {
            "elapsed_minutes": round(elapsed_minutes, 2),
            "gated_count": self.gated_count,
            "error_count": self.error_count,
            "consecutive_errors": self.consecutive_errors,
            "error_403_count": self.error_403_count,
            "error_429_count": self.error_429_count,
        }

