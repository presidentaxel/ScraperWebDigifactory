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
        self.errors_table = "cto_errors"

    async def upsert_run_and_pages(
        self,
        run_id: str,
        record: SaleRecord,
        max_html_bytes: Optional[int] = None,
    ) -> None:
        """Upsert run and pages to Supabase."""
        from datetime import datetime
        
        # Prepare run data (redacted)
        gate_passed = record.data.get("gate_passed", False)
        run_data = {
            "nr": record.nr,
            "run_id": run_id,
            "gate_passed": gate_passed,
            "gate_reason": record.data.get("gate_reason"),  # Fixed: was "reason", should be "gate_reason"
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
        
        # Log warning if gate_passed but no pages (should not happen)
        if gate_passed and not pages:
            logger.warning(f"Run {run_id} (nr={record.nr}) has gate_passed=True but no pages data!")
        
        if not isinstance(pages, dict):
            logger.warning(f"Run {run_id} (nr={record.nr}) has pages that is not a dict: {type(pages)}")
            pages = {}
        
        # Log pages being processed
        if gate_passed and pages:
            page_types = list(pages.keys())
            logger.info(
                f"[SUPABASE_WRITE] run_id={run_id} nr={record.nr} gate_passed={gate_passed} "
                f"Preparing {len(page_types)} pages: {page_types}"
            )
        elif gate_passed and not pages:
            logger.warning(
                f"[SUPABASE_WRITE] run_id={run_id} nr={record.nr} gate_passed={gate_passed} "
                f"but NO PAGES to write!"
            )
        
        for page_type, page_info in pages.items():
            if not isinstance(page_info, dict):
                logger.warning(f"Run {run_id} (nr={record.nr}) page {page_type} is not a dict: {type(page_info)}")
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
            
            # Extract and redact only the "extracted" field, keep other fields intact
            extracted_raw = page_info.get("extracted", {})
            extracted = redact_json(extracted_raw) if extracted_raw else {}
            
            page_data = {
                "run_id": run_id,
                "nr": record.nr,
                "page_type": page_type,
                "url": page_info.get("url", ""),
                "status_code": page_info.get("status_code"),
                "final_url": page_info.get("final_url"),
                "html_hash": page_info.get("hash"),
                "content_length": page_info.get("content_length"),  # Add content_length if available
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
            if gate_passed and len(pages_data) == 0:
                logger.warning(
                    f"[SUPABASE_WRITE] Upserted run {run_id} (nr={record.nr}) with gate_passed=True but 0 pages!"
                )
            elif gate_passed:
                page_types = [p.get("page_type") for p in pages_data]
                logger.info(
                    f"[SUPABASE_WRITE] Successfully upserted run {run_id} (nr={record.nr}) "
                    f"with {len(pages_data)} pages: {page_types}"
                )
            else:
                logger.debug(f"[SUPABASE_WRITE] Upserted run {run_id} (nr={record.nr}) with gate_passed=False (no pages)")
        except Exception as e:
            logger.error(f"Supabase upsert error for run {run_id} (nr={record.nr}): {e}", exc_info=True)
            # Log error to errors table
            await self.log_error(
                run_id=run_id,
                error_type="supabase_error",
                error_message=str(e)[:500],
                error_details={
                    "nr": record.nr,
                    "gate_passed": record.data.get("gate_passed"),
                    "pages_count": len(pages_data),
                },
                nr=record.nr,
            )
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
    )
    def _upsert_sync(self, run_data: dict, pages_data: list[dict]) -> None:
        """Synchronous upsert (called from thread pool)."""
        nr = run_data.get("nr")
        run_id = run_data.get("run_id")
        gate_passed = run_data.get("gate_passed", False)
        
        # CRITICAL: Before upserting a new run, delete old pages for this nr
        # This prevents orphaned pages from previous runs when we overwrite cto_runs
        # We only keep pages from the current run_id
        try:
            # Delete all pages for this nr that don't belong to the current run_id
            # This ensures we don't accumulate pages from multiple runs
            delete_response = (
                self.client.table(self.pages_table)
                .delete()
                .eq("nr", nr)
                .neq("run_id", run_id)  # Keep pages from current run_id only
                .execute()
            )
            deleted_count = len(delete_response.data) if delete_response.data else 0
            if deleted_count > 0:
                logger.info(
                    f"[SUPABASE_WRITE] Deleted {deleted_count} old pages for nr={nr} "
                    f"(keeping run_id={run_id})"
                )
        except Exception as e:
            # Log but don't fail - deletion is best effort to prevent orphaned pages
            logger.warning(f"[SUPABASE_WRITE] Failed to delete old pages for nr={nr}: {e}")
        
        # Upsert run (this will overwrite previous run for this nr)
        try:
            (
                self.client.table(self.runs_table)
                .upsert(run_data, on_conflict="nr")
                .execute()
            )
        except Exception as e:
            logger.error(f"Failed to upsert run nr={nr} run_id={run_id}: {e}", exc_info=True)
            raise
        
        # Log if no pages but gate_passed
        if gate_passed and len(pages_data) == 0:
            logger.warning(f"Run nr={nr} run_id={run_id} has gate_passed=True but 0 pages to insert!")
        
        # Upsert pages (one by one due to unique constraint)
        # Continue processing all pages even if one fails
        successful_pages = 0
        failed_pages = 0
        for page_data in pages_data:
            try:
                (
                    self.client.table(self.pages_table)
                    .upsert(page_data, on_conflict="run_id,page_type")
                    .execute()
                )
                successful_pages += 1
            except Exception as e:
                failed_pages += 1
                logger.error(
                    f"Failed to upsert page run_id={page_data.get('run_id')} "
                    f"page_type={page_data.get('page_type')} nr={page_data.get('nr')}: {e}",
                    exc_info=True
                )
                # Continue processing other pages instead of raising
        
        # Log summary
        if failed_pages > 0:
            logger.warning(
                f"[SUPABASE_WRITE] Upserted {successful_pages}/{len(pages_data)} pages for run_id={run_id} nr={nr}. "
                f"{failed_pages} pages failed."
            )
        elif len(pages_data) > 0:
            page_types_written = [p.get("page_type") for p in pages_data]
            logger.info(
                f"[SUPABASE_WRITE] Successfully upserted all {len(pages_data)} pages "
                f"for run_id={run_id} nr={nr}: {page_types_written}"
            )

    async def log_error(
        self,
        run_id: str,
        error_type: str,
        error_message: str,
        error_details: Optional[dict] = None,
        nr: Optional[int] = None,
        page_type: Optional[str] = None,
        url: Optional[str] = None,
    ) -> None:
        """Log an error to the cto_errors table."""
        from datetime import datetime
        from traceback import format_exc
        
        # Prepare error data
        error_data = {
            "run_id": run_id,
            "nr": nr,
            "error_type": error_type,
            "error_message": error_message[:1000],  # Limit message length
            "error_details": redact_json(error_details or {}),
            "page_type": page_type,
            "url": url,
            "occurred_at": datetime.utcnow().isoformat(),
        }
        
        # Add stack trace if available in error_details
        if error_details and "traceback" not in error_details:
            try:
                error_data["error_details"]["traceback"] = format_exc()
            except Exception:
                pass
        
        # Insert error (non-blocking, don't fail if this fails)
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None, self._insert_error_sync, error_data
            )
        except Exception as e:
            # Don't fail the main process if error logging fails
            logger.warning(f"Failed to log error to Supabase: {e}")

    def _insert_error_sync(self, error_data: dict) -> None:
        """Synchronous error insert (called from thread pool)."""
        try:
            (
                self.client.table(self.errors_table)
                .insert(error_data)
                .execute()
            )
        except Exception as e:
            # Log but don't raise - error logging should never break the main flow
            logger.warning(f"Failed to insert error log: {e}")

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

