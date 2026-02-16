#!/usr/bin/env python3
"""
List Available Databases

Shows all *_rag.db files in the data/ directory with metadata:
- Which PDF each database corresponds to
- Which database is currently active (based on ACTIVE_PDF env var)
- File size, creation date
- Document count (if database is valid)

Usage:
    python scripts/list_databases.py
"""

import os
import sqlite3
from pathlib import Path
from datetime import datetime

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import PROJECT_ROOT, ACTIVE_PDF, DATABASE_NAME, SOURCE_PDFS_DIR, get_database_name_from_pdf


def get_document_count(db_path: Path) -> int:
    """Get count of documents in database."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def get_pdf_for_database(db_name: str) -> str:
    """Derive PDF filename from database name."""
    if db_name.endswith('_rag.db'):
        pdf_name = db_name[:-7] + '.pdf'  # Remove _rag.db, add .pdf
        return pdf_name
    return "Unknown"


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def format_date(timestamp: float) -> str:
    """Format timestamp as readable date."""
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M")


def main():
    """List all available databases."""
    data_dir = PROJECT_ROOT / "data"

    # Find all *_rag.db files
    db_files = sorted(data_dir.glob("*_rag.db"))

    if not db_files:
        print("No databases found in data/ directory.")
        print(f"\nTo create a database:")
        print(f"  1. Add a PDF to: {SOURCE_PDFS_DIR}")
        print(f"  2. Set ACTIVE_PDF: export ACTIVE_PDF=\"YourFile.pdf\"")
        print(f"  3. Run pipeline: python src/main.py")
        return

    print("=" * 80)
    print("Available Databases")
    print("=" * 80)

    for db_path in db_files:
        db_name = db_path.name
        is_active = (db_name == DATABASE_NAME)

        # Get metadata
        size = db_path.stat().st_size
        created = db_path.stat().st_ctime
        doc_count = get_document_count(db_path)
        pdf_name = get_pdf_for_database(db_name)

        # Check if PDF exists
        pdf_path = SOURCE_PDFS_DIR / pdf_name
        pdf_exists = pdf_path.exists()

        # Print status
        status = "[ACTIVE]" if is_active else "[ ]"
        print(f"\n  {status} {db_name}")
        print(f"           PDF: {pdf_name} {'✓' if pdf_exists else '✗ (missing)'}")
        print(f"           Size: {format_size(size)}")
        print(f"           Created: {format_date(created)}")
        print(f"           Documents: {doc_count}")

    print("\n" + "=" * 80)
    print(f"Currently Active: {DATABASE_NAME}")
    print(f"Set in src/config.py: ACTIVE_PDF = '{ACTIVE_PDF}'")
    print("=" * 80)

    print("\nTo switch databases:")
    print("  Edit src/config.py line ~165")
    print("  Change: ACTIVE_PDF = \"YourFile.pdf\"")


if __name__ == "__main__":
    main()
