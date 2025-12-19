"""
Pytest configuration and shared fixtures for UCG-23 RAG ETL Pipeline tests.

Provides common test fixtures, utilities, and configuration for unit and
integration tests.
"""

import tempfile
from pathlib import Path
from typing import Generator
import sqlite3

import pytest


@pytest.fixture
def temp_db() -> Generator[Path, None, None]:
    """
    Create a temporary database file for testing.

    Yields:
        Path to temporary database file

    Cleanup:
        Automatically removes temp file after test

    Example:
        >>> def test_something(temp_db):
        ...     create_schema(db_path=temp_db)
        ...     assert temp_db.exists()
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path
        # Cleanup happens automatically when context exits


@pytest.fixture
def temp_db_with_schema(temp_db: Path) -> Path:
    """
    Create a temporary database with schema already created.

    Args:
        temp_db: Temporary database path fixture

    Returns:
        Path to database with schema

    Example:
        >>> def test_insertion(temp_db_with_schema):
        ...     # Schema already exists, can insert directly
        ...     conn = sqlite3.connect(str(temp_db_with_schema))
    """
    from src.database.schema import create_schema

    create_schema(db_path=temp_db, force_recreate=False)
    return temp_db


@pytest.fixture
def sample_embedding() -> list[float]:
    """
    Generate a sample embedding vector for testing.

    Returns:
        List of floats representing a 1536-dimension embedding

    Note:
        Uses small values to avoid numerical issues in tests
    """
    # Create a simple pattern instead of random for reproducibility
    return [0.1 * (i % 10) for i in range(1536)]


def get_table_names(db_path: Path) -> set[str]:
    """
    Helper function to get all table names from a database.

    Args:
        db_path: Path to SQLite database

    Returns:
        Set of table names

    Example:
        >>> tables = get_table_names(temp_db)
        >>> assert "documents" in tables
    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type IN ('table', 'view')
        AND name NOT LIKE 'sqlite_%'
    """)

    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    return tables


def get_index_names(db_path: Path, table_name: str) -> set[str]:
    """
    Helper function to get all index names for a table.

    Args:
        db_path: Path to SQLite database
        table_name: Name of table to check

    Returns:
        Set of index names
    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute(f"PRAGMA index_list({table_name})")
    indexes = {row[1] for row in cursor.fetchall()}

    conn.close()
    return indexes


def get_column_info(db_path: Path, table_name: str) -> list[dict]:
    """
    Helper function to get column information for a table.

    Args:
        db_path: Path to SQLite database
        table_name: Name of table to inspect

    Returns:
        List of dicts with column info (cid, name, type, notnull, dflt_value, pk)
    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = []
    for row in cursor.fetchall():
        columns.append({
            'cid': row[0],
            'name': row[1],
            'type': row[2],
            'notnull': row[3],
            'dflt_value': row[4],
            'pk': row[5],
        })

    conn.close()
    return columns


# Export helper functions for use in tests
__all__ = [
    'temp_db',
    'temp_db_with_schema',
    'sample_embedding',
    'get_table_names',
    'get_index_names',
    'get_column_info',
]
