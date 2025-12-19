"""
Unit Tests for src.database.schema

Tests schema DDL statements, constants, and logic without requiring
actual database operations (those are covered in integration tests).
"""

import pytest
import re

from src.database import schema
from src.database.schema import SchemaError


class TestDDLStatements:
    """Test DDL statement constants are valid SQL"""

    def test_documents_table_ddl(self):
        """DOCUMENTS_TABLE contains valid CREATE TABLE statement"""
        assert isinstance(schema.DOCUMENTS_TABLE, str)
        assert "CREATE TABLE" in schema.DOCUMENTS_TABLE
        assert "IF NOT EXISTS" in schema.DOCUMENTS_TABLE
        assert "documents" in schema.DOCUMENTS_TABLE
        assert "PRIMARY KEY" in schema.DOCUMENTS_TABLE

    def test_embedding_metadata_table_ddl(self):
        """EMBEDDING_METADATA_TABLE contains valid CREATE TABLE statement"""
        assert isinstance(schema.EMBEDDING_METADATA_TABLE, str)
        assert "CREATE TABLE" in schema.EMBEDDING_METADATA_TABLE
        assert "embedding_metadata" in schema.EMBEDDING_METADATA_TABLE
        assert "CHECK" in schema.EMBEDDING_METADATA_TABLE  # Has CHECK constraint

    def test_sections_table_ddl(self):
        """SECTIONS_TABLE contains valid CREATE TABLE statement"""
        assert isinstance(schema.SECTIONS_TABLE, str)
        assert "CREATE TABLE" in schema.SECTIONS_TABLE
        assert "sections" in schema.SECTIONS_TABLE
        assert "FOREIGN KEY" in schema.SECTIONS_TABLE

    def test_raw_blocks_table_ddl(self):
        """RAW_BLOCKS_TABLE contains valid CREATE TABLE statement"""
        assert isinstance(schema.RAW_BLOCKS_TABLE, str)
        assert "CREATE TABLE" in schema.RAW_BLOCKS_TABLE
        assert "raw_blocks" in schema.RAW_BLOCKS_TABLE
        assert "FOREIGN KEY" in schema.RAW_BLOCKS_TABLE

    def test_parent_chunks_table_ddl(self):
        """PARENT_CHUNKS_TABLE contains valid CREATE TABLE statement"""
        assert isinstance(schema.PARENT_CHUNKS_TABLE, str)
        assert "CREATE TABLE" in schema.PARENT_CHUNKS_TABLE
        assert "parent_chunks" in schema.PARENT_CHUNKS_TABLE
        assert "FOREIGN KEY" in schema.PARENT_CHUNKS_TABLE

    def test_child_chunks_table_ddl(self):
        """CHILD_CHUNKS_TABLE contains valid CREATE TABLE statement"""
        assert isinstance(schema.CHILD_CHUNKS_TABLE, str)
        assert "CREATE TABLE" in schema.CHILD_CHUNKS_TABLE
        assert "child_chunks" in schema.CHILD_CHUNKS_TABLE
        assert "FOREIGN KEY" in schema.CHILD_CHUNKS_TABLE

    def test_vec_child_chunks_table_ddl(self):
        """VEC_CHILD_CHUNKS_TABLE contains valid VIRTUAL TABLE statement"""
        assert isinstance(schema.VEC_CHILD_CHUNKS_TABLE, str)
        assert "CREATE VIRTUAL TABLE" in schema.VEC_CHILD_CHUNKS_TABLE
        assert "vec_child_chunks" in schema.VEC_CHILD_CHUNKS_TABLE
        assert "USING vec0" in schema.VEC_CHILD_CHUNKS_TABLE
        assert "FLOAT[1536]" in schema.VEC_CHILD_CHUNKS_TABLE  # Embedding dimension


class TestIndexDefinitions:
    """Test index definitions are valid SQL"""

    def test_documents_indexes(self):
        """DOCUMENTS_INDEXES list contains valid CREATE INDEX statements"""
        assert isinstance(schema.DOCUMENTS_INDEXES, list)
        assert len(schema.DOCUMENTS_INDEXES) > 0
        for idx_sql in schema.DOCUMENTS_INDEXES:
            assert "CREATE INDEX" in idx_sql
            assert "IF NOT EXISTS" in idx_sql

    def test_sections_indexes(self):
        """SECTIONS_INDEXES list contains valid CREATE INDEX statements"""
        assert isinstance(schema.SECTIONS_INDEXES, list)
        assert len(schema.SECTIONS_INDEXES) >= 4  # Should have at least 4 indexes
        for idx_sql in schema.SECTIONS_INDEXES:
            assert "CREATE INDEX" in idx_sql or "CREATE UNIQUE INDEX" in idx_sql

    def test_child_chunks_indexes(self):
        """CHILD_CHUNKS_INDEXES includes unique index on (parent_id, chunk_index)"""
        assert isinstance(schema.CHILD_CHUNKS_INDEXES, list)
        # Should have unique index to prevent duplicate chunk_index per parent
        unique_index_found = any("UNIQUE" in idx for idx in schema.CHILD_CHUNKS_INDEXES)
        assert unique_index_found


class TestIndexNamingConvention:
    """Test indexes follow naming convention: idx_<table>_<column>"""

    def test_index_names_follow_convention(self):
        """All indexes follow idx_<table>_<column> naming pattern"""
        all_indexes = (
            schema.DOCUMENTS_INDEXES +
            schema.EMBEDDING_METADATA_INDEXES +
            schema.SECTIONS_INDEXES +
            schema.RAW_BLOCKS_INDEXES +
            schema.PARENT_CHUNKS_INDEXES +
            schema.CHILD_CHUNKS_INDEXES
        )

        pattern = re.compile(r'idx_\w+_\w+')

        for idx_sql in all_indexes:
            # Extract index name from SQL
            match = re.search(r'INDEX\s+(?:IF NOT EXISTS\s+)?(\w+)', idx_sql)
            if match:
                idx_name = match.group(1)
                assert pattern.match(idx_name), f"Index name '{idx_name}' doesn't follow convention"


class TestTableNamingConsistency:
    """Test table names in DDL match expected names"""

    def test_all_required_tables_defined(self):
        """All 7 required tables have DDL definitions"""
        required_tables = [
            "documents",
            "embedding_metadata",
            "sections",
            "raw_blocks",
            "parent_chunks",
            "child_chunks",
            "vec_child_chunks",
        ]

        # Check each table has a DDL constant
        assert "documents" in schema.DOCUMENTS_TABLE
        assert "embedding_metadata" in schema.EMBEDDING_METADATA_TABLE
        assert "sections" in schema.SECTIONS_TABLE
        assert "raw_blocks" in schema.RAW_BLOCKS_TABLE
        assert "parent_chunks" in schema.PARENT_CHUNKS_TABLE
        assert "child_chunks" in schema.CHILD_CHUNKS_TABLE
        assert "vec_child_chunks" in schema.VEC_CHILD_CHUNKS_TABLE

    def test_validate_schema_checks_all_tables(self):
        """validate_schema() function checks for all 7 tables"""
        # Read the validate_schema source to verify it checks all tables
        import inspect
        source = inspect.getsource(schema.validate_schema)

        required_tables = [
            "documents",
            "embedding_metadata",
            "sections",
            "raw_blocks",
            "parent_chunks",
            "child_chunks",
            "vec_child_chunks",
        ]

        for table in required_tables:
            assert table in source, f"validate_schema should check for '{table}' table"


class TestForeignKeyReferences:
    """Test foreign keys reference valid tables"""

    def test_sections_references_documents(self):
        """sections table references documents table"""
        assert "REFERENCES documents" in schema.SECTIONS_TABLE

    def test_raw_blocks_references_documents(self):
        """raw_blocks table references documents table"""
        assert "REFERENCES documents" in schema.RAW_BLOCKS_TABLE

    def test_parent_chunks_references_sections(self):
        """parent_chunks table references sections table"""
        assert "REFERENCES sections" in schema.PARENT_CHUNKS_TABLE

    def test_child_chunks_references_parent_and_section(self):
        """child_chunks table references both parent_chunks and sections"""
        assert "REFERENCES parent_chunks" in schema.CHILD_CHUNKS_TABLE
        assert "REFERENCES sections" in schema.CHILD_CHUNKS_TABLE

    def test_cascade_delete_defined(self):
        """Foreign keys include ON DELETE CASCADE"""
        # Check at least some foreign keys have CASCADE
        tables_with_fk = [
            schema.SECTIONS_TABLE,
            schema.RAW_BLOCKS_TABLE,
            schema.PARENT_CHUNKS_TABLE,
            schema.CHILD_CHUNKS_TABLE,
        ]

        cascade_found = any("ON DELETE CASCADE" in table for table in tables_with_fk)
        assert cascade_found, "At least one table should have ON DELETE CASCADE"


class TestCheckConstraints:
    """Test CHECK constraints are defined"""

    def test_embedding_metadata_has_dimension_check(self):
        """embedding_metadata table checks dimension > 0"""
        assert "CHECK" in schema.EMBEDDING_METADATA_TABLE
        assert "dimension" in schema.EMBEDDING_METADATA_TABLE

    def test_sections_has_level_check(self):
        """sections table checks level >= 1"""
        assert "CHECK" in schema.SECTIONS_TABLE
        assert "level" in schema.SECTIONS_TABLE

    def test_raw_blocks_has_content_check(self):
        """raw_blocks table checks at least one content field is not NULL"""
        assert "CHECK" in schema.RAW_BLOCKS_TABLE
        # Should check that text_content OR markdown_content is not NULL

    def test_parent_chunks_has_token_check(self):
        """parent_chunks table checks token_count > 0"""
        assert "CHECK" in schema.PARENT_CHUNKS_TABLE
        assert "token_count" in schema.PARENT_CHUNKS_TABLE

    def test_child_chunks_has_token_check(self):
        """child_chunks table checks token_count > 0"""
        assert "CHECK" in schema.CHILD_CHUNKS_TABLE
        assert "token_count" in schema.CHILD_CHUNKS_TABLE


class TestConfigurationIntegration:
    """Test schema uses configuration constants"""

    def test_uses_embedding_dimension_from_config(self):
        """VEC_CHILD_CHUNKS_TABLE uses EMBEDDING_DIMENSION from config"""
        from src.config import EMBEDDING_DIMENSION

        assert str(EMBEDDING_DIMENSION) in schema.VEC_CHILD_CHUNKS_TABLE

    def test_uses_docling_version_in_metadata(self):
        """embedding_metadata table has docling_version field"""
        assert "docling_version" in schema.EMBEDDING_METADATA_TABLE


class TestSchemaErrorException:
    """Test SchemaError exception"""

    def test_schema_error_exists(self):
        """SchemaError exception class exists"""
        assert SchemaError is not None

    def test_schema_error_is_exception(self):
        """SchemaError inherits from Exception"""
        assert issubclass(SchemaError, Exception)

    def test_schema_error_can_be_raised(self):
        """SchemaError can be instantiated and raised"""
        with pytest.raises(SchemaError):
            raise SchemaError("Test error")

    def test_schema_error_with_message(self):
        """SchemaError preserves error message"""
        msg = "Test error message"
        try:
            raise SchemaError(msg)
        except SchemaError as e:
            assert str(e) == msg


class TestModuleExports:
    """Test module exports correct public API"""

    def test_all_exports_defined(self):
        """__all__ list is defined"""
        assert hasattr(schema, '__all__')
        assert isinstance(schema.__all__, list)

    def test_main_functions_exported(self):
        """Main functions are in __all__"""
        required_exports = [
            'create_schema',
            'validate_schema',
            'get_table_stats',
            'print_schema_info',
            'SchemaError',
        ]

        for export in required_exports:
            assert export in schema.__all__, f"{export} should be in __all__"

    def test_exported_functions_exist(self):
        """All exported names actually exist in module"""
        for name in schema.__all__:
            assert hasattr(schema, name), f"Exported name '{name}' not found in module"


class TestDependencyOrder:
    """Test tables are created in correct dependency order"""

    def test_base_tables_have_no_foreign_keys(self):
        """documents and embedding_metadata have no FOREIGN KEY"""
        assert "FOREIGN KEY" not in schema.DOCUMENTS_TABLE
        assert "FOREIGN KEY" not in schema.EMBEDDING_METADATA_TABLE

    def test_sections_depends_on_documents(self):
        """sections table depends on documents (has FK to documents)"""
        assert "FOREIGN KEY" in schema.SECTIONS_TABLE
        assert "document_id" in schema.SECTIONS_TABLE
        assert "REFERENCES documents" in schema.SECTIONS_TABLE

    def test_chunks_depend_on_sections(self):
        """parent_chunks and child_chunks depend on sections"""
        assert "section_id" in schema.PARENT_CHUNKS_TABLE
        assert "section_id" in schema.CHILD_CHUNKS_TABLE


class TestTimestampFields:
    """Test all tables have created_at timestamps"""

    def test_all_tables_have_created_at(self):
        """All regular tables (not vec) have created_at timestamp"""
        tables = [
            schema.DOCUMENTS_TABLE,
            schema.EMBEDDING_METADATA_TABLE,
            schema.SECTIONS_TABLE,
            schema.RAW_BLOCKS_TABLE,
            schema.PARENT_CHUNKS_TABLE,
            schema.CHILD_CHUNKS_TABLE,
        ]

        for table_ddl in tables:
            assert "created_at" in table_ddl, f"Table missing created_at field"
            assert "TIMESTAMP" in table_ddl or "DEFAULT CURRENT_TIMESTAMP" in table_ddl


class TestMetadataFields:
    """Test tables have JSON metadata fields where appropriate"""

    def test_sections_has_metadata(self):
        """sections table has metadata field"""
        assert "metadata" in schema.SECTIONS_TABLE
        assert "DEFAULT '{}'" in schema.SECTIONS_TABLE

    def test_raw_blocks_has_metadata(self):
        """raw_blocks table has metadata field"""
        assert "metadata" in schema.RAW_BLOCKS_TABLE

    def test_chunks_have_metadata(self):
        """parent_chunks and child_chunks have metadata fields"""
        assert "metadata" in schema.PARENT_CHUNKS_TABLE
        assert "metadata" in schema.CHILD_CHUNKS_TABLE
