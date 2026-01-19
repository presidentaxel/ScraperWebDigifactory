"""Supabase writer with batch upsert and retries."""
import asyncio
import logging
from typing import Optional
from supabase import create_client, Client
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import config
from src.parse.models import SaleRecord

logger = logging.getLogger(__name__)


class SupabaseWriter:
    """Writes records to Supabase with batch upsert."""

    def __init__(self):
        if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE:
            raise ValueError("Supabase configuration missing")
        self.client: Client = create_client(
            config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE
        )
        self.table = config.SUPABASE_TABLE

    async def upsert_batch(self, records: list[SaleRecord]) -> None:
        """Upsert a batch of records (runs in thread pool since Supabase is sync)."""
        if not records:
            return

        # Convert to dicts for Supabase
        data = [self._record_to_dict(record) for record in records]

        # Run sync Supabase client in thread pool
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None, self._upsert_sync, data
            )
            logger.info(f"Upserted {len(records)} records to Supabase")
        except Exception as e:
            logger.error(f"Supabase upsert error: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
    )
    def _upsert_sync(self, data: list[dict]) -> None:
        """Synchronous upsert (called from thread pool)."""
        (
            self.client.table(self.table)
            .upsert(data, on_conflict="nr")
            .execute()
        )

    def _record_to_dict(self, record: SaleRecord) -> dict:
        """Convert SaleRecord to dict for Supabase."""
        return {
            "nr": record.nr,
            "fetched_at": record.fetched_at.isoformat(),
            "status": record.status,
            "data": record.data,
            "raw": record.raw,
            "hash": record.hash,
        }

    async def test_connection(self) -> bool:
        """Test Supabase connection."""
        try:
            # Run sync query in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: (
                    self.client.table(self.table)
                    .select("nr", count="exact")
                    .limit(1)
                    .execute()
                ),
            )
            logger.info("Supabase connection successful")
            return True
        except Exception as e:
            logger.error(f"Supabase connection test failed: {e}")
            return False

