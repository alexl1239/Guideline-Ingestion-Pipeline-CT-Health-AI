"""
Database Connection Management for UCG-23 RAG ETL Pipeline

Provides thread-safe SQLite connection management with:
- sqlite-vec extension loading for vector embeddings
- Foreign key constraint enforcement
- Write-Ahead Logging (WAL) for better concurrency
- Performance optimizations (caching, memory temp storage)
- Proper transaction handling and cleanup
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from src.config import DATABASE_PATH
from src.utils.logging_config import logger


class ConnectionError(Exception):
    """Raised when database connection fails."""
    pass


class ExtensionError(Exception):
    """Raised when sqlite-vec extension cannot be loaded."""
    pass


def _load_sqlite_vec(conn: sqlite3.Connection) -> None:
    """
    Load sqlite-vec extension into the connection.

    This extension provides vector similarity search capabilities
    required for embedding storage and retrieval.

    Args:
        conn: SQLite connection object

    Raises:
        ExtensionError: If sqlite-vec extension cannot be loaded
    """
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        try:
            sqlite_vec.load(conn)
            logger.debug("sqlite-vec extension loaded successfully")
        finally:
            conn.enable_load_extension(False)

    except ImportError as e:
        error_msg = (
            "sqlite-vec extension is not installed. "
            "Install it with: pip install sqlite-vec"
        )
        logger.error(error_msg)
        raise ExtensionError(error_msg) from e

    except sqlite3.OperationalError as e:
        error_msg = (
            f"Failed to load sqlite-vec extension: {e}\n"
            "Ensure sqlite-vec is properly installed and compatible with your SQLite version."
        )
        logger.error(error_msg)
        raise ExtensionError(error_msg) from e


def _configure_connection(conn: sqlite3.Connection) -> None:
    """
    Configure SQLite connection with performance optimizations.

    Optimizations:
    - WAL mode: Write-Ahead Logging for better concurrency
    - NORMAL synchronous: Balance between safety and performance
    - 64MB cache: Improve query performance
    - Memory temp storage: Faster temporary table operations
    - Foreign keys: Enforce referential integrity

    Args:
        conn: SQLite connection object
    """
    cursor = conn.cursor()

    # Enable foreign key constraints (critical for referential integrity)
    cursor.execute("PRAGMA foreign_keys = ON;")
    logger.debug("Foreign key constraints enabled")

    # Write-Ahead Logging for better concurrency
    cursor.execute("PRAGMA journal_mode = WAL;")
    logger.debug("WAL mode enabled")

    # Balance safety and performance
    cursor.execute("PRAGMA synchronous = NORMAL;")
    logger.debug("Synchronous mode set to NORMAL")

    # 64MB cache for better performance
    cursor.execute("PRAGMA cache_size = -64000;")
    logger.debug("Cache size set to 64MB")

    # Use memory for temporary storage
    cursor.execute("PRAGMA temp_store = MEMORY;")
    logger.debug("Temp store set to MEMORY")

    cursor.close()


@contextmanager
def get_connection(
    db_path: Optional[Path] = None,
    read_only: bool = False,
) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for SQLite database connections.

    Provides a properly configured SQLite connection with:
    - sqlite-vec extension loaded
    - Foreign key constraints enabled
    - Performance optimizations applied
    - Automatic commit on success
    - Automatic rollback on error
    - Guaranteed cleanup

    Args:
        db_path: Path to SQLite database file (defaults to DATABASE_PATH from config)
        read_only: Open connection in read-only mode (default: False)

    Yields:
        sqlite3.Connection: Configured database connection

    Raises:
        ConnectionError: If connection cannot be established
        ExtensionError: If sqlite-vec extension cannot be loaded

    Example:
        >>> from src.database.connections import get_connection
        >>> with get_connection() as conn:
        ...     cursor = conn.cursor()
        ...     cursor.execute("SELECT COUNT(*) FROM documents")
        ...     count = cursor.fetchone()[0]
        ...     print(f"Documents: {count}")
    """
    db_path = db_path or DATABASE_PATH

    # Ensure parent directory exists
    if not read_only:
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = None

    try:
        # Open connection
        if read_only:
            # Read-only mode: file must exist
            if not db_path.exists():
                raise ConnectionError(f"Database file does not exist: {db_path}")
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            logger.debug(f"Opened read-only connection to: {db_path}")
        else:
            # Read-write mode
            conn = sqlite3.connect(str(db_path))
            logger.debug(f"Opened connection to: {db_path}")

        # Enable row factory for dict-like access
        conn.row_factory = sqlite3.Row

        # Load sqlite-vec extension
        _load_sqlite_vec(conn)

        # Configure connection
        _configure_connection(conn)

        # Yield connection to caller
        yield conn

        # Commit on successful completion
        if not read_only:
            conn.commit()
            logger.debug("Transaction committed successfully")

    except sqlite3.Error as e:
        # Rollback on error
        if conn and not read_only:
            conn.rollback()
            logger.warning("Transaction rolled back due to error")

        error_msg = f"Database error: {e}"
        logger.error(error_msg)
        raise ConnectionError(error_msg) from e

    except Exception as e:
        # Rollback on any other error
        if conn and not read_only:
            conn.rollback()
            logger.warning("Transaction rolled back due to error")
        raise

    finally:
        # Always close connection
        if conn:
            conn.close()
            logger.debug("Connection closed")


def init_database(
    db_path: Optional[Path] = None,
    force_recreate: bool = False,
) -> sqlite3.Connection:
    """
    Initialize database with schema and sqlite-vec extension.

    Creates the database file if it doesn't exist, loads the sqlite-vec
    extension, and creates all required tables and indexes.

    Args:
        db_path: Path to SQLite database file (defaults to DATABASE_PATH from config)
        force_recreate: If True, drop all existing tables and recreate (default: False)

    Returns:
        sqlite3.Connection: Configured database connection (caller must close)

    Raises:
        ConnectionError: If database initialization fails
        ExtensionError: If sqlite-vec extension cannot be loaded

    Example:
        >>> from src.database.connections import init_database
        >>> conn = init_database()
        >>> try:
        ...     cursor = conn.cursor()
        ...     cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ...     tables = cursor.fetchall()
        ...     print(f"Tables: {[t[0] for t in tables]}")
        ... finally:
        ...     conn.close()
    """
    from src.database.schema import create_schema

    db_path = db_path or DATABASE_PATH

    logger.info(f"Initializing database at: {db_path}")

    try:
        # Create schema (handles connection internally)
        create_schema(db_path=db_path, force_recreate=force_recreate)

        # Open and return a new connection
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Load sqlite-vec extension
        _load_sqlite_vec(conn)

        # Configure connection
        _configure_connection(conn)

        logger.info(f"Database initialized successfully: {db_path}")

        return conn

    except Exception as e:
        error_msg = f"Failed to initialize database: {e}"
        logger.error(error_msg)
        raise ConnectionError(error_msg) from e


def verify_connection(db_path: Optional[Path] = None) -> bool:
    """
    Verify that database connection works and sqlite-vec is available.

    Args:
        db_path: Path to SQLite database file (defaults to DATABASE_PATH from config)

    Returns:
        bool: True if connection successful and sqlite-vec loaded

    Example:
        >>> from src.database.connections import verify_connection
        >>> if verify_connection():
        ...     print("Database connection verified!")
    """
    db_path = db_path or DATABASE_PATH

    try:
        with get_connection(db_path=db_path, read_only=True) as conn:
            cursor = conn.cursor()

            # Test basic query
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

            if result[0] != 1:
                logger.error("Basic query test failed")
                return False

            logger.info("Database connection verified successfully")
            return True

    except Exception as e:
        logger.error(f"Connection verification failed: {e}")
        return False


__all__ = [
    "get_connection",
    "init_database",
    "verify_connection",
    "ConnectionError",
    "ExtensionError",
]
