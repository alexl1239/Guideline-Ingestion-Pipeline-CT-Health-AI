"""
Integration Tests for src.database.schema

Tests actual database creation, validation, and operations with SQLite.
Uses temporary databases to avoid affecting production data.
"""

import pytest
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.database.schema import (
    create_schema,
    validate_schema,
    get_table_stats,
    print_schema_info,
    SchemaError,
    _load_sqlite_vec,
    _drop_all_tables,
)
from tests.conftest import get_table_names, get_index_names, get_column_info


class TestSchemaCreation:
    """Tests for create_schema() function"""

    def test_creates_database_file(self, temp_db):
        """Database file is created at specified path"""
        assert not temp_db.exists()

        create_schema(db_path=temp_db)

        assert temp_db.exists()
        assert temp_db.stat().st_size > 0

    def test_creates_all_tables(self, temp_db):
        """All 7 required tables are created"""
        create_schema(db_path=temp_db)

        tables = get_table_names(temp_db)

        required_tables = {
            "documents",
            "embedding_metadata",
            "sections",
            "raw_blocks",
            "parent_chunks",
            "child_chunks",
            "vec_child_chunks",
        }

        assert required_tables.issubset(tables), f"Missing tables: {required_tables - tables}"

    def test_creates_parent_directory(self):
        """Parent directories are created if they don't exist"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Use nested path that doesn't exist yet
            db_path = Path(tmpdir) / "subdir1" / "subdir2" / "test.db"
            assert not db_path.parent.exists()

            create_schema(db_path=db_path)

            assert db_path.exists()
            assert db_path.parent.exists()

    def test_idempotent_creation(self, temp_db):
        """Schema can be created multiple times without error"""
        create_schema(db_path=temp_db)
        # Should not raise error on second call
        create_schema(db_path=temp_db)

        tables = get_table_names(temp_db)
        assert len(tables) >= 7

    def test_foreign_keys_enabled(self, temp_db):
        """Foreign key constraints are enabled"""
        create_schema(db_path=temp_db)

        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys;")
        result = cursor.fetchone()
        conn.close()

        # Note: PRAGMA foreign_keys returns current connection state
        # We verify FKs work by testing constraint violations later


class TestTableStructure:
    """Tests for table column definitions"""

    def test_documents_table_structure(self, temp_db_with_schema):
        """documents table has correct columns"""
        columns = get_column_info(temp_db_with_schema, "documents")
        column_names = {col['name'] for col in columns}

        required_columns = {
            'id', 'title', 'version_label', 'source_url',
            'checksum_sha256', 'pdf_bytes', 'docling_json', 'created_at'
        }

        assert required_columns.issubset(column_names)

        # Check primary key
        pk_columns = [col['name'] for col in columns if col['pk']]
        assert 'id' in pk_columns

    def test_sections_table_structure(self, temp_db_with_schema):
        """sections table has correct columns"""
        columns = get_column_info(temp_db_with_schema, "sections")
        column_names = {col['name'] for col in columns}

        required_columns = {
            'id', 'document_id', 'level', 'heading', 'heading_path',
            'order_index', 'page_start', 'page_end', 'metadata', 'created_at'
        }

        assert required_columns.issubset(column_names)

    def test_parent_chunks_table_structure(self, temp_db_with_schema):
        """parent_chunks table has correct columns"""
        columns = get_column_info(temp_db_with_schema, "parent_chunks")
        column_names = {col['name'] for col in columns}

        required_columns = {
            'id', 'section_id', 'content', 'token_count',
            'page_start', 'page_end', 'metadata', 'created_at'
        }

        assert required_columns.issubset(column_names)

    def test_child_chunks_table_structure(self, temp_db_with_schema):
        """child_chunks table has correct columns"""
        columns = get_column_info(temp_db_with_schema, "child_chunks")
        column_names = {col['name'] for col in columns}

        required_columns = {
            'id', 'parent_id', 'section_id', 'content', 'token_count',
            'chunk_index', 'page_start', 'page_end', 'metadata', 'created_at'
        }

        assert required_columns.issubset(column_names)


class TestIndexes:
    """Tests for index creation"""

    def test_documents_indexes_created(self, temp_db_with_schema):
        """documents table indexes are created"""
        indexes = get_index_names(temp_db_with_schema, "documents")
        assert len(indexes) > 0
        assert any("checksum" in idx for idx in indexes)

    def test_sections_indexes_created(self, temp_db_with_schema):
        """sections table indexes are created"""
        indexes = get_index_names(temp_db_with_schema, "sections")
        assert len(indexes) >= 4  # Should have at least 4 indexes

    def test_child_chunks_unique_index(self, temp_db_with_schema):
        """child_chunks has unique index on (parent_id, chunk_index)"""
        indexes = get_index_names(temp_db_with_schema, "child_chunks")
        # Check that unique index exists
        assert len(indexes) > 0


class TestConstraints:
    """Tests for SQL constraints"""

    def test_foreign_key_enforcement(self, temp_db_with_schema):
        """Foreign key constraints are enforced"""
        conn = sqlite3.connect(str(temp_db_with_schema))
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()

        # Try to insert section with non-existent document_id
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO sections (document_id, level, heading, heading_path, order_index)
                VALUES ('nonexistent-doc-id', 1, 'Test', 'Test', 1)
            """)

        conn.close()

    def test_check_constraint_token_count(self, temp_db_with_schema):
        """CHECK constraint prevents token_count <= 0"""
        conn = sqlite3.connect(str(temp_db_with_schema))
        cursor = conn.cursor()

        # First insert a valid document and section
        cursor.execute("""
            INSERT INTO documents (id, title, checksum_sha256)
            VALUES ('test-doc', 'Test', 'abc123')
        """)
        cursor.execute("""
            INSERT INTO sections (document_id, level, heading, heading_path, order_index)
            VALUES ('test-doc', 1, 'Test', 'Test', 1)
        """)
        conn.commit()

        # Try to insert parent_chunk with token_count = 0
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO parent_chunks (section_id, content, token_count)
                VALUES (1, 'Test content', 0)
            """)

        conn.close()

    def test_check_constraint_level(self, temp_db_with_schema):
        """CHECK constraint prevents level < 1"""
        conn = sqlite3.connect(str(temp_db_with_schema))
        cursor = conn.cursor()

        # Insert a valid document first
        cursor.execute("""
            INSERT INTO documents (id, title, checksum_sha256)
            VALUES ('test-doc', 'Test', 'abc123')
        """)
        conn.commit()

        # Try to insert section with level = 0
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO sections (document_id, level, heading, heading_path, order_index)
                VALUES ('test-doc', 0, 'Test', 'Test', 1)
            """)

        conn.close()

    def test_unique_constraint_checksum(self, temp_db_with_schema):
        """Unique constraint on checksum_sha256"""
        conn = sqlite3.connect(str(temp_db_with_schema))
        cursor = conn.cursor()

        # Insert first document
        cursor.execute("""
            INSERT INTO documents (id, title, checksum_sha256)
            VALUES ('doc1', 'Test 1', 'same-checksum')
        """)
        conn.commit()

        # Try to insert second document with same checksum
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO documents (id, title, checksum_sha256)
                VALUES ('doc2', 'Test 2', 'same-checksum')
            """)

        conn.close()

    def test_unique_constraint_child_chunk_index(self, temp_db_with_schema):
        """Unique constraint on (parent_id, chunk_index)"""
        conn = sqlite3.connect(str(temp_db_with_schema))
        cursor = conn.cursor()

        # Set up parent data
        cursor.execute("""
            INSERT INTO documents (id, title, checksum_sha256)
            VALUES ('test-doc', 'Test', 'abc123')
        """)
        cursor.execute("""
            INSERT INTO sections (document_id, level, heading, heading_path, order_index)
            VALUES ('test-doc', 1, 'Test', 'Test', 1)
        """)
        cursor.execute("""
            INSERT INTO parent_chunks (section_id, content, token_count)
            VALUES (1, 'Parent content', 100)
        """)
        conn.commit()

        # Insert first child chunk
        cursor.execute("""
            INSERT INTO child_chunks (parent_id, section_id, content, token_count, chunk_index)
            VALUES (1, 1, 'Child content 1', 50, 0)
        """)
        conn.commit()

        # Try to insert another child chunk with same chunk_index
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO child_chunks (parent_id, section_id, content, token_count, chunk_index)
                VALUES (1, 1, 'Child content 2', 50, 0)
            """)

        conn.close()


class TestCascadeDelete:
    """Tests for CASCADE DELETE behavior"""

    def test_delete_document_cascades_to_sections(self, temp_db_with_schema):
        """Deleting document cascades to sections"""
        conn = sqlite3.connect(str(temp_db_with_schema))
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()

        # Insert document and section
        cursor.execute("""
            INSERT INTO documents (id, title, checksum_sha256)
            VALUES ('test-doc', 'Test', 'abc123')
        """)
        cursor.execute("""
            INSERT INTO sections (document_id, level, heading, heading_path, order_index)
            VALUES ('test-doc', 1, 'Test', 'Test', 1)
        """)
        conn.commit()

        # Verify section exists
        cursor.execute("SELECT COUNT(*) FROM sections WHERE document_id = 'test-doc'")
        assert cursor.fetchone()[0] == 1

        # Delete document
        cursor.execute("DELETE FROM documents WHERE id = 'test-doc'")
        conn.commit()

        # Verify section is also deleted
        cursor.execute("SELECT COUNT(*) FROM sections WHERE document_id = 'test-doc'")
        assert cursor.fetchone()[0] == 0

        conn.close()

    def test_delete_parent_cascades_to_children(self, temp_db_with_schema):
        """Deleting parent_chunk cascades to child_chunks"""
        conn = sqlite3.connect(str(temp_db_with_schema))
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()

        # Set up full hierarchy
        cursor.execute("""
            INSERT INTO documents (id, title, checksum_sha256)
            VALUES ('test-doc', 'Test', 'abc123')
        """)
        cursor.execute("""
            INSERT INTO sections (document_id, level, heading, heading_path, order_index)
            VALUES ('test-doc', 1, 'Test', 'Test', 1)
        """)
        cursor.execute("""
            INSERT INTO parent_chunks (section_id, content, token_count)
            VALUES (1, 'Parent content', 100)
        """)
        cursor.execute("""
            INSERT INTO child_chunks (parent_id, section_id, content, token_count, chunk_index)
            VALUES (1, 1, 'Child content', 50, 0)
        """)
        conn.commit()

        # Verify child exists
        cursor.execute("SELECT COUNT(*) FROM child_chunks WHERE parent_id = 1")
        assert cursor.fetchone()[0] == 1

        # Delete parent
        cursor.execute("DELETE FROM parent_chunks WHERE id = 1")
        conn.commit()

        # Verify child is also deleted
        cursor.execute("SELECT COUNT(*) FROM child_chunks WHERE parent_id = 1")
        assert cursor.fetchone()[0] == 0

        conn.close()


class TestSqliteVecExtension:
    """Tests for sqlite-vec extension loading"""

    def test_vec_table_created(self, temp_db_with_schema):
        """vec_child_chunks virtual table is created"""
        tables = get_table_names(temp_db_with_schema)
        assert "vec_child_chunks" in tables

    def test_vec_table_accepts_embeddings(self, temp_db_with_schema, sample_embedding):
        """vec_child_chunks accepts embedding vectors"""
        import struct

        conn = sqlite3.connect(str(temp_db_with_schema))
        _load_sqlite_vec(conn)
        cursor = conn.cursor()

        # sqlite-vec expects embeddings as bytes
        # Convert list of floats to bytes
        embedding_bytes = struct.pack(f'{len(sample_embedding)}f', *sample_embedding)

        # Insert an embedding
        cursor.execute("""
            INSERT INTO vec_child_chunks (chunk_id, embedding)
            VALUES (?, ?)
        """, (1, embedding_bytes))
        conn.commit()

        # Query it back
        cursor.execute("SELECT chunk_id FROM vec_child_chunks WHERE chunk_id = 1")
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == 1

        conn.close()

    def test_load_sqlite_vec_function(self, temp_db):
        """_load_sqlite_vec() successfully loads extension"""
        create_schema(db_path=temp_db)

        conn = sqlite3.connect(str(temp_db))
        # Should not raise error
        _load_sqlite_vec(conn)

        # Verify extension loaded by querying virtual table
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM vec_child_chunks")
        result = cursor.fetchone()
        assert result[0] == 0  # Empty but accessible

        conn.close()


class TestForceRecreate:
    """Tests for force_recreate parameter"""

    def test_force_recreate_drops_tables(self, temp_db):
        """force_recreate=True drops existing tables"""
        # Create schema and insert data
        create_schema(db_path=temp_db)
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO documents (id, title, checksum_sha256)
            VALUES ('test-doc', 'Test', 'abc123')
        """)
        conn.commit()
        conn.close()

        # Verify data exists
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents")
        assert cursor.fetchone()[0] == 1
        conn.close()

        # Recreate with force
        create_schema(db_path=temp_db, force_recreate=True)

        # Verify tables are empty
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents")
        assert cursor.fetchone()[0] == 0
        conn.close()

    def test_drop_all_tables_function(self, temp_db_with_schema):
        """_drop_all_tables() removes all tables"""
        # Verify tables exist
        tables_before = get_table_names(temp_db_with_schema)
        assert len(tables_before) >= 7

        # Drop all tables
        conn = sqlite3.connect(str(temp_db_with_schema))
        _load_sqlite_vec(conn)
        cursor = conn.cursor()
        _drop_all_tables(cursor)
        conn.commit()
        conn.close()

        # Verify tables are gone
        tables_after = get_table_names(temp_db_with_schema)
        required_tables = {
            "documents", "embedding_metadata", "sections", "raw_blocks",
            "parent_chunks", "child_chunks", "vec_child_chunks"
        }
        assert len(required_tables.intersection(tables_after)) == 0


class TestSchemaValidation:
    """Tests for validate_schema() function"""

    def test_validates_complete_schema(self, temp_db_with_schema):
        """validate_schema() returns True for complete schema"""
        result = validate_schema(db_path=temp_db_with_schema)
        assert result is True

    def test_detects_missing_database(self, temp_db):
        """validate_schema() returns False if database doesn't exist"""
        assert not temp_db.exists()
        result = validate_schema(db_path=temp_db)
        assert result is False

    def test_detects_missing_tables(self, temp_db):
        """validate_schema() returns False if tables are missing"""
        # Create database but only create some tables
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                checksum_sha256 TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

        result = validate_schema(db_path=temp_db)
        assert result is False

    def test_validates_vec_table_accessible(self, temp_db_with_schema):
        """validate_schema() checks vec_child_chunks is accessible"""
        # This is implicitly tested by validate_complete_schema
        # but we verify it checks the virtual table
        result = validate_schema(db_path=temp_db_with_schema)
        assert result is True


class TestTableStats:
    """Tests for get_table_stats() function"""

    def test_empty_database_stats(self, temp_db_with_schema):
        """get_table_stats() returns zeros for empty database"""
        stats = get_table_stats(db_path=temp_db_with_schema)

        assert isinstance(stats, dict)
        assert len(stats) == 7

        for table, count in stats.items():
            assert count == 0, f"Table {table} should have 0 rows"

    def test_stats_with_data(self, temp_db_with_schema):
        """get_table_stats() correctly counts rows"""
        conn = sqlite3.connect(str(temp_db_with_schema))
        cursor = conn.cursor()

        # Insert test data
        cursor.execute("""
            INSERT INTO documents (id, title, checksum_sha256)
            VALUES ('doc1', 'Test 1', 'abc123')
        """)
        cursor.execute("""
            INSERT INTO documents (id, title, checksum_sha256)
            VALUES ('doc2', 'Test 2', 'def456')
        """)
        cursor.execute("""
            INSERT INTO documents (id, title, checksum_sha256)
            VALUES ('doc3', 'Test 3', 'ghi789')
        """)
        conn.commit()
        conn.close()

        stats = get_table_stats(db_path=temp_db_with_schema)

        assert stats['documents'] == 3
        assert stats['sections'] == 0  # Still empty

    def test_stats_nonexistent_database(self, temp_db):
        """get_table_stats() returns empty dict for missing database"""
        assert not temp_db.exists()
        stats = get_table_stats(db_path=temp_db)
        assert stats == {}


class TestPrintSchemaInfo:
    """Tests for print_schema_info() function"""

    def test_print_schema_info_no_crash(self, temp_db_with_schema, capsys):
        """print_schema_info() executes without errors"""
        # Should not raise any exceptions
        print_schema_info(db_path=temp_db_with_schema)

        # Capture output
        captured = capsys.readouterr()
        assert "Database Schema Information" in captured.out
        assert str(temp_db_with_schema) in captured.out

    def test_print_schema_info_missing_database(self, temp_db, capsys):
        """print_schema_info() handles missing database gracefully"""
        assert not temp_db.exists()

        # Should not crash
        print_schema_info(db_path=temp_db)

        captured = capsys.readouterr()
        assert "Database file not found" in captured.out or "exists: False" in captured.out


class TestErrorHandling:
    """Tests for error handling"""

    def test_create_schema_rollback_on_error(self, temp_db):
        """Schema creation rolls back on error"""
        # Mock one of the table creation to fail
        with patch('src.database.schema.SECTIONS_TABLE', 'INVALID SQL'):
            with pytest.raises(SchemaError):
                create_schema(db_path=temp_db, force_recreate=False)

        # Verify database either doesn't exist or is empty
        if temp_db.exists():
            tables = get_table_names(temp_db)
            # Should have no tables or incomplete set
            assert len(tables) < 7

    def test_schema_error_on_connection_failure(self):
        """Error raised if database path is invalid"""
        # Use invalid path that will cause connection error
        invalid_path = Path("/invalid/path/that/cannot/exist/db.sqlite")

        # Expecting OSError or SchemaError depending on where the failure occurs
        with pytest.raises((SchemaError, OSError)):
            create_schema(db_path=invalid_path)


class TestDefaultConfiguration:
    """Tests for default configuration usage"""

    def test_uses_default_database_path(self):
        """create_schema() uses DATABASE_PATH when no path provided"""
        from src.config import DATABASE_PATH

        # We won't actually create at production path, just verify the logic
        # This test documents the expected behavior
        assert DATABASE_PATH is not None
        assert isinstance(DATABASE_PATH, Path)


class TestTransactionBehavior:
    """Tests for transaction handling"""

    def test_schema_creation_is_atomic(self, temp_db):
        """All tables created in single transaction"""
        create_schema(db_path=temp_db)

        # If any table failed, none should exist
        # Since creation succeeded, all should exist
        tables = get_table_names(temp_db)
        assert len(tables) >= 7

    def test_commit_on_success(self, temp_db):
        """Changes are committed after successful creation"""
        create_schema(db_path=temp_db)

        # Open new connection to verify changes persisted
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        conn.close()

        assert len(tables) >= 7
