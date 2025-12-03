"""
Database Schema Module for UCG-23 RAG ETL Pipeline

Defines the complete SQLite database schema including:
- Document registration and provenance tracking
- Hierarchical section structure (chapters, diseases, subsections)
- Raw parsed blocks for auditability
- Parent and child chunks for RAG retrieval
- Vector embeddings using sqlite-vec extension

Transaction boundaries are enforced at the pipeline step level.
"""

import sqlite3
from pathlib import Path
from typing import Optional
from loguru import logger

from src.config import (
    DATABASE_PATH,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_DIMENSION,
)


class SchemaError(Exception):
    """Raised when schema creation or validation fails."""
    pass


# ==================================
# Schema DDL Statements
# ==================================

# Documents table: Source PDF provenance and checksums
DOCUMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    part_number INTEGER NOT NULL,
    total_pages INTEGER,
    file_size_bytes INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT DEFAULT '{}',
    CONSTRAINT unique_part CHECK (part_number IN (1, 2))
);
"""

DOCUMENTS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash);",
    "CREATE INDEX IF NOT EXISTS idx_documents_part_number ON documents(part_number);",
]


# Embedding metadata: Model configuration for reproducibility
EMBEDDING_METADATA_TABLE = """
CREATE TABLE IF NOT EXISTS embedding_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    model_version TEXT,
    dimension INTEGER NOT NULL,
    token_encoding TEXT DEFAULT 'cl100k_base',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT DEFAULT '{}',
    CONSTRAINT valid_dimension CHECK (dimension > 0)
);
"""

EMBEDDING_METADATA_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_embedding_metadata_model ON embedding_metadata(model_name);",
]


# Sections table: Hierarchical structure (chapters ’ diseases ’ subsections)
SECTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    level INTEGER NOT NULL,
    heading TEXT NOT NULL,
    heading_path TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    CONSTRAINT valid_level CHECK (level >= 1)
);
"""

SECTIONS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_sections_document_id ON sections(document_id);",
    "CREATE INDEX IF NOT EXISTS idx_sections_order_index ON sections(document_id, order_index);",
    "CREATE INDEX IF NOT EXISTS idx_sections_level ON sections(level);",
    "CREATE INDEX IF NOT EXISTS idx_sections_heading_path ON sections(heading_path);",
]


# Raw blocks table: Parsed content from LlamaParse/Marker (auditability)
RAW_BLOCKS_TABLE = """
CREATE TABLE IF NOT EXISTS raw_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    block_type TEXT NOT NULL,
    text_content TEXT,
    markdown_content TEXT,
    page_number INTEGER NOT NULL,
    bbox TEXT,
    element_id TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    CONSTRAINT has_content CHECK (
        text_content IS NOT NULL OR markdown_content IS NOT NULL
    )
);
"""

RAW_BLOCKS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_raw_blocks_document_id ON raw_blocks(document_id);",
    "CREATE INDEX IF NOT EXISTS idx_raw_blocks_page_number ON raw_blocks(document_id, page_number);",
    "CREATE INDEX IF NOT EXISTS idx_raw_blocks_type ON raw_blocks(block_type);",
]


# Parent chunks table: Complete clinical topics (1000-1500 tokens)
PARENT_CHUNKS_TABLE = """
CREATE TABLE IF NOT EXISTS parent_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE CASCADE,
    CONSTRAINT valid_token_count CHECK (token_count > 0),
    CONSTRAINT valid_content CHECK (LENGTH(content) > 0)
);
"""

PARENT_CHUNKS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_parent_chunks_section_id ON parent_chunks(section_id);",
    "CREATE INDEX IF NOT EXISTS idx_parent_chunks_token_count ON parent_chunks(token_count);",
]


# Child chunks table: Retrieval units (256 tokens)
CHILD_CHUNKS_TABLE = """
CREATE TABLE IF NOT EXISTS child_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id INTEGER NOT NULL,
    section_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_id) REFERENCES parent_chunks(id) ON DELETE CASCADE,
    FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE CASCADE,
    CONSTRAINT valid_token_count CHECK (token_count > 0),
    CONSTRAINT valid_content CHECK (LENGTH(content) > 0),
    CONSTRAINT valid_chunk_index CHECK (chunk_index >= 0)
);
"""

CHILD_CHUNKS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_child_chunks_parent_id ON child_chunks(parent_id);",
    "CREATE INDEX IF NOT EXISTS idx_child_chunks_section_id ON child_chunks(section_id);",
    "CREATE INDEX IF NOT EXISTS idx_child_chunks_token_count ON child_chunks(token_count);",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_child_chunks_parent_index ON child_chunks(parent_id, chunk_index);",
]


# Vector embeddings table: sqlite-vec virtual table for child chunks
# IMPORTANT: This uses the sqlite-vec extension VIRTUAL TABLE syntax
VEC_CHILD_CHUNKS_TABLE = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS vec_child_chunks USING vec0(
    chunk_id INTEGER PRIMARY KEY,
    embedding FLOAT[{EMBEDDING_DIMENSION}]
);
"""

# No indexes needed for virtual table - vec0 handles indexing internally


# ==================================
# Schema Creation Function
# ==================================

def create_schema(db_path: Optional[Path] = None, force_recreate: bool = False) -> None:
    """
    Create complete database schema with all tables and indexes.

    Args:
        db_path: Path to SQLite database file (defaults to DATABASE_PATH from config)
        force_recreate: If True, drop all tables and recreate from scratch

    Raises:
        SchemaError: If schema creation fails
    """
    db_path = db_path or DATABASE_PATH

    logger.info(f"Creating database schema at: {db_path}")

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Enable foreign key constraints (critical for referential integrity)
        cursor.execute("PRAGMA foreign_keys = ON;")

        # Load sqlite-vec extension
        try:
            _load_sqlite_vec(conn)
            logger.info("sqlite-vec extension loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load sqlite-vec extension: {e}")
            raise SchemaError(
                "sqlite-vec extension is required but could not be loaded. "
                "Ensure sqlite-vec is installed and accessible."
            ) from e

        # Begin transaction for atomic schema creation
        conn.execute("BEGIN;")

        try:
            if force_recreate:
                logger.warning("Force recreate enabled - dropping all existing tables")
                _drop_all_tables(cursor)

            # Create tables in dependency order
            logger.info("Creating documents table...")
            cursor.execute(DOCUMENTS_TABLE)
            for idx_sql in DOCUMENTS_INDEXES:
                cursor.execute(idx_sql)

            logger.info("Creating embedding_metadata table...")
            cursor.execute(EMBEDDING_METADATA_TABLE)
            for idx_sql in EMBEDDING_METADATA_INDEXES:
                cursor.execute(idx_sql)

            logger.info("Creating sections table...")
            cursor.execute(SECTIONS_TABLE)
            for idx_sql in SECTIONS_INDEXES:
                cursor.execute(idx_sql)

            logger.info("Creating raw_blocks table...")
            cursor.execute(RAW_BLOCKS_TABLE)
            for idx_sql in RAW_BLOCKS_INDEXES:
                cursor.execute(idx_sql)

            logger.info("Creating parent_chunks table...")
            cursor.execute(PARENT_CHUNKS_TABLE)
            for idx_sql in PARENT_CHUNKS_INDEXES:
                cursor.execute(idx_sql)

            logger.info("Creating child_chunks table...")
            cursor.execute(CHILD_CHUNKS_TABLE)
            for idx_sql in CHILD_CHUNKS_INDEXES:
                cursor.execute(idx_sql)

            logger.info("Creating vec_child_chunks virtual table...")
            cursor.execute(VEC_CHILD_CHUNKS_TABLE)

            # Insert initial embedding metadata record
            cursor.execute("""
                INSERT OR IGNORE INTO embedding_metadata (model_name, model_version, dimension)
                VALUES (?, ?, ?)
            """, (EMBEDDING_MODEL_NAME, "v1.0", EMBEDDING_DIMENSION))

            # Commit transaction
            conn.commit()
            logger.success(f"Database schema created successfully at {db_path}")

        except Exception as e:
            conn.rollback()
            logger.error(f"Schema creation failed, rolling back: {e}")
            raise SchemaError(f"Failed to create schema: {e}") from e

    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise SchemaError(f"Database error: {e}") from e

    finally:
        if conn:
            conn.close()


def _load_sqlite_vec(conn: sqlite3.Connection) -> None:
    """
    Load sqlite-vec extension into the connection.

    Args:
        conn: SQLite connection object

    Raises:
        sqlite3.Error: If extension cannot be loaded
    """
    # Enable extension loading
    conn.enable_load_extension(True)

    try:
        # Try common extension paths
        extension_paths = [
            "vec0",  # If in system path
            "libsqlite_vec0",
            "./vec0",
        ]

        loaded = False
        for ext_path in extension_paths:
            try:
                conn.load_extension(ext_path)
                loaded = True
                break
            except sqlite3.Error:
                continue

        if not loaded:
            raise sqlite3.Error(
                "Could not load sqlite-vec extension from any known path. "
                "Install with: pip install sqlite-vec"
            )

    finally:
        # Disable extension loading for security
        conn.enable_load_extension(False)


def _drop_all_tables(cursor: sqlite3.Cursor) -> None:
    """
    Drop all tables in the database (used for force_recreate).

    Args:
        cursor: SQLite cursor object
    """
    tables = [
        "vec_child_chunks",  # Virtual table must be dropped first
        "child_chunks",
        "parent_chunks",
        "raw_blocks",
        "sections",
        "embedding_metadata",
        "documents",
    ]

    for table in tables:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table};")
            logger.debug(f"Dropped table: {table}")
        except sqlite3.Error as e:
            logger.warning(f"Could not drop table {table}: {e}")


def validate_schema(db_path: Optional[Path] = None) -> bool:
    """
    Validate that all required tables and indexes exist.

    Args:
        db_path: Path to SQLite database file (defaults to DATABASE_PATH from config)

    Returns:
        True if schema is valid, False otherwise
    """
    db_path = db_path or DATABASE_PATH

    if not db_path.exists():
        logger.error(f"Database file does not exist: {db_path}")
        return False

    required_tables = [
        "documents",
        "embedding_metadata",
        "sections",
        "raw_blocks",
        "parent_chunks",
        "child_chunks",
        "vec_child_chunks",
    ]

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check for required tables
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type IN ('table', 'view')
        """)
        existing_tables = {row[0] for row in cursor.fetchall()}

        missing_tables = set(required_tables) - existing_tables
        if missing_tables:
            logger.error(f"Missing tables: {missing_tables}")
            return False

        # Verify sqlite-vec is loaded by checking vec_child_chunks
        try:
            cursor.execute("SELECT COUNT(*) FROM vec_child_chunks;")
            logger.debug("sqlite-vec virtual table is accessible")
        except sqlite3.Error as e:
            logger.error(f"sqlite-vec virtual table check failed: {e}")
            return False

        logger.success("Schema validation passed")
        return True

    except sqlite3.Error as e:
        logger.error(f"Schema validation error: {e}")
        return False

    finally:
        if conn:
            conn.close()


def get_table_stats(db_path: Optional[Path] = None) -> dict:
    """
    Get row counts for all tables in the database.

    Args:
        db_path: Path to SQLite database file (defaults to DATABASE_PATH from config)

    Returns:
        Dictionary mapping table names to row counts
    """
    db_path = db_path or DATABASE_PATH

    if not db_path.exists():
        logger.error(f"Database file does not exist: {db_path}")
        return {}

    tables = [
        "documents",
        "embedding_metadata",
        "sections",
        "raw_blocks",
        "parent_chunks",
        "child_chunks",
        "vec_child_chunks",
    ]

    stats = {}

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table};")
                count = cursor.fetchone()[0]
                stats[table] = count
            except sqlite3.Error as e:
                logger.warning(f"Could not get stats for {table}: {e}")
                stats[table] = -1

        return stats

    except sqlite3.Error as e:
        logger.error(f"Error getting table stats: {e}")
        return {}

    finally:
        if conn:
            conn.close()


def print_schema_info(db_path: Optional[Path] = None) -> None:
    """
    Print detailed schema information for debugging.

    Args:
        db_path: Path to SQLite database file (defaults to DATABASE_PATH from config)
    """
    db_path = db_path or DATABASE_PATH

    print("\n" + "=" * 80)
    print("Database Schema Information")
    print("=" * 80)
    print(f"Database path: {db_path}")
    print(f"Database exists: {db_path.exists()}")

    if not db_path.exists():
        print("Database file not found. Run create_schema() first.")
        print("=" * 80 + "\n")
        return

    print(f"Database size: {db_path.stat().st_size / 1024 / 1024:.2f} MB")

    # Get table stats
    stats = get_table_stats(db_path)

    print("\nTable Row Counts:")
    print("-" * 80)
    for table, count in stats.items():
        status = "" if count >= 0 else ""
        print(f"  {status} {table:25s} {count:>10,} rows" if count >= 0 else f"  {status} {table:25s} ERROR")

    # Get embedding metadata
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT model_name, dimension, created_at FROM embedding_metadata LIMIT 1;")
        result = cursor.fetchone()

        if result:
            print("\nEmbedding Configuration:")
            print("-" * 80)
            print(f"  Model: {result[0]}")
            print(f"  Dimension: {result[1]}")
            print(f"  Created: {result[2]}")

        conn.close()

    except sqlite3.Error as e:
        logger.warning(f"Could not fetch embedding metadata: {e}")

    print("=" * 80 + "\n")


# ==================================
# Exports
# ==================================

__all__ = [
    "create_schema",
    "validate_schema",
    "get_table_stats",
    "print_schema_info",
    "SchemaError",
]
