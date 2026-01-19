"""Script to cleanup spool files."""
import argparse
import asyncio
import logging
from pathlib import Path

from src.config import SPOOL_DIR
from src.store.spool import SpoolManager

logger = logging.getLogger(__name__)


async def cleanup_spool(dry_run: bool = False, older_than_days: int = 7) -> None:
    """Cleanup old spool files."""
    import time
    
    spool = SpoolManager()
    cutoff_time = time.time() - (older_than_days * 24 * 60 * 60)
    
    deleted = 0
    total_size = 0
    
    for spool_file in spool.list_spool_files():
        stat = spool_file.stat()
        if stat.st_mtime < cutoff_time:
            size = stat.st_size
            if not dry_run:
                spool_file.unlink()
                logger.info(f"Deleted {spool_file.name} ({size} bytes)")
            else:
                logger.info(f"Would delete {spool_file.name} ({size} bytes)")
            deleted += 1
            total_size += size
    
    logger.info(f"Cleanup complete: {deleted} files, {total_size / 1024 / 1024:.2f} MB")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Cleanup spool files")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=7,
        help="Delete files older than N days (default: 7)",
    )
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    asyncio.run(cleanup_spool(args.dry_run, args.older_than_days))


if __name__ == "__main__":
    main()

