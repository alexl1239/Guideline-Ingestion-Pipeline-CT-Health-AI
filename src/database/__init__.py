"""
Database Module for UCG-23 RAG ETL Pipeline

Provides database connection management and schema definitions for SQLite
with sqlite-vec extension support.
"""

from src.database.connections import (
    get_connection,
    init_database,
    verify_connection,
    ConnectionError,
    ExtensionError,
)
from src.database.schema import (
    create_schema,
    validate_schema,
    get_table_stats,
    print_schema_info,
    SchemaError,
)

__all__ = [
    # Connection management
    "get_connection",
    "init_database",
    "verify_connection",
    "ConnectionError",
    "ExtensionError",
    # Schema management
    "create_schema",
    "validate_schema",
    "get_table_stats",
    "print_schema_info",
    "SchemaError",
]
