"""SQLite state database for tracking progress."""
import aiosqlite
import logging
from pathlib import Path
from typing import Optional

from src.config import STATE_DB

logger = logging.getLogger(__name__)


class StateDB:
    """SQLite database for tracking scraping progress."""

    def __init__(self, db_path: Path = STATE_DB):
        self.db_path = db_path

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS scrape_progress (
                    nr INTEGER PRIMARY KEY,
                    status TEXT NOT NULL,
                    fetched_at TIMESTAMP,
                    error TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_status ON scrape_progress(status)
                """
            )
            await db.commit()
            logger.info(f"State database initialized at {self.db_path}")

    async def is_done(self, nr: int) -> bool:
        """Check if nr has been successfully processed."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT status FROM scrape_progress WHERE nr = ? AND status = 'ok'",
                (nr,),
            )
            row = await cursor.fetchone()
            return row is not None

    async def mark_done(self, nr: int) -> None:
        """Mark nr as successfully processed."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO scrape_progress (nr, status, fetched_at)
                VALUES (?, 'ok', datetime('now'))
                """,
                (nr,),
            )
            await db.commit()

    async def mark_failed(self, nr: int, error: str) -> None:
        """Mark nr as failed."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO scrape_progress (nr, status, fetched_at, error)
                VALUES (?, 'failed', datetime('now'), ?)
                """,
                (nr, error[:500]),  # Limit error length
            )
            await db.commit()

    async def mark_not_found(self, nr: int) -> None:
        """Mark nr as not found."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO scrape_progress (nr, status, fetched_at)
                VALUES (?, 'not_found', datetime('now'))
                """,
                (nr,),
            )
            await db.commit()

    async def get_next_undone(self, start: int, end: int) -> list[int]:
        """Get list of nr that haven't been processed yet."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT nr FROM scrape_progress
                WHERE nr >= ? AND nr <= ? AND status = 'ok'
                """,
                (start, end),
            )
            done_nrs = {row[0] for row in await cursor.fetchall()}
            all_nrs = set(range(start, end + 1))
            return sorted(all_nrs - done_nrs)

    async def get_stats(self) -> dict:
        """Get statistics about progress."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT status, COUNT(*) FROM scrape_progress
                GROUP BY status
                """
            )
            stats = {row[0]: row[1] for row in await cursor.fetchall()}
            return stats

