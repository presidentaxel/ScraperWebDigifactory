"""Disk spool for buffering records when Supabase is unavailable."""
import json
import logging
from pathlib import Path
from typing import Iterator
import aiofiles
import orjson

from src.config import SPOOL_DIR
from src.parse.models import SaleRecord

logger = logging.getLogger(__name__)


class SpoolManager:
    """Manages JSONL spool files for offline buffering."""

    def __init__(self, spool_dir: Path = SPOOL_DIR):
        self.spool_dir = spool_dir
        self.spool_dir.mkdir(parents=True, exist_ok=True)

    def _get_spool_file(self, batch_id: int) -> Path:
        """Get spool file path for a batch."""
        return self.spool_dir / f"batch_{batch_id}.jsonl"

    async def write_record(self, record: SaleRecord, batch_id: int) -> None:
        """Write a record to spool file."""
        spool_file = self._get_spool_file(batch_id)
        async with aiofiles.open(spool_file, "ab") as f:
            line = orjson.dumps(record.model_dump(mode="json")).decode() + "\n"
            await f.write(line.encode())

    async def read_batch(self, batch_id: int) -> list[dict]:
        """Read all records from a spool file."""
        spool_file = self._get_spool_file(batch_id)
        if not spool_file.exists():
            return []

        records = []
        async with aiofiles.open(spool_file, "rb") as f:
            async for line in f:
                try:
                    record = orjson.loads(line)
                    records.append(record)
                except Exception as e:
                    logger.warning(f"Error reading spool line: {e}")
                    continue

        return records

    async def delete_batch(self, batch_id: int) -> None:
        """Delete a spool file after successful upload."""
        spool_file = self._get_spool_file(batch_id)
        if spool_file.exists():
            spool_file.unlink()

    def list_spool_files(self) -> Iterator[Path]:
        """List all spool files."""
        return self.spool_dir.glob("batch_*.jsonl")

