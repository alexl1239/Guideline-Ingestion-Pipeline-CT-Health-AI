#!/usr/bin/env python3
"""
Database inspection script.

Quick utility to inspect the UCG database structure and contents.
"""

import sys
import sqlite3
from pathlib import Path
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config import DATABASE_PATH


def inspect_database(db_path: Optional[str] = None):
    """
    Inspect database and print summary.

    Args:
        db_path: Optional path to database (defaults to config)
    """
    if db_path is None:
        db_path = DATABASE_PATH

    if not Path(db_path).exists():
        print(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 80)
    print("UCG-23 RAG DATABASE INSPECTION")
    print("=" * 80)
    print(f"Database: {db_path}")
    print(f"Size: {Path(db_path).stat().st_size / (1024*1024):.2f} MB")
    print()

    # Documents
    print("DOCUMENTS:")
    cursor.execute("SELECT id, title, version_label, checksum_sha256, created_at FROM documents")
    for row in cursor.fetchall():
        print(f"  ID: {row[0]}")
        print(f"  Title: {row[1]}")
        print(f"  Version: {row[2]}")
        print(f"  Checksum: {row[3][:16]}...")
        print(f"  Created: {row[4]}")
    print()

    # Sections by level
    print("SECTIONS BY LEVEL:")
    cursor.execute("""
        SELECT level, COUNT(*) as count
        FROM sections
        GROUP BY level
        ORDER BY level
    """)
    for row in cursor.fetchall():
        level_name = {1: "Chapters", 2: "Diseases/Topics", 3: "Subsections"}.get(row[0], f"Level {row[0]}")
        print(f"  {level_name}: {row[1]}")
    print()

    # Sample sections
    print("SAMPLE SECTIONS:")
    cursor.execute("""
        SELECT level, heading, heading_path
        FROM sections
        ORDER BY order_index
        LIMIT 10
    """)
    for row in cursor.fetchall():
        indent = "  " * row[0]
        print(f"{indent}[L{row[0]}] {row[1]}")
    print()

    # Chunks
    print("CHUNKS:")
    cursor.execute("SELECT COUNT(*) FROM parent_chunks")
    parent_count = cursor.fetchone()[0]
    print(f"  Parent chunks: {parent_count}")

    cursor.execute("""
        SELECT AVG(token_count), MIN(token_count), MAX(token_count)
        FROM parent_chunks
    """)
    avg, min_val, max_val = cursor.fetchone()
    print(f"    Token stats: avg={avg:.1f}, min={min_val}, max={max_val}")

    cursor.execute("SELECT COUNT(*) FROM child_chunks")
    child_count = cursor.fetchone()[0]
    print(f"  Child chunks: {child_count}")

    cursor.execute("""
        SELECT AVG(token_count), MIN(token_count), MAX(token_count)
        FROM child_chunks
    """)
    avg, min_val, max_val = cursor.fetchone()
    print(f"    Token stats: avg={avg:.1f}, min={min_val}, max={max_val}")
    print()

    # Embeddings
    print("EMBEDDINGS:")
    try:
        cursor.execute("SELECT COUNT(*) FROM vec_child_chunks")
        embedding_count = cursor.fetchone()[0]
        print(f"  Embedded chunks: {embedding_count}")

        cursor.execute("""
            SELECT model_name, dimension, created_at
            FROM embedding_metadata
            ORDER BY created_at DESC
            LIMIT 1
        """)
        model_info = cursor.fetchone()
        if model_info:
            print(f"  Model: {model_info[0]}")
            print(f"  Dimension: {model_info[1]}")
            print(f"  Created: {model_info[2]}")
    except sqlite3.OperationalError:
        print("  No embeddings table found")
    print()

    # Raw blocks
    print("RAW BLOCKS:")
    cursor.execute("SELECT COUNT(*) FROM raw_blocks")
    block_count = cursor.fetchone()[0]
    print(f"  Total blocks: {block_count}")

    cursor.execute("""
        SELECT block_type, COUNT(*) as count
        FROM raw_blocks
        GROUP BY block_type
        ORDER BY count DESC
    """)
    print("  By type:")
    for row in cursor.fetchall():
        print(f"    {row[0]}: {row[1]}")

    print("=" * 80)

    conn.close()


def main():
    """Run database inspection."""
    import argparse

    parser = argparse.ArgumentParser(description="Inspect UCG-23 RAG database")
    parser.add_argument("--db", type=str, help="Path to database (optional)")
    args = parser.parse_args()

    inspect_database(args.db)


if __name__ == "__main__":
    main()
