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
        dev_limit_payment: Optional[int] = None,
        dev_limit_transaction: Optional[int] = None,
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
        self.dev_limit_payment = dev_limit_payment
        self.dev_limit_transaction = dev_limit_transaction
        
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

        # Save the main nr (cto_nr) - never overwrite this!
        cto_nr = nr
        start_time = time.time()
        
        try:
            # Check if already done (skip in DEV mode for fresh testing)
            if not self.dev_mode and await self.state_db.is_done(cto_nr):
                self.metrics.increment("skipped")
                return

            # Step 1: Fetch the main view page first for gating
            view_url = f"{config.BASE_URL}/digi/com/cto/view?nr={cto_nr}"
            
            if self.dev_mode:
                logger.info(f"[DEV] Fetching view page for nr {cto_nr}...")
            
            async with FetchClient(cookie_only=self.cookie_only, login_only=self.login_only) as client:
                view_response = await client.fetch(view_url)

            # Check for errors
            if not view_response:
                error_msg = "View page request failed"
                await self.state_db.mark_failed(cto_nr, error_msg)
                
                # Log error to Supabase
                if self.writer:
                    await self.writer.log_error(
                        run_id=self.run_id,
                        error_type="fetch_error",
                        error_message=error_msg,
                        error_details={"nr": cto_nr, "url": view_url},
                        nr=cto_nr,
                        url=view_url,
                    )
                
                self.run_control.record_error()
                self.metrics.increment("failed")
                self.metrics.increment("processed")
                if self.run_control.fail_fast:
                    raise RuntimeError(error_msg)
                return

            # Check for 404
            if view_response.status_code == 404:
                await self.state_db.mark_not_found(cto_nr)
                self.metrics.increment("not_found")
                self.metrics.increment("processed")
                self.run_control.record_success()
                if self.dev_mode:
                    logger.info(f"[DEV] nr {cto_nr}: NOT FOUND (404)")
                return
            
            # Check for 403/429 and record
            if view_response.status_code == 403:
                error_msg = "403 Forbidden - authentication failed"
                self.run_control.record_error(status_code=403)
                
                # Log auth error to Supabase
                if self.writer:
                    await self.writer.log_error(
                        run_id=self.run_id,
                        error_type="auth_error",
                        error_message=error_msg,
                        error_details={"nr": cto_nr, "url": view_url, "status_code": 403},
                        nr=cto_nr,
                        url=view_url,
                    )
                
                if self.run_control.fail_fast:
                    raise RuntimeError(error_msg)
            elif view_response.status_code == 429:
                self.run_control.record_error(status_code=429)
                
                # Log rate limit error to Supabase
                if self.writer:
                    await self.writer.log_error(
                        run_id=self.run_id,
                        error_type="rate_limit_error",
                        error_message="429 Too Many Requests",
                        error_details={"nr": cto_nr, "url": view_url, "status_code": 429},
                        nr=cto_nr,
                        url=view_url,
                    )

            # Step 2: Check gate (Location de véhicule)
            html_content = view_response.text
            gate_passed, gate_reason = contains_location_vehicule(html_content)

            if self.dev_mode:
                logger.info(f"[DEV] nr {cto_nr}: Gate {'PASSED' if gate_passed else 'FAILED'} (Location de véhicule)")
                if not gate_passed:
                    logger.info(f"[DEV] Gate reason: {gate_reason.get('gate_reason', 'unknown')}")

            if not gate_passed:
                # Gate failed - minimal record with gate_reason
                logger.debug(f"Gate failed for nr {cto_nr}, skipping full extraction")
                record_data = {
                    "nr": cto_nr,
                    "gate_passed": False,
                    "gate_reason": gate_reason.get("gate_reason", "unknown"),
                }
                
                # Add dev-only fields
                if self.dev_mode:
                    if gate_reason.get("gate_match_count") is not None:
                        record_data["gate_match_count"] = gate_reason["gate_match_count"]
                    if gate_reason.get("gate_matched_text"):
                        record_data["gate_matched_text"] = gate_reason["gate_matched_text"]
                
                # Redact before storing
                record_data = redact_json(record_data)
                
                record = SaleRecord(
                    nr=cto_nr,
                    status="ok",
                    data=record_data,
                )
                
                # Save to DEV storage (redacted)
                if self.dev_storage:
                    self.dev_storage.save_nr_data(
                        nr=cto_nr,
                        gate_passed=False,
                        urls_status={view_url: view_response.status_code},
                        extracted_data=record_data,
                        html_pages={view_url: html_content} if self.store_html else None,
                        store_html=self.store_html,
                    )
                
                self.batch_buffer.append(record)
                await self.state_db.mark_done(cto_nr)
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
            logger.debug(f"Gate passed for nr {cto_nr}, fetching all pages")
            urls = get_urls_for_nr(cto_nr)  # Returns list[str] of URLs
            
            if self.dev_mode:
                page_types = [self._get_page_type_from_url(u) for u in urls]
                logger.info(f"[DEV] nr {cto_nr}: Crawling {len(urls)} URLs: {page_types}")
            
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

            # Extract payment requests and transactions from JSinfos spans (NEW METHOD)
            payment_url = next((u for u in urls if "viewPayment" in u), None)
            payment_html = html_responses.get(payment_url) if payment_url else None
            detail_urls = {}
            payment_requests_data = []
            transactions_data = []
            
            if payment_html:
                from src.parse.payment_details import extract_payment_data_from_jsinfos
                payment_data = extract_payment_data_from_jsinfos(payment_html, config.BASE_URL)
                
                # Store raw data for later enrichment with modal details
                payment_requests_data = payment_data.get("payment_requests", [])
                transactions_data = payment_data.get("transactions", [])
                
                # Collect detail URLs to fetch (limit in DEV mode if flag set)
                dev_limit_payment = getattr(self, 'dev_limit_payment', None) if self.dev_mode else None
                payment_requests_to_fetch = payment_requests_data[:dev_limit_payment] if dev_limit_payment else payment_requests_data
                
                dev_limit_transaction = getattr(self, 'dev_limit_transaction', None) if self.dev_mode else None
                transactions_to_fetch = transactions_data[:dev_limit_transaction] if dev_limit_transaction else transactions_data
                
                # Build URLs for payment requests
                for item in payment_requests_to_fetch:
                    request_nr = item.get("nr")
                    if request_nr:
                        details_url = f"{config.BASE_URL}/digi/com/gocardless/viewPaymentRequestInfos?spaceSelect=1&nr={request_nr}"
                        detail_urls[details_url] = {"type": "gocardless", "item": item}
                
                # Build URLs for transactions
                for item in transactions_to_fetch:
                    transaction_nr = item.get("nr")
                    if transaction_nr:
                        details_url = f"{config.BASE_URL}/digi/cfg/modal/ajax/viewTransaction?nr={transaction_nr}"
                        detail_urls[details_url] = {"type": "transaction", "item": item}
            
            # Fetch all detail pages in parallel if any
            detail_responses = {}
            if detail_urls:
                if self.dev_mode:
                    logger.info(f"[PAYMENT] Fetching {len(detail_urls)} detail modals...")
                
                async with FetchClient(cookie_only=self.cookie_only, login_only=self.login_only) as detail_client:
                    detail_responses = await detail_client.fetch_all(detail_urls.keys())
                    
                    # Log fetch results in DEV mode
                    if self.dev_mode:
                        for url, response in detail_responses.items():
                            url_info = detail_urls.get(url, {})
                            item = url_info.get("item", {})
                            detail_nr = item.get("nr", "?")
                            url_type = url_info.get("type", "?")
                            
                            if response and response.status_code == 200:
                                bytes_size = len(response.text.encode("utf-8"))
                                logger.info(f"[PAYMENT] fetching {url_type}_details nr={detail_nr} -> {response.status_code} bytes={bytes_size}")
                            else:
                                status_code = response.status_code if response else "no_response"
                                logger.warning(f"[PAYMENT] fetching {url_type}_details nr={detail_nr} -> {status_code}")
                    
                    # Store detail responses separately (don't mix with main pages)
                    # We'll parse these separately in _parse_payment_details
                    # Do NOT add them to html_responses as they would be treated as main pages

            # Parse HTML pages - only parse the 5 main pages (not detail modals)
            # html_responses should only contain the 5 main pages (view, payment, logistic, infos, orders)
            # Filter out any detail modal URLs that might have been accidentally added
            main_pages_responses = {
                url: html_content 
                for url, html_content in html_responses.items() 
                if not any(keyword in url for keyword in [
                    "/gocardless/viewPaymentRequestInfos", 
                    "/modal/ajax/viewTransaction",
                    "/cfg/modal/ajax/viewTransaction"
                ])
            }
            parsed_data = parse_html_pages(main_pages_responses, config.BASE_URL, gate_passed=True, store_debug_snippets=self.dev_mode)
            
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
            
            # Parse detailed payment data from already-fetched modal responses
            await self._parse_payment_details(
                parsed_data, 
                detail_responses, 
                detail_urls,
                payment_requests_data,
                transactions_data
            )

            # Create full record (restructured, redacted)
            # Structure: nr, gate_passed, run_id, summary, pages, explorer_links_all
            # Use cto_nr (never overwrite the main nr)
            data = {
                "nr": cto_nr,
                "gate_passed": True,
                "run_id": self.run_id,
                "summary": {
                    "nb_pages": len(parsed_data.get("pages", {})),
                    "nb_jsinfos": self._count_jsinfos(parsed_data),
                    "nb_explorer_links": len(parsed_data.get("explorer_links_all", [])),
                },
                "pages": parsed_data.get("pages", {}),
            }
            
            # Add explorer_links_all if storing
            if self.store_explorer and parsed_data.get("explorer_links_all"):
                data["explorer_links_all"] = parsed_data["explorer_links_all"]
            
            # Redact secrets before storing
            data = redact_json(data)

            record = SaleRecord(
                nr=cto_nr,
                status="ok",
                data=data,
            )

            # Save to DEV storage
            if self.dev_storage:
                view_page = parsed_data.get("pages", {}).get("view", {})
                extracted = view_page.get("extracted", {})
                basket = extracted.get("basket", {})
                location = extracted.get("location", {})
                
                payment_page = parsed_data.get("pages", {}).get("payment", {})
                payment_extracted = payment_page.get("extracted", {})
                nb_payment_requests = len(payment_extracted.get("payment_requests", []))
                nb_transactions = len(payment_extracted.get("transactions", []))
                
                nb_jsinfos = self._count_jsinfos(parsed_data)
                nb_basket = len(basket.get("basket_lines", []))
                nb_explorer = len(parsed_data.get("explorer_links_all", []))
                semaine = location.get("semaine", "N/A")
                elapsed = time.time() - start_time
                
                logger.info(
                    f"[DEV] nr {cto_nr}: Extraction complete - "
                    f"JSinfos: {nb_jsinfos}, Basket lines: {nb_basket}, "
                    f"Semaine: {semaine}, Explorer links: {nb_explorer}, "
                    f"Payment requests: {nb_payment_requests}, Transactions: {nb_transactions}, "
                    f"Time: {elapsed:.2f}s"
                )
                
                self.dev_storage.save_nr_data(
                    nr=cto_nr,
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

            # Mark as done (use cto_nr)
            await self.state_db.mark_done(cto_nr)
            self.metrics.increment("ok")
            self.metrics.increment("processed")
            self.metrics.increment("gate_passed")
            self.run_control.record_success()
            
            # Report periodically
            if self.metrics.counters["processed"] % 100 == 0:
                self.metrics.report()

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error processing nr {cto_nr}: {error_msg}", exc_info=True)
            # Don't log cookies/tokens in error messages
            error_msg_redacted = redact_string(error_msg)
            await self.state_db.mark_failed(cto_nr, error_msg_redacted)
            
            # Log error to Supabase if writer is available
            if self.writer:
                import traceback
                error_type = "processing_error"
                if "auth" in error_msg.lower() or "login" in error_msg.lower():
                    error_type = "auth_error"
                elif "fetch" in error_msg.lower() or "http" in error_msg.lower():
                    error_type = "fetch_error"
                elif "parse" in error_msg.lower():
                    error_type = "parse_error"
                
                await self.writer.log_error(
                    run_id=self.run_id,
                    error_type=error_type,
                    error_message=error_msg_redacted[:500],
                    error_details={
                        "full_message": error_msg_redacted[:2000],
                        "traceback": traceback.format_exc(),
                        "nr": cto_nr,
                    },
                    nr=cto_nr,
                )
            
            self.run_control.record_error()
            self.metrics.increment("failed")
            self.metrics.increment("processed")
            
            # Fail fast if configured
            if self.run_control.fail_fast and "auth" in error_msg.lower():
                raise

    def _count_jsinfos(self, data: dict) -> int:
        """Count total JSinfos found across all pages."""
        count = 0
        pages = data.get("pages", {})
        for page_data in pages.values():
            extracted = page_data.get("extracted", {})
            if isinstance(extracted, dict):
                jsinfos = extracted.get("jsinfos", {})
                if isinstance(jsinfos, dict):
                    count += len(jsinfos)
        return count

    async def _parse_payment_details(
        self, 
        parsed_data: dict, 
        detail_responses: dict,
        detail_urls: dict,
        payment_requests_data: list,
        transactions_data: list
    ) -> None:
        """Parse detailed payment data from already-fetched modal responses."""
        from src.parse.payment_details import (
            parse_gocardless_modal,
            parse_transaction_modal,
        )
        from src.parse.redact import redact_json, redact_string
        
        payment_page = parsed_data.get("pages", {}).get("payment", {})
        if not payment_page:
            return
        
        extracted = payment_page.get("extracted", {})
        if not isinstance(extracted, dict):
            return
        
        # Build map: nr -> item data
        payment_requests_map = {item.get("nr"): item for item in payment_requests_data if item.get("nr")}
        transactions_map = {item.get("nr"): item for item in transactions_data if item.get("nr")}
        
        # Parse all detail responses and enrich items
        payment_requests_enriched = []
        transactions_enriched = []
        
        payment_request_fields_count = 0
        transaction_fields_count = 0
        
        for details_url, url_info in detail_urls.items():
            response = detail_responses.get(details_url)
            url_type = url_info.get("type")
            item = url_info.get("item", {})
            detail_nr = item.get("nr")  # This is transaction_nr or payment_request_nr, NOT cto_nr
            
            if not response or response.status_code != 200:
                # Log error but continue
                if response and response.status_code in (302, 401, 403):
                    logger.warning(f"[PAYMENT] Auth error for {url_type} details nr={detail_nr}: {response.status_code}")
                    item["fetch_error"] = f"auth_error_{response.status_code}"
                elif response:
                    logger.warning(f"[PAYMENT] HTTP error for {url_type} details nr={detail_nr}: {response.status_code}")
                    item["fetch_error"] = f"http_error_{response.status_code}"
                else:
                    logger.warning(f"[PAYMENT] No response for {url_type} details nr={detail_nr}")
                    item["fetch_error"] = "no_response"
                continue
            
            try:
                html_content = response.text
                if url_type == "gocardless" and detail_nr:
                    modal_data = parse_gocardless_modal(
                        html_content,
                        detail_nr,
                        details_url,
                    )
                    # Redact before storing
                    modal_data = redact_json(modal_data)
                    
                    # Merge item data with modal details
                    enriched_item = dict(item)  # Copy all fields from JSinfos
                    enriched_item["details"] = modal_data.get("details", {})
                    enriched_item["raw"] = modal_data.get("raw_fields", {})
                    
                    payment_requests_enriched.append(enriched_item)
                    payment_request_fields_count += len(modal_data.get("raw_fields", {}))
                        
                elif url_type == "transaction" and detail_nr:
                    modal_data = parse_transaction_modal(
                        html_content,
                        detail_nr,
                        details_url,
                    )
                    # Redact before storing
                    modal_data = redact_json(modal_data)
                    
                    # Merge item data with modal details
                    enriched_item = dict(item)  # Copy all fields from JSinfos
                    # Add structured modal fields
                    for key in ["type", "method", "date", "amount", "currency", 
                               "bank_account_label", "bank_account_href", 
                               "transaction_id", "invoice_ref"]:
                        if key in modal_data:
                            enriched_item[key] = modal_data[key]
                    enriched_item["raw"] = modal_data.get("raw_fields", {})
                    
                    transactions_enriched.append(enriched_item)
                    transaction_fields_count += len(modal_data.get("raw_fields", {}))
                        
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"[PAYMENT] Error parsing {url_type} details nr={detail_nr}: {error_msg}")
                # Redact error message before storing
                error_msg_redacted = redact_string(error_msg)
                item["fetch_error"] = error_msg_redacted[:200]  # Truncate
        
        # Log parsing results
        if self.dev_mode:
            logger.info(
                f"[PAYMENT] parsed modal fields: "
                f"transaction_fields={transaction_fields_count} "
                f"payment_request_fields={payment_request_fields_count}"
            )
        
        # Store enriched items (replace raw items with enriched ones)
        if payment_requests_enriched:
            extracted["payment_requests"] = payment_requests_enriched
        elif payment_requests_data:
            # If no modals were fetched, still store raw data
            extracted["payment_requests"] = payment_requests_data
        
        if transactions_enriched:
            extracted["transactions"] = transactions_enriched
        elif transactions_data:
            # If no modals were fetched, still store raw data
            extracted["transactions"] = transactions_data

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
                # Log pages count before writing
                pages_count = len(record.data.get("pages", {}))
                gate_passed = record.data.get("gate_passed", False)
                if gate_passed:
                    logger.debug(f"Flushing record nr={record.nr} gate_passed={gate_passed} pages_count={pages_count}")
                    if pages_count == 0:
                        logger.warning(f"Record nr={record.nr} has gate_passed=True but pages_count=0!")
                
                await self.writer.upsert_run_and_pages(
                    self.run_id,
                    record,
                    max_html_bytes=self.max_html_bytes if self.store_html else None,
                )
            # Delete spool file if it exists (from previous failed attempt)
            await self.spool.delete_batch(self.batch_id)
        except Exception as e:
            logger.warning(f"Supabase write failed, spooling to disk: {e}", exc_info=True)
            
            # Log error to Supabase (if writer is still available)
            if self.writer:
                import traceback
                try:
                    await self.writer.log_error(
                        run_id=self.run_id,
                        error_type="supabase_write_error",
                        error_message=str(e)[:500],
                        error_details={
                            "batch_id": self.batch_id,
                            "records_count": len(records),
                            "traceback": traceback.format_exc(),
                        },
                    )
                except Exception:
                    # Don't fail if error logging itself fails
                    pass
            
            # Write to spool (redacted)
            for record in records:
                # Redact before spooling
                record.data = redact_json(record.data)
                await self.spool.write_record(record, self.batch_id)

