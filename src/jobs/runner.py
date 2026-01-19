"""Main job runner orchestrating the scraping pipeline."""
import asyncio
import logging
import time
import uuid
from typing import Optional

from src.config import config
from src.fetch.client import FetchClient
from src.fetch.endpoints import get_urls_for_nr
from src.parse.html_parser import parse_html_pages
from src.parse.models import SaleRecord
from src.parse.redact import redact_json, redact_string
from src.parse.explorer_enhanced import filter_and_tag_explorer_links
from src.store.state import StateDB
from src.store.supabase_writer_v2 import SupabaseWriterV2
from src.store.spool import SpoolManager
from src.store.dev_storage import DevStorage
from src.jobs.metrics import Metrics
from src.jobs.run_control import RunControl
from src.jobs.metrics_exporter import MetricsExporter

logger = logging.getLogger(__name__)


class ScrapeRunner:
    """Orchestrates the scraping pipeline."""

    def __init__(
        self,
        start: int,
        end: int,
        resume: bool = False,
        dev_mode: bool = False,
        dry_run: bool = False,
        store_html: bool = False,
        store_jsinfos: bool = True,
        store_explorer: bool = True,
        max_html_bytes: int = 1_500_000,
        explorer_max_links: int = 200,
        limit_gated: Optional[int] = None,
        stop_after_minutes: Optional[int] = None,
        max_errors: Optional[int] = None,
        max_consecutive_errors: Optional[int] = None,
        max_403: Optional[int] = None,
        max_429: Optional[int] = None,
        fail_fast: bool = False,
        cookie_only: bool = False,
        login_only: bool = False,
    ):
        self.start = start
        self.end = end
        self.resume = resume
        self.dev_mode = dev_mode
        self.dry_run = dry_run
        self.store_html = store_html
        self.store_jsinfos = store_jsinfos
        self.store_explorer = store_explorer
        self.max_html_bytes = max_html_bytes
        self.explorer_max_links = explorer_max_links
        self.cookie_only = cookie_only
        self.login_only = login_only
        
        # Generate run_id
        self.run_id = str(uuid.uuid4())
        logger.info(f"Run ID: {self.run_id}")
        
        # Run control
        self.run_control = RunControl(
            limit_gated=limit_gated,
            stop_after_minutes=stop_after_minutes,
            max_errors=max_errors,
            max_consecutive_errors=max_consecutive_errors,
            max_403=max_403,
            max_429=max_429,
            fail_fast=fail_fast,
        )
        
        self.state_db = StateDB()
        if not self.dry_run:
            try:
                self.writer = SupabaseWriterV2()
            except Exception as e:
                logger.warning(f"Supabase writer initialization failed: {e}")
                self.writer = None
        else:
            self.writer = None
            
        self.spool = SpoolManager()
        if self.dev_mode:
            self.dev_storage = DevStorage()
        else:
            self.dev_storage = None
            
        self.metrics = Metrics(end - start + 1)
        self.metrics_exporter = MetricsExporter(self.run_id)
        self.batch_buffer: list[SaleRecord] = []
        self.batch_id = 0
        self.last_metrics_export = time.time()

    async def initialize(self) -> None:
        """Initialize databases and test connections."""
        await self.state_db.initialize()
        if self.writer and not self.dry_run:
            if not await self.writer.test_connection():
                if not self.dev_mode:
                    raise RuntimeError("Supabase connection failed")
                else:
                    logger.warning("Supabase connection failed, continuing in DEV mode")

    async def run(self) -> None:
        """Run the scraping job with run control."""
        await self.initialize()

        # Get list of nr to process
        if self.resume:
            nrs = await self.state_db.get_next_undone(self.start, self.end)
            logger.info(f"Resuming: {len(nrs)} remaining records")
        else:
            nrs = list(range(self.start, self.end + 1))
            logger.info(f"Starting fresh: {len(nrs)} records")

        # Process with concurrency
        semaphore = asyncio.Semaphore(config.CONCURRENCY)

        async def process_nr(nr: int) -> None:
            async with semaphore:
                # Check stop conditions
                should_stop, reason = self.run_control.should_stop()
                if should_stop:
                    logger.warning(f"Stop condition met: {reason}")
                    return
                await self._process_single_nr(nr)
                
                # Export metrics periodically
                if time.time() - self.last_metrics_export > 30:  # Every 30 seconds
                    await self._export_metrics()
                    self.last_metrics_export = time.time()

        # Process with controlled concurrency
        chunk_size = 500
        try:
            for i in range(0, len(nrs), chunk_size):
                # Check stop conditions before each chunk
                should_stop, reason = self.run_control.should_stop()
                if should_stop:
                    logger.warning(f"Stop condition met before chunk: {reason}")
                    break
                
                chunk_nrs = nrs[i : i + chunk_size]
                tasks = [process_nr(nr) for nr in chunk_nrs]
                await asyncio.gather(*tasks, return_exceptions=True)
                # Flush buffer after each chunk
                await self._flush_buffer()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            # Final flush
            await self._flush_buffer()
            
            # Final report
            await self._final_report()

    async def _export_metrics(self) -> None:
        """Export current metrics."""
        summary = self.metrics.get_summary()
        run_summary = self.run_control.get_summary()
        
        await self.metrics_exporter.export_metrics(
            processed=summary["processed"],
            gate_false=self.metrics.counters.get("gate_failed", 0),
            ok=summary["ok"],
            failed=summary["failed"],
            error_403=run_summary["error_403_count"],
            error_429=run_summary["error_429_count"],
            rps=summary["rate"],
            eta=summary["eta_seconds"],
            avg_time_per_nr=run_summary["elapsed_minutes"] * 60 / max(summary["processed"], 1),
        )

    async def _final_report(self) -> None:
        """Generate final report."""
        summary = self.metrics.get_summary()
        run_summary = self.run_control.get_summary()
        
        logger.info("=" * 60)
        logger.info("FINAL REPORT")
        logger.info(f"Run ID: {self.run_id}")
        logger.info(f"Elapsed: {run_summary['elapsed_minutes']:.2f} minutes")
        logger.info(f"Processed: {summary['processed']}/{self.end - self.start + 1}")
        logger.info(f"OK: {summary['ok']}")
        logger.info(f"Gate passed: {run_summary['gated_count']}")
        logger.info(f"Gate failed: {self.metrics.counters.get('gate_failed', 0)}")
        logger.info(f"Failed: {summary['failed']}")
        logger.info(f"Not found: {summary['not_found']}")
        logger.info(f"403 errors: {run_summary['error_403_count']}")
        logger.info(f"429 errors: {run_summary['error_429_count']}")
        logger.info(f"Throughput: {summary['rate']:.2f} req/s")
        logger.info("=" * 60)
        
        # Export final metrics
        await self._export_metrics()

    async def _process_single_nr(self, nr: int) -> None:
        """Process a single nr with gating logic."""
        from src.parse.html_parser import contains_location_vehicule
        from src.config import config

        start_time = time.time()
        
        try:
            # Check if already done (skip in DEV mode for fresh testing)
            if not self.dev_mode and await self.state_db.is_done(nr):
                self.metrics.increment("skipped")
                return

            # Step 1: Fetch the main view page first for gating
            view_url = f"{config.BASE_URL}/digi/com/cto/view?nr={nr}"
            
            if self.dev_mode:
                logger.info(f"[DEV] Fetching view page for nr {nr}...")
            
            async with FetchClient(cookie_only=self.cookie_only, login_only=self.login_only) as client:
                view_response = await client.fetch(view_url)

            # Check for errors
            if not view_response:
                error_msg = "View page request failed"
                await self.state_db.mark_failed(nr, error_msg)
                self.run_control.record_error()
                self.metrics.increment("failed")
                self.metrics.increment("processed")
                if self.run_control.fail_fast:
                    raise RuntimeError(error_msg)
                return

            # Check for 404
            if view_response.status_code == 404:
                await self.state_db.mark_not_found(nr)
                self.metrics.increment("not_found")
                self.metrics.increment("processed")
                self.run_control.record_success()
                if self.dev_mode:
                    logger.info(f"[DEV] nr {nr}: NOT FOUND (404)")
                return
            
            # Check for 403/429 and record
            if view_response.status_code == 403:
                self.run_control.record_error(status_code=403)
                if self.run_control.fail_fast:
                    raise RuntimeError("403 Forbidden - authentication failed")
            elif view_response.status_code == 429:
                self.run_control.record_error(status_code=429)

            # Step 2: Check gate (Location de véhicule)
            html_content = view_response.text
            gate_passed = contains_location_vehicule(html_content)

            if self.dev_mode:
                logger.info(f"[DEV] nr {nr}: Gate {'PASSED' if gate_passed else 'FAILED'} (Location de véhicule)")

            if not gate_passed:
                # Gate failed - minimal record
                logger.debug(f"Gate failed for nr {nr}, skipping full extraction")
                record_data = {
                    "nr": nr,
                    "gate_passed": False,
                    "reason": "Location de véhicule not found",
                }
                # Redact before storing
                record_data = redact_json(record_data)
                
                record = SaleRecord(
                    nr=nr,
                    status="ok",
                    data=record_data,
                )
                
                # Save to DEV storage (redacted)
                if self.dev_storage:
                    self.dev_storage.save_nr_data(
                        nr=nr,
                        gate_passed=False,
                        urls_status={view_url: view_response.status_code},
                        extracted_data=record_data,
                        html_pages={view_url: html_content} if self.store_html else None,
                        store_html=self.store_html,
                    )
                
                self.batch_buffer.append(record)
                await self.state_db.mark_done(nr)
                self.metrics.increment("ok")
                self.metrics.increment("processed")
                self.metrics.increment("gate_failed")
                self.run_control.record_success()
                
                # Flush if needed
                if len(self.batch_buffer) >= config.BATCH_SIZE:
                    await self._flush_buffer()
                return

            # Step 3: Gate passed - record and fetch all 5 pages
            self.run_control.record_gated()
            logger.debug(f"Gate passed for nr {nr}, fetching all pages")
            urls = get_urls_for_nr(nr)
            
            if self.dev_mode:
                logger.info(f"[DEV] nr {nr}: Crawling {len(urls)} URLs: {[self._get_page_type_from_url(u) for u in urls]}")
            
            async with FetchClient(cookie_only=self.cookie_only, login_only=self.login_only) as client:
                responses = await client.fetch_all(urls)

            # Parse HTML with full extraction
            html_responses = {
                url: (r.text if r else None) for url, r in responses.items()
            }
            
            # Add status codes and final URLs
            urls_status = {}
            page_results = {}
            for url, response in responses.items():
                if response:
                    status = response.status_code
                    urls_status[url] = status
                    page_results[url] = {
                        "status_code": status,
                        "final_url": str(response.url),
                    }

            # Filter data based on store flags
            parsed_data = parse_html_pages(html_responses, config.BASE_URL, gate_passed=True)
            
            # Process explorer links with enhanced filtering
            if self.store_explorer:
                for page_type, page_data in parsed_data.get("pages", {}).items():
                    html_content = html_responses.get(page_data.get("url", ""))
                    if html_content:
                        explorer_links = filter_and_tag_explorer_links(
                            html_content,
                            config.BASE_URL,
                            max_links=self.explorer_max_links,
                        )
                        page_data["explorer_links"] = explorer_links
            else:
                parsed_data.pop("explorer_links", None)
                for page_data in parsed_data.get("pages", {}).values():
                    page_data.pop("explorer_links", None)
            
            # Remove JSinfos if not storing
            if not self.store_jsinfos:
                parsed_data.pop("jsinfos", None)
                for page_data in parsed_data.get("pages", {}).values():
                    page_data.pop("jsinfos", None)
            
            # Store HTML content temporarily for writer (if within limits)
            for page_type, page_data in parsed_data.get("pages", {}).items():
                url = page_data.get("url", "")
                html_content = html_responses.get(url)
                if html_content and self.store_html:
                    html_bytes = len(html_content.encode("utf-8"))
                    if html_bytes <= self.max_html_bytes:
                        page_data["_html_content"] = html_content
            
            # Merge page results
            for page_type, page_data in parsed_data.get("pages", {}).items():
                if page_data.get("url") in page_results:
                    page_data.update(page_results[page_data["url"]])

            # Create full record (redacted)
            data = {
                "nr": nr,
                "gate_passed": True,
                **parsed_data,
            }
            # Redact secrets before storing
            data = redact_json(data)

            record = SaleRecord(
                nr=nr,
                status="ok",
                data=data,
            )

            # Save to DEV storage
            if self.dev_storage:
                nb_jsinfos = self._count_jsinfos(parsed_data)
                nb_basket = len(parsed_data.get("basket_lines", []))
                nb_explorer = len(parsed_data.get("explorer_links", []))
                elapsed = time.time() - start_time
                
                logger.info(
                    f"[DEV] nr {nr}: Extraction complete - "
                    f"JSinfos: {nb_jsinfos}, Basket lines: {nb_basket}, "
                    f"Explorer links: {nb_explorer}, Time: {elapsed:.2f}s"
                )
                
                self.dev_storage.save_nr_data(
                    nr=nr,
                    gate_passed=True,
                    urls_status=urls_status,
                    extracted_data=data,
                    html_pages=html_responses if self.store_html else None,
                    store_html=self.store_html,
                )

            # Add to buffer
            self.batch_buffer.append(record)

            # Flush if buffer is full
            if len(self.batch_buffer) >= config.BATCH_SIZE:
                await self._flush_buffer()

            # Mark as done
            await self.state_db.mark_done(nr)
            self.metrics.increment("ok")
            self.metrics.increment("processed")
            self.metrics.increment("gate_passed")
            self.run_control.record_success()

            # Report periodically
            if self.metrics.counters["processed"] % 100 == 0:
                self.metrics.report()

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error processing nr {nr}: {error_msg}", exc_info=True)
            # Don't log cookies/tokens in error messages
            error_msg_redacted = redact_string(error_msg)
            await self.state_db.mark_failed(nr, error_msg_redacted)
            self.run_control.record_error()
            self.metrics.increment("failed")
            self.metrics.increment("processed")
            
            # Fail fast if configured
            if self.run_control.fail_fast and "auth" in error_msg.lower():
                raise

    def _count_jsinfos(self, data: dict) -> int:
        """Count total JSinfos found."""
        count = 0
        jsinfos = data.get("jsinfos", {})
        if isinstance(jsinfos, dict):
            for page_jsinfos in jsinfos.values():
                if isinstance(page_jsinfos, dict):
                    count += len(page_jsinfos)
        return count

    def _get_page_type_from_url(self, url: str) -> str:
        """Extract page type from URL."""
        if "viewLogistic" in url:
            return "logistic"
        elif "viewPayment" in url:
            return "payment"
        elif "viewInfos" in url:
            return "infos"
        elif "viewOrders" in url:
            return "orders"
        else:
            return "view"

    async def _flush_buffer(self) -> None:
        """Flush buffer to Supabase or spool."""
        if not self.batch_buffer:
            return

        records = self.batch_buffer.copy()
        self.batch_buffer.clear()
        self.batch_id += 1

        # Skip Supabase write in dry-run or if no writer
        if self.dry_run or not self.writer:
            if self.dev_mode:
                logger.info(f"[DEV] Skipping Supabase write ({len(records)} records) - dry-run mode")
            return

        try:
            # Use new writer with 2-table schema
            for record in records:
                await self.writer.upsert_run_and_pages(
                    self.run_id,
                    record,
                    max_html_bytes=self.max_html_bytes if self.store_html else None,
                )
            # Delete spool file if it exists (from previous failed attempt)
            await self.spool.delete_batch(self.batch_id)
        except Exception as e:
            logger.warning(f"Supabase write failed, spooling to disk: {e}")
            # Write to spool (redacted)
            for record in records:
                # Redact before spooling
                record.data = redact_json(record.data)
                await self.spool.write_record(record, self.batch_id)

