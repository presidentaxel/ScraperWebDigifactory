"""Metrics exporter for observability."""
import json
import time
from pathlib import Path
from typing import Dict
import aiofiles

from src.config import DATA_DIR

METRICS_FILE = DATA_DIR / "metrics.jsonl"


class MetricsExporter:
    """Exports metrics to JSONL file for observability."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.metrics_file = METRICS_FILE
        self.start_time = time.time()

    async def export_metrics(
        self,
        processed: int,
        gate_false: int,
        ok: int,
        failed: int,
        error_403: int,
        error_429: int,
        rps: float,
        eta: float,
        avg_time_per_nr: float,
    ) -> None:
        """Export metrics to JSONL file."""
        metrics = {
            "ts": time.time(),
            "run_id": self.run_id,
            "processed": processed,
            "gate_false": gate_false,
            "ok": ok,
            "failed": failed,
            "error_403": error_403,
            "error_429": error_429,
            "rps": round(rps, 2),
            "eta": round(eta, 2),
            "avg_time_per_nr": round(avg_time_per_nr, 3),
        }
        
        line = json.dumps(metrics) + "\n"
        async with aiofiles.open(self.metrics_file, "a") as f:
            await f.write(line)

