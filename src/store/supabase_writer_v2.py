"""Supabase writer for 2-table schema (cto_runs + cto_pages)."""
import asyncio
import base64
import gzip
import logging
from typing import Optional
from supabase import create_client, Client
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import config
from src.parse.models import SaleRecord
from src.parse.redact import redact_json

logger = logging.getLogger(__name__)


class SupabaseWriterV2:
    """Writes records to Supabase using 2-table schema."""

    def __init__(self):
        if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE:
            raise ValueError("Supabase configuration missing")
        self.client: Client = create_client(
            config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE
        )
        self.runs_table = "cto_runs"
        self.pages_table = "cto_pages"

    async def upsert_run_and_pages(
        self,
        run_id: str,
        record: SaleRecord,
        max_html_bytes: Optional[int] = None,
    ) -> None:
        """Upsert run and pages to Supabase."""
        from datetime import datetime
        
        # Prepare run data (redacted)
        run_data = {
            "nr": record.nr,
            "run_id": run_id,
            "gate_passed": record.data.get("gate_passed", False),
            "gate_reason": record.data.get("reason"),
            "status": record.status,
            "started_at": record.fetched_at.isoformat(),
            "finished_at": datetime.utcnow().isoformat(),
            "error": record.data.get("error"),
            "metrics": record.data.get("metrics"),
        }
        run_data = redact_json(run_data)

        # Prepare pages data
        pages_data = []
        pages = record.data.get("pages", {})
        
        for page_type, page_info in pages.items():
            if not isinstance(page_info, dict):
                continue
            
            # Extract HTML if available and within limits
            raw_html_gz_b64 = None
            html_content = page_info.get("_html_content")  # Stored temporarily
            if html_content and max_html_bytes:
                html_bytes = len(html_content.encode("utf-8"))
                if html_bytes <= max_html_bytes:
                    # Compress and encode
                    compressed = gzip.compress(html_content.encode("utf-8"))
                    raw_html_gz_b64 = base64.b64encode(compressed).decode("utf-8")
                # Remove from page_info before storing
                page_info = {k: v for k, v in page_info.items() if k != "_html_content"}
            
            # Redact extracted data
            extracted = redact_json(page_info)
            
            page_data = {
                "run_id": run_id,
                "nr": record.nr,
                "page_type": page_type,
                "url": page_info.get("url", ""),
                "status_code": page_info.get("status_code"),
                "final_url": page_info.get("final_url"),
                "html_hash": page_info.get("hash"),
                "extracted": extracted,
                "raw_html_gz_b64": raw_html_gz_b64,
            }
            pages_data.append(page_data)

        # Upsert in transaction-like manner
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None, self._upsert_sync, run_data, pages_data
            )
            logger.info(f"Upserted run {run_id} (nr={record.nr}) with {len(pages_data)} pages")
        except Exception as e:
            logger.error(f"Supabase upsert error: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
    )
    def _upsert_sync(self, run_data: dict, pages_data: list[dict]) -> None:
        """Synchronous upsert (called from thread pool)."""
        # Upsert run
        (
            self.client.table(self.runs_table)
            .upsert(run_data, on_conflict="nr")
            .execute()
        )
        
        # Upsert pages (one by one due to unique constraint)
        for page_data in pages_data:
            (
                self.client.table(self.pages_table)
                .upsert(page_data, on_conflict="run_id,page_type")
                .execute()
            )

    async def test_connection(self) -> bool:
        """Test Supabase connection."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: (
                    self.client.table(self.runs_table)
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

