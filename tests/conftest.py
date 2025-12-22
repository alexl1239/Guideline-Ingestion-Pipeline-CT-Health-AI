"""
Pytest configuration and shared fixtures for UCG-23 RAG ETL Pipeline tests.

Provides common test fixtures, utilities, and configuration for unit and
integration tests.
"""

import tempfile
from pathlib import Path
from typing import Generator, Tuple
import sqlite3

import pytest

# Test data paths
FIXTURES_DIR = Path(__file__).parent / "fixtures"
OUTPUTS_DIR = Path(__file__).parent / "outputs"

# Ensure outputs directory exists
OUTPUTS_DIR.mkdir(exist_ok=True)


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


@pytest.fixture
def test_pdf_4_pages() -> Path:
    """
    Path to 4-page test PDF.

    Returns:
        Path to tests/fixtures/ucg_4_pages.pdf
    """
    pdf_path = FIXTURES_DIR / "ucg_4_pages.pdf"
    if not pdf_path.exists():
        pytest.skip(f"Test PDF not found: {pdf_path}")
    return pdf_path


@pytest.fixture
def test_pdf_15_pages() -> Path:
    """
    Path to 15-page test PDF.

    Returns:
        Path to tests/fixtures/ucg_15_pages.pdf
    """
    pdf_path = FIXTURES_DIR / "ucg_15_pages.pdf"
    if not pdf_path.exists():
        pytest.skip(f"Test PDF not found: {pdf_path}")
    return pdf_path


@pytest.fixture
def golden_db_4_pages() -> Path:
    """
    Path to golden database for 4-page test.

    Returns:
        Path to tests/fixtures/golden_4pages.db
    """
    db_path = FIXTURES_DIR / "golden_4pages.db"
    if not db_path.exists() or db_path.stat().st_size == 0:
        pytest.skip(f"Golden database not found or empty: {db_path}")
    return db_path


@pytest.fixture
def golden_db_15_pages() -> Path:
    """
    Path to golden database for 15-page test.

    Returns:
        Path to tests/fixtures/golden_15pages.db
    """
    db_path = FIXTURES_DIR / "golden_15pages.db"
    if not db_path.exists() or db_path.stat().st_size == 0:
        pytest.skip(f"Golden database not found or empty: {db_path}")
    return db_path


@pytest.fixture
def test_output_db(request) -> Generator[Path, None, None]:
    """
    Create a test output database that persists for inspection.

    Database is saved to tests/outputs/ with test name.
    Useful for debugging test failures.

    Yields:
        Path to test output database

    Example:
        >>> def test_something(test_output_db):
        ...     # Use test_output_db
        ...     # After test, inspect: tests/outputs/test_something.db
    """
    test_name = request.node.name
    db_path = OUTPUTS_DIR / f"{test_name}.db"

    # Clean up old test database
    if db_path.exists():
        db_path.unlink()

    yield db_path

    # Keep database for inspection
    # (User can manually delete tests/outputs/ to clean up)


@pytest.fixture
def temp_db_with_registered_doc_4_pages(test_output_db: Path, test_pdf_4_pages: Path) -> Tuple[Path, str]:
    """
    Create a test database with schema and registered 4-page document.

    Args:
        test_output_db: Output database fixture
        test_pdf_4_pages: 4-page test PDF fixture

    Returns:
        Tuple of (db_path, document_id)
    """
    from src.database.schema import create_schema

    create_schema(db_path=test_output_db, force_recreate=True)

    # Register document
    conn = sqlite3.connect(str(test_output_db))
    cursor = conn.cursor()

    import hashlib
    with open(test_pdf_4_pages, 'rb') as f:
        checksum = hashlib.sha256(f.read()).hexdigest()

    doc_id = "test-doc-4pages"
    cursor.execute("""
        INSERT INTO documents (id, title, version_label, checksum_sha256)
        VALUES (?, ?, ?, ?)
    """, (doc_id, "Test Document 4 Pages", "v1.0", checksum))

    # Insert embedding metadata
    cursor.execute("""
        INSERT OR IGNORE INTO embedding_metadata
        (model_name, dimension, docling_version, created_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, ("text-embedding-3-small", 1536, "2.0.0"))

    conn.commit()
    conn.close()

    return test_output_db, doc_id


@pytest.fixture
def temp_db_with_registered_doc_15_pages(test_output_db: Path, test_pdf_15_pages: Path) -> Tuple[Path, str]:
    """
    Create a test database with schema and registered 15-page document.

    Args:
        test_output_db: Output database fixture
        test_pdf_15_pages: 15-page test PDF fixture

    Returns:
        Tuple of (db_path, document_id)
    """
    from src.database.schema import create_schema

    create_schema(db_path=test_output_db, force_recreate=True)

    # Register document
    conn = sqlite3.connect(str(test_output_db))
    cursor = conn.cursor()

    import hashlib
    with open(test_pdf_15_pages, 'rb') as f:
        checksum = hashlib.sha256(f.read()).hexdigest()

    doc_id = "test-doc-15pages"
    cursor.execute("""
        INSERT INTO documents (id, title, version_label, checksum_sha256)
        VALUES (?, ?, ?, ?)
    """, (doc_id, "Test Document 15 Pages", "v1.0", checksum))

    # Insert embedding metadata
    cursor.execute("""
        INSERT OR IGNORE INTO embedding_metadata
        (model_name, dimension, docling_version, created_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, ("text-embedding-3-small", 1536, "2.0.0"))

    conn.commit()
    conn.close()

    return test_output_db, doc_id


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


# Export helper functions and fixtures for use in tests
__all__ = [
    'temp_db',
    'temp_db_with_schema',
    'sample_embedding',
    'test_pdf_4_pages',
    'test_pdf_15_pages',
    'golden_db_4_pages',
    'golden_db_15_pages',
    'test_output_db',
    'temp_db_with_registered_doc_4_pages',
    'temp_db_with_registered_doc_15_pages',
    'get_table_names',
    'get_index_names',
    'get_column_info',
]
