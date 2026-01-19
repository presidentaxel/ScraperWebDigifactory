"""Main entry point with CLI."""
import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config, Config
from src.logging_conf import setup_logging
from src.jobs.runner import ScrapeRunner

import logging

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="DigiFactory Scraper")
    
    # Range arguments
    parser.add_argument(
        "--nr",
        type=int,
        default=None,
        help="Scrape a single nr",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=None,
        help="Starting nr",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=None,
        help="Ending nr",
    )
    
    # Mode flags
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Development mode (safe defaults, verbose logs, local storage)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run: no Supabase writes, only local storage",
    )
    parser.add_argument(
        "--write-supabase",
        action="store_true",
        help="Explicitly enable Supabase writes (required in DEV mode)",
    )
    
    # Storage options
    parser.add_argument(
        "--store-html",
        action="store_true",
        help="Store compressed HTML files in DEV mode",
    )
    parser.add_argument(
        "--max-html-bytes",
        type=int,
        default=1_500_000,
        help="Maximum HTML size in bytes before skipping raw storage (default: 1.5MB)",
    )
    parser.add_argument(
        "--no-store-jsinfos",
        action="store_true",
        help="Don't store JSinfos (default: store)",
    )
    parser.add_argument(
        "--no-store-explorer",
        action="store_true",
        help="Don't store explorer links (default: store when gate passes)",
    )
    parser.add_argument(
        "--explorer-max-links",
        type=int,
        default=200,
        help="Maximum explorer links per page (default: 200)",
    )
    parser.add_argument(
        "--explorer-store",
        choices=["on", "off"],
        default="on",
        help="Store explorer links (default: on if gate passes)",
    )
    
    # Run control flags
    parser.add_argument(
        "--limit-gated",
        type=int,
        default=None,
        help="Stop after N sales that pass the gate",
    )
    parser.add_argument(
        "--stop-after-minutes",
        type=int,
        default=None,
        help="Stop after M minutes",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=None,
        help="Stop if total errors > N",
    )
    parser.add_argument(
        "--max-consecutive-errors",
        type=int,
        default=None,
        help="Stop if N consecutive errors",
    )
    parser.add_argument(
        "--max-403",
        type=int,
        default=None,
        help="Stop if 403 errors > N",
    )
    parser.add_argument(
        "--max-429",
        type=int,
        default=None,
        help="Stop if 429 errors > N",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first critical error (auth)",
    )
    
    # Auth modes
    parser.add_argument(
        "--cookie-only",
        action="store_true",
        help="Use only SESSION_COOKIE, never attempt login",
    )
    parser.add_argument(
        "--login-only",
        action="store_true",
        help="Ignore cookie, always login with USERNAME/PASSWORD",
    )
    
    # Performance arguments
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help=f"Concurrency level (default: {config.CONCURRENCY})",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint (default in PROD)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help=f"Batch size for Supabase (default: {config.BATCH_SIZE})",
    )
    
    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    # Setup logging
    setup_logging()

    # Parse args
    args = parse_args()

    # Determine mode
    is_dev = args.dev
    is_dry_run = args.dry_run
    write_supabase = args.write_supabase

    # Apply DEV mode defaults
    if is_dev:
        if args.start is None and args.end is None and args.nr is None:
            # Default DEV: single nr or small range
            if args.nr is None:
                args.start = 52000
                args.end = 52005
        if args.concurrency is None:
            config.CONCURRENCY = 2
        if args.batch_size is None:
            config.BATCH_SIZE = 10
        config.RATE_PER_DOMAIN = 0.5
        # Resume disabled in DEV by default
        if not args.resume:
            args.resume = False
        # Set log level to DEBUG for verbose output
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        # PROD mode: resume by default
        if not args.resume:
            args.resume = True

    # Determine range
    if args.nr:
        start = end = args.nr
    elif args.start is not None and args.end is not None:
        start = args.start
        end = args.end
    else:
        logger.error("Must specify either --nr or --start/--end")
        sys.exit(1)

    # Override config from args
    if args.concurrency:
        config.CONCURRENCY = args.concurrency
    if args.batch_size:
        config.BATCH_SIZE = args.batch_size

    # Security: DEV mode requires explicit --write-supabase
    if is_dev and not write_supabase:
        logger.warning("DEV mode: Supabase writes disabled (use --write-supabase to enable)")
        is_dry_run = True  # Force dry-run in DEV without explicit flag

    # Validate config (skip Supabase validation in dry-run)
    try:
        Config.validate(require_supabase=not is_dry_run)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    if is_dry_run:
        logger.info("DRY-RUN mode: Supabase writes disabled")

    logger.info("=" * 60)
    logger.info("DigiFactory Scraper Starting")
    logger.info(f"Mode: {'DEV' if is_dev else 'PROD'}")
    logger.info(f"Range: {start} - {end}")
    logger.info(f"Concurrency: {config.CONCURRENCY}")
    logger.info(f"Rate per domain: {config.RATE_PER_DOMAIN}")
    logger.info(f"Batch size: {config.BATCH_SIZE}")
    logger.info(f"Resume: {args.resume}")
    logger.info(f"Dry-run: {is_dry_run}")
    logger.info(f"Write Supabase: {write_supabase and not is_dry_run}")
    logger.info("=" * 60)

    # Run scraper
    runner = ScrapeRunner(
        start=start,
        end=end,
        resume=args.resume,
        dev_mode=is_dev,
        dry_run=is_dry_run,
        store_html=args.store_html,
        store_jsinfos=not args.no_store_jsinfos,
        store_explorer=not args.no_store_explorer and args.explorer_store == "on",
        max_html_bytes=args.max_html_bytes,
        explorer_max_links=args.explorer_max_links,
        limit_gated=args.limit_gated,
        stop_after_minutes=args.stop_after_minutes,
        max_errors=args.max_errors,
        max_consecutive_errors=args.max_consecutive_errors,
        max_403=args.max_403,
        max_429=args.max_429,
        fail_fast=args.fail_fast,
        cookie_only=args.cookie_only,
        login_only=args.login_only,
    )
    try:
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

