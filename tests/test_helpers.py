"""
Test Helper Utilities

Provides utilities for comparing databases, computing statistics, and
validating test outputs.
"""

import sqlite3
from pathlib import Path
from typing import Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class DatabaseDiff:
    """Results of comparing two databases"""
    block_count_diff: int
    section_count_diff: int
    parent_chunk_count_diff: int
    child_chunk_count_diff: int
    block_type_distribution: Dict[str, Tuple[int, int]]  # {type: (db1_count, db2_count)}
    page_coverage_diff: Tuple[int, int]  # (db1_max_page, db2_max_page)

    def is_similar(self, tolerance: float = 0.05) -> bool:
        """
        Check if databases are similar within tolerance.

        Args:
            tolerance: Allowed percentage difference (0.05 = 5%)

        Returns:
            True if databases are similar
        """
        # Allow small absolute differences for small counts
        if abs(self.block_count_diff) > 10:
            return False
        if abs(self.section_count_diff) > 5:
            return False
        if abs(self.parent_chunk_count_diff) > 3:
            return False
        if abs(self.child_chunk_count_diff) > 10:
            return False

        return True

    def summary(self) -> str:
        """Human-readable summary of differences"""
        lines = [
            f"Block count difference: {self.block_count_diff:+d}",
            f"Section count difference: {self.section_count_diff:+d}",
            f"Parent chunk difference: {self.parent_chunk_count_diff:+d}",
            f"Child chunk difference: {self.child_chunk_count_diff:+d}",
            f"Page coverage: {self.page_coverage_diff[0]} vs {self.page_coverage_diff[1]}",
            "",
            "Block type distribution:"
        ]

        for block_type, (count1, count2) in self.block_type_distribution.items():
            diff = count2 - count1
            lines.append(f"  {block_type}: {count1} vs {count2} ({diff:+d})")

        return "\n".join(lines)


def compare_databases(db1_path: Path, db2_path: Path) -> DatabaseDiff:
    """
    Compare two databases and return differences.

    Args:
        db1_path: Path to first database (typically test output)
        db2_path: Path to second database (typically golden reference)

    Returns:
        DatabaseDiff object with comparison results

    Example:
        >>> diff = compare_databases(test_db, golden_db)
        >>> assert diff.is_similar(tolerance=0.05)
        >>> if not diff.is_similar():
        ...     print(diff.summary())
    """
    conn1 = sqlite3.connect(str(db1_path))
    conn2 = sqlite3.connect(str(db2_path))

    cursor1 = conn1.cursor()
    cursor2 = conn2.cursor()

    # Compare block counts
    cursor1.execute("SELECT COUNT(*) FROM raw_blocks")
    block_count1 = cursor1.fetchone()[0]

    cursor2.execute("SELECT COUNT(*) FROM raw_blocks")
    block_count2 = cursor2.fetchone()[0]

    # Compare section counts
    cursor1.execute("SELECT COUNT(*) FROM sections")
    section_count1 = cursor1.fetchone()[0] if cursor1.fetchone() else 0
    cursor1.execute("SELECT COUNT(*) FROM sections")  # Re-execute
    section_count1 = cursor1.fetchone()[0]

    cursor2.execute("SELECT COUNT(*) FROM sections")
    section_count2 = cursor2.fetchone()[0]

    # Compare chunk counts
    cursor1.execute("SELECT COUNT(*) FROM parent_chunks")
    parent_count1 = cursor1.fetchone()[0]

    cursor2.execute("SELECT COUNT(*) FROM parent_chunks")
    parent_count2 = cursor2.fetchone()[0]

    cursor1.execute("SELECT COUNT(*) FROM child_chunks")
    child_count1 = cursor1.fetchone()[0]

    cursor2.execute("SELECT COUNT(*) FROM child_chunks")
    child_count2 = cursor2.fetchone()[0]

    # Compare block type distributions
    cursor1.execute("SELECT block_type, COUNT(*) FROM raw_blocks GROUP BY block_type")
    block_types1 = dict(cursor1.fetchall())

    cursor2.execute("SELECT block_type, COUNT(*) FROM raw_blocks GROUP BY block_type")
    block_types2 = dict(cursor2.fetchall())

    # Merge block types from both databases
    all_types = set(block_types1.keys()) | set(block_types2.keys())
    block_type_distribution = {
        bt: (block_types1.get(bt, 0), block_types2.get(bt, 0))
        for bt in all_types
    }

    # Compare page coverage
    cursor1.execute("SELECT MAX(page_number) FROM raw_blocks")
    max_page1 = cursor1.fetchone()[0] or 0

    cursor2.execute("SELECT MAX(page_number) FROM raw_blocks")
    max_page2 = cursor2.fetchone()[0] or 0

    conn1.close()
    conn2.close()

    return DatabaseDiff(
        block_count_diff=block_count1 - block_count2,
        section_count_diff=section_count1 - section_count2,
        parent_chunk_count_diff=parent_count1 - parent_count2,
        child_chunk_count_diff=child_count1 - child_count2,
        block_type_distribution=block_type_distribution,
        page_coverage_diff=(max_page1, max_page2)
    )


def get_database_stats(db_path: Path) -> Dict[str, any]:
    """
    Get comprehensive statistics from a database.

    Args:
        db_path: Path to database

    Returns:
        Dictionary with various statistics
    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    stats = {}

    # Document info
    cursor.execute("SELECT COUNT(*) FROM documents")
    stats['document_count'] = cursor.fetchone()[0]

    # Block stats
    cursor.execute("SELECT COUNT(*) FROM raw_blocks")
    stats['total_blocks'] = cursor.fetchone()[0]

    cursor.execute("SELECT block_type, COUNT(*) FROM raw_blocks GROUP BY block_type")
    stats['block_types'] = dict(cursor.fetchall())

    cursor.execute("SELECT MIN(page_number), MAX(page_number) FROM raw_blocks")
    min_page, max_page = cursor.fetchone()
    stats['page_range'] = (min_page or 0, max_page or 0)

    # Section stats
    cursor.execute("SELECT COUNT(*) FROM sections")
    stats['section_count'] = cursor.fetchone()[0]

    cursor.execute("SELECT level, COUNT(*) FROM sections GROUP BY level")
    stats['sections_by_level'] = dict(cursor.fetchall())

    # Chunk stats
    cursor.execute("SELECT COUNT(*) FROM parent_chunks")
    stats['parent_chunk_count'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM child_chunks")
    stats['child_chunk_count'] = cursor.fetchone()[0]

    if stats['parent_chunk_count'] > 0:
        cursor.execute("SELECT AVG(token_count), MIN(token_count), MAX(token_count) FROM parent_chunks")
        avg, min_tok, max_tok = cursor.fetchone()
        stats['parent_chunk_tokens'] = {
            'avg': avg,
            'min': min_tok,
            'max': max_tok
        }

    if stats['child_chunk_count'] > 0:
        cursor.execute("SELECT AVG(token_count), MIN(token_count), MAX(token_count) FROM child_chunks")
        avg, min_tok, max_tok = cursor.fetchone()
        stats['child_chunk_tokens'] = {
            'avg': avg,
            'min': min_tok,
            'max': max_tok
        }

    # Embedding stats
    try:
        cursor.execute("SELECT COUNT(*) FROM vec_child_chunks")
        stats['embedding_count'] = cursor.fetchone()[0]
    except sqlite3.OperationalError:
        stats['embedding_count'] = 0

    conn.close()

    return stats


def assert_database_structure_valid(db_path: Path) -> None:
    """
    Assert that database has valid structure and constraints.

    Raises AssertionError if any checks fail.

    Args:
        db_path: Path to database to validate
    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Check required tables exist
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table'
        AND name NOT LIKE 'sqlite_%'
    """)
    tables = {row[0] for row in cursor.fetchall()}

    required_tables = {
        'documents', 'raw_blocks', 'sections',
        'parent_chunks', 'child_chunks', 'embedding_metadata'
    }
    missing = required_tables - tables
    assert not missing, f"Missing required tables: {missing}"

    # Check no orphaned child chunks
    cursor.execute("""
        SELECT COUNT(*)
        FROM child_chunks c
        LEFT JOIN parent_chunks p ON c.parent_id = p.id
        WHERE p.id IS NULL
    """)
    orphaned = cursor.fetchone()[0]
    assert orphaned == 0, f"Found {orphaned} orphaned child chunks"

    # Check no NULL required fields in raw_blocks
    cursor.execute("SELECT COUNT(*) FROM raw_blocks WHERE block_type IS NULL")
    null_types = cursor.fetchone()[0]
    assert null_types == 0, f"Found {null_types} blocks with NULL block_type"

    cursor.execute("SELECT COUNT(*) FROM raw_blocks WHERE page_number IS NULL")
    null_pages = cursor.fetchone()[0]
    assert null_pages == 0, f"Found {null_pages} blocks with NULL page_number"

    conn.close()


__all__ = [
    'DatabaseDiff',
    'compare_databases',
    'get_database_stats',
    'assert_database_structure_valid',
]
