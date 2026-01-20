#!/usr/bin/env python3
"""Utility script to clean the state database."""
import sqlite3
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import STATE_DB


def clean_from_nr(min_nr: int) -> None:
    """Delete all records with nr >= min_nr."""
    conn = sqlite3.connect(STATE_DB)
    cursor = conn.cursor()
    
    # Count before deletion
    cursor.execute("SELECT COUNT(*) FROM scrape_progress WHERE nr >= ?", (min_nr,))
    count_before = cursor.fetchone()[0]
    
    if count_before == 0:
        print(f"No records found with nr >= {min_nr}")
        conn.close()
        return
    
    # Delete
    cursor.execute("DELETE FROM scrape_progress WHERE nr >= ?", (min_nr,))
    conn.commit()
    
    # Count after deletion
    cursor.execute("SELECT COUNT(*) FROM scrape_progress")
    count_remaining = cursor.fetchone()[0]
    
    print(f"Deleted {count_before} records with nr >= {min_nr}")
    print(f"Remaining records in database: {count_remaining}")
    
    conn.close()


def clean_range(min_nr: int, max_nr: int) -> None:
    """Delete all records with nr between min_nr and max_nr (inclusive)."""
    conn = sqlite3.connect(STATE_DB)
    cursor = conn.cursor()
    
    # Count before deletion
    cursor.execute(
        "SELECT COUNT(*) FROM scrape_progress WHERE nr >= ? AND nr <= ?",
        (min_nr, max_nr)
    )
    count_before = cursor.fetchone()[0]
    
    if count_before == 0:
        print(f"No records found with nr between {min_nr} and {max_nr}")
        conn.close()
        return
    
    # Delete
    cursor.execute(
        "DELETE FROM scrape_progress WHERE nr >= ? AND nr <= ?",
        (min_nr, max_nr)
    )
    conn.commit()
    
    # Count after deletion
    cursor.execute("SELECT COUNT(*) FROM scrape_progress")
    count_remaining = cursor.fetchone()[0]
    
    print(f"Deleted {count_before} records with nr between {min_nr} and {max_nr}")
    print(f"Remaining records in database: {count_remaining}")
    
    conn.close()


def show_stats() -> None:
    """Show statistics about the state database."""
    conn = sqlite3.connect(STATE_DB)
    cursor = conn.cursor()
    
    # Total count
    cursor.execute("SELECT COUNT(*) FROM scrape_progress")
    total = cursor.fetchone()[0]
    
    # Count by status
    cursor.execute("SELECT status, COUNT(*) FROM scrape_progress GROUP BY status")
    by_status = dict(cursor.fetchall())
    
    # Min and max nr
    cursor.execute("SELECT MIN(nr), MAX(nr) FROM scrape_progress")
    min_nr, max_nr = cursor.fetchone()
    
    print(f"State database: {STATE_DB}")
    print(f"Total records: {total}")
    print(f"Records by status: {by_status}")
    if min_nr is not None:
        print(f"NR range: {min_nr} - {max_nr}")
    else:
        print("NR range: (empty)")
    
    conn.close()


def delete_all() -> None:
    """Delete all records from the state database."""
    conn = sqlite3.connect(STATE_DB)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM scrape_progress")
    count = cursor.fetchone()[0]
    
    if count == 0:
        print("Database is already empty")
        conn.close()
        return
    
    cursor.execute("DELETE FROM scrape_progress")
    conn.commit()
    
    print(f"Deleted all {count} records from state database")
    
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/clean_state.py stats                    # Show statistics")
        print("  python scripts/clean_state.py delete-all               # Delete all records")
        print("  python scripts/clean_state.py from <nr>               # Delete records with nr >= <nr>")
        print("  python scripts/clean_state.py range <min> <max>        # Delete records between min and max")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "stats":
        show_stats()
    elif command == "delete-all":
        confirm = input("Are you sure you want to delete ALL records? (yes/no): ")
        if confirm.lower() == "yes":
            delete_all()
        else:
            print("Cancelled")
    elif command == "from":
        if len(sys.argv) < 3:
            print("Error: Please provide minimum nr")
            sys.exit(1)
        min_nr = int(sys.argv[2])
        clean_from_nr(min_nr)
    elif command == "range":
        if len(sys.argv) < 4:
            print("Error: Please provide min and max nr")
            sys.exit(1)
        min_nr = int(sys.argv[2])
        max_nr = int(sys.argv[3])
        clean_range(min_nr, max_nr)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

