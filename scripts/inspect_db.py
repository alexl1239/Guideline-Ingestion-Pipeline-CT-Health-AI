#!/usr/bin/env python3
"""
Database inspection script.

Quick utility to inspect the UCG database structure and contents.
"""

import sys
import sqlite3
from pathlib import Path
from typing import Optional

# Add project root to path for proper module resolution
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import DATABASE_PATH
from src.utils.logging_config import setup_logger, logger


def inspect_database(db_path: Optional[str] = None):
    """
    Inspect database and print summary.

    Args:
        db_path: Optional path to database (defaults to config)
    """
    if db_path is None:
        db_path = DATABASE_PATH

    if not Path(db_path).exists():
        logger.error(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    logger.info("=" * 80)
    logger.info("UCG-23 RAG DATABASE INSPECTION")
    logger.info("=" * 80)
    logger.info(f"Database: {db_path}")
    logger.info(f"Size: {Path(db_path).stat().st_size / (1024*1024):.2f} MB")
    logger.info("")

    # Documents
    logger.info("DOCUMENTS:")
    cursor.execute("SELECT id, title, version_label, checksum_sha256, created_at FROM documents")
    for row in cursor.fetchall():
        logger.info(f"  ID: {row[0]}")
        logger.info(f"  Title: {row[1]}")
        logger.info(f"  Version: {row[2]}")
        logger.info(f"  Checksum: {row[3][:16]}...")
        logger.info(f"  Created: {row[4]}")
    logger.info("")

    # Raw Blocks (Step 1 output)
    logger.info("RAW BLOCKS (Step 1 - Parsing):")
    cursor.execute("SELECT COUNT(*) FROM raw_blocks")
    raw_block_count = cursor.fetchone()[0]
    logger.info(f"  Total blocks: {raw_block_count:,}")

    if raw_block_count > 0:
        cursor.execute("""
            SELECT block_type, COUNT(*) as count
            FROM raw_blocks
            GROUP BY block_type
            ORDER BY count DESC
            LIMIT 10
        """)
        logger.info("  Block type distribution:")
        for row in cursor.fetchall():
            logger.info(f"    {row[0]}: {row[1]:,}")

        cursor.execute("""
            SELECT MIN(page_number) as first, MAX(page_number) as last,
                   COUNT(DISTINCT page_number) as unique_pages
            FROM raw_blocks
        """)
        first, last, unique = cursor.fetchone()
        logger.info(f"  Page coverage: {first} to {last} ({unique} unique pages)")
    else:
        logger.info("  (No raw blocks yet - run Step 1)")
    logger.info("")

    # Sections by level
    logger.info("SECTIONS BY LEVEL:")
    cursor.execute("""
        SELECT level, COUNT(*) as count
        FROM sections
        GROUP BY level
        ORDER BY level
    """)
    section_count = cursor.fetchall()
    if section_count:
        for row in section_count:
            level_name = {1: "Chapters", 2: "Diseases/Topics", 3: "Subsections"}.get(row[0], f"Level {row[0]}")
            logger.info(f"  {level_name}: {row[1]}")
    else:
        logger.info("  (No sections yet - run Step 2)")
    logger.info("")

    # Sample sections
    logger.info("SAMPLE SECTIONS:")
    cursor.execute("""
        SELECT level, heading, heading_path
        FROM sections
        ORDER BY order_index
        LIMIT 10
    """)
    sample_sections = cursor.fetchall()
    if sample_sections:
        for row in sample_sections:
            indent = "  " * row[0]
            logger.info(f"{indent}[L{row[0]}] {row[1]}")
    else:
        logger.info("  (No sections yet)")
    logger.info("")

    # Chunks
    logger.info("CHUNKS:")
    cursor.execute("SELECT COUNT(*) FROM parent_chunks")
    parent_count = cursor.fetchone()[0]
    logger.info(f"  Parent chunks: {parent_count}")

    cursor.execute("""
        SELECT AVG(token_count), MIN(token_count), MAX(token_count)
        FROM parent_chunks
    """)
    avg, min_val, max_val = cursor.fetchone()
    if avg is not None:
        logger.info(f"    Token stats: avg={avg:.1f}, min={min_val}, max={max_val}")
    else:
        logger.info(f"    Token stats: (no data yet)")

    cursor.execute("SELECT COUNT(*) FROM child_chunks")
    child_count = cursor.fetchone()[0]
    logger.info(f"  Child chunks: {child_count}")

    cursor.execute("""
        SELECT AVG(token_count), MIN(token_count), MAX(token_count)
        FROM child_chunks
    """)
    avg, min_val, max_val = cursor.fetchone()
    if avg is not None:
        logger.info(f"    Token stats: avg={avg:.1f}, min={min_val}, max={max_val}")
    else:
        logger.info(f"    Token stats: (no data yet)")
    logger.info("")

    # Embeddings
    logger.info("EMBEDDINGS:")
    try:
        cursor.execute("SELECT COUNT(*) FROM vec_child_chunks")
        embedding_count = cursor.fetchone()[0]
        logger.info(f"  Embedded chunks: {embedding_count}")

        cursor.execute("""
            SELECT block_type, COUNT(*) as count
            FROM raw_blocks
            GROUP BY block_type
            ORDER BY count DESC
        """)
        model_info = cursor.fetchone()
        if model_info:
            logger.info(f"  Model: {model_info[0]}")
            logger.info(f"  Dimension: {model_info[1]}")
            logger.info(f"  Created: {model_info[2]}")
    except sqlite3.OperationalError:
        logger.warning("  No embeddings table found")
    logger.info("")
    logger.info("=" * 80)

    conn.close()


def main():
    """Run database inspection."""
    import argparse

    # Initialize logging
    setup_logger()

    parser = argparse.ArgumentParser(description="Inspect UCG-23 RAG database")
    parser.add_argument("--db", type=str, help="Path to database (optional)")
    args = parser.parse_args()

    inspect_database(args.db)


if __name__ == "__main__":
    main()
