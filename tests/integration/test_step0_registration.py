"""
Integration Tests for src.pipeline.step0_registration

Tests the complete document registration flow with actual database operations.
Uses temporary databases and test PDF files.
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.pipeline import step0_registration
from src.pipeline.step0_registration import run, RegistrationError
from src.database.schema import create_schema


@pytest.fixture
def test_pdf():
    """Create a temporary test PDF file"""
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pdf') as f:
        # Write some test content
        test_content = b"%PDF-1.4\nTest PDF content for registration testing"
        f.write(test_content)
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def temp_db_for_registration(temp_db):
    """Create a temporary database with schema for registration tests"""
    create_schema(db_path=temp_db, force_recreate=True)
    return temp_db


class TestDocumentRegistration:
    """Tests for complete document registration flow"""

    @patch('src.pipeline.step0_registration.PDF_PATH')
    @patch('src.config.DATABASE_PATH')
    def test_register_document_success(self, mock_db_path, mock_pdf_path,
                                       test_pdf, temp_db_for_registration):
        """Complete registration flow succeeds"""
        # Mock paths
        mock_pdf_path.return_value = test_pdf
        step0_registration.PDF_PATH = test_pdf
        mock_db_path.return_value = temp_db_for_registration

        # Patch get_connection to use temp database
        with patch('src.pipeline.step0_registration.get_connection') as mock_conn:
            conn = sqlite3.connect(str(temp_db_for_registration))
            mock_conn.return_value.__enter__.return_value = conn

            # Run registration
            doc_id = run()

            # Verify document ID returned
            assert doc_id is not None
            assert len(doc_id) == 36  # UUID format

            # Verify document in database
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, checksum_sha256 FROM documents WHERE id = ?", (doc_id,))
            result = cursor.fetchone()

            assert result is not None
            assert result[0] == doc_id
            assert result[1] == "Uganda Clinical Guidelines"
            assert len(result[2]) == 64  # SHA-256 hex length

            conn.close()

    @patch('src.pipeline.step0_registration.PDF_PATH')
    @patch('src.config.DATABASE_PATH')
    def test_register_document_idempotent(self, mock_db_path, mock_pdf_path,
                                          test_pdf, temp_db_for_registration):
        """Re-registration returns existing document ID"""
        mock_pdf_path.return_value = test_pdf
        step0_registration.PDF_PATH = test_pdf
        mock_db_path.return_value = temp_db_for_registration

        with patch('src.pipeline.step0_registration.get_connection') as mock_conn:
            conn = sqlite3.connect(str(temp_db_for_registration))
            mock_conn.return_value.__enter__.return_value = conn

            # First registration
            doc_id_1 = run()

            # Second registration (idempotent)
            doc_id_2 = run()

            # Should return same ID
            assert doc_id_1 == doc_id_2

            # Only one document in database
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM documents")
            count = cursor.fetchone()[0]
            assert count == 1

            conn.close()

    @patch('src.pipeline.step0_registration.PDF_PATH')
    def test_register_document_missing_pdf(self, mock_pdf_path):
        """FileNotFoundError raised when PDF missing"""
        fake_path = Path("/nonexistent/test.pdf")
        mock_pdf_path.return_value = fake_path
        step0_registration.PDF_PATH = fake_path

        with pytest.raises(FileNotFoundError) as exc_info:
            run()

        assert "PDF not found" in str(exc_info.value)

    @patch('src.pipeline.step0_registration.PDF_PATH')
    @patch('src.config.DATABASE_PATH')
    def test_pdf_bytes_stored(self, mock_db_path, mock_pdf_path,
                              test_pdf, temp_db_for_registration):
        """PDF bytes are stored in database"""
        mock_pdf_path.return_value = test_pdf
        step0_registration.PDF_PATH = test_pdf
        mock_db_path.return_value = temp_db_for_registration

        with patch('src.pipeline.step0_registration.get_connection') as mock_conn:
            conn = sqlite3.connect(str(temp_db_for_registration))
            mock_conn.return_value.__enter__.return_value = conn

            doc_id = run()

            # Verify PDF bytes stored
            cursor = conn.cursor()
            cursor.execute("SELECT LENGTH(pdf_bytes) FROM documents WHERE id = ?", (doc_id,))
            pdf_size = cursor.fetchone()[0]

            # Should match original file size
            original_size = test_pdf.stat().st_size
            assert pdf_size == original_size
            assert pdf_size > 0

            conn.close()

    @patch('src.pipeline.step0_registration.PDF_PATH')
    @patch('src.config.DATABASE_PATH')
    def test_embedding_metadata_inserted(self, mock_db_path, mock_pdf_path,
                                        test_pdf, temp_db_for_registration):
        """Embedding metadata is inserted during registration"""
        mock_pdf_path.return_value = test_pdf
        step0_registration.PDF_PATH = test_pdf
        mock_db_path.return_value = temp_db_for_registration

        with patch('src.pipeline.step0_registration.get_connection') as mock_conn:
            conn = sqlite3.connect(str(temp_db_for_registration))
            mock_conn.return_value.__enter__.return_value = conn

            run()

            # Verify embedding metadata
            cursor = conn.cursor()
            cursor.execute("SELECT model_name, dimension, docling_version FROM embedding_metadata")
            result = cursor.fetchone()

            assert result is not None
            assert result[0] == "text-embedding-3-small"
            assert result[1] == 1536
            assert result[2] == "2.0.0"

            conn.close()

    @patch('src.pipeline.step0_registration.PDF_PATH')
    @patch('src.config.DATABASE_PATH')
    def test_embedding_metadata_not_duplicated(self, mock_db_path, mock_pdf_path,
                                               test_pdf, temp_db_for_registration):
        """Embedding metadata not inserted twice on re-registration"""
        mock_pdf_path.return_value = test_pdf
        step0_registration.PDF_PATH = test_pdf
        mock_db_path.return_value = temp_db_for_registration

        with patch('src.pipeline.step0_registration.get_connection') as mock_conn:
            # First registration
            conn1 = sqlite3.connect(str(temp_db_for_registration))
            mock_conn.return_value.__enter__.return_value = conn1
            run()
            conn1.close()

            # Create a second test PDF with different content
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pdf') as f:
                f.write(b"%PDF-1.4\nDifferent content")
                test_pdf2 = Path(f.name)

            try:
                step0_registration.PDF_PATH = test_pdf2

                # Second registration with different PDF (new connection)
                conn2 = sqlite3.connect(str(temp_db_for_registration))
                mock_conn.return_value.__enter__.return_value = conn2
                run()

                # Should still only have one embedding_metadata row
                cursor = conn2.cursor()
                cursor.execute("SELECT COUNT(*) FROM embedding_metadata")
                count = cursor.fetchone()[0]
                assert count == 1
                conn2.close()

            finally:
                test_pdf2.unlink()

    @patch('src.pipeline.step0_registration.PDF_PATH')
    @patch('src.config.DATABASE_PATH')
    def test_checksum_uniqueness(self, mock_db_path, mock_pdf_path,
                                 test_pdf, temp_db_for_registration):
        """Unique checksum constraint prevents duplicate checksums"""
        mock_pdf_path.return_value = test_pdf
        step0_registration.PDF_PATH = test_pdf
        mock_db_path.return_value = temp_db_for_registration

        with patch('src.pipeline.step0_registration.get_connection') as mock_conn:
            conn = sqlite3.connect(str(temp_db_for_registration))
            mock_conn.return_value.__enter__.return_value = conn

            # First registration
            doc_id = run()

            # Try to manually insert same checksum with different ID
            cursor = conn.cursor()
            cursor.execute("SELECT checksum_sha256 FROM documents WHERE id = ?", (doc_id,))
            checksum = cursor.fetchone()[0]

            # Should raise IntegrityError
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute("""
                    INSERT INTO documents (id, title, checksum_sha256)
                    VALUES ('different-uuid', 'Test', ?)
                """, (checksum,))

            conn.close()


class TestRegistrationMetadata:
    """Tests for metadata fields in registration"""

    @patch('src.pipeline.step0_registration.PDF_PATH')
    @patch('src.config.DATABASE_PATH')
    def test_document_title_stored(self, mock_db_path, mock_pdf_path,
                                   test_pdf, temp_db_for_registration):
        """Document title is stored correctly"""
        mock_pdf_path.return_value = test_pdf
        step0_registration.PDF_PATH = test_pdf
        mock_db_path.return_value = temp_db_for_registration

        with patch('src.pipeline.step0_registration.get_connection') as mock_conn:
            conn = sqlite3.connect(str(temp_db_for_registration))
            mock_conn.return_value.__enter__.return_value = conn

            doc_id = run()

            cursor = conn.cursor()
            cursor.execute("SELECT title FROM documents WHERE id = ?", (doc_id,))
            title = cursor.fetchone()[0]

            assert title == "Uganda Clinical Guidelines"
            conn.close()

    @patch('src.pipeline.step0_registration.PDF_PATH')
    @patch('src.config.DATABASE_PATH')
    def test_version_label_stored(self, mock_db_path, mock_pdf_path,
                                  test_pdf, temp_db_for_registration):
        """Version label is stored correctly"""
        mock_pdf_path.return_value = test_pdf
        step0_registration.PDF_PATH = test_pdf
        mock_db_path.return_value = temp_db_for_registration

        with patch('src.pipeline.step0_registration.get_connection') as mock_conn:
            conn = sqlite3.connect(str(temp_db_for_registration))
            mock_conn.return_value.__enter__.return_value = conn

            doc_id = run()

            cursor = conn.cursor()
            cursor.execute("SELECT version_label FROM documents WHERE id = ?", (doc_id,))
            version = cursor.fetchone()[0]

            assert version == "UCG 2023"
            conn.close()

    @patch('src.pipeline.step0_registration.PDF_PATH')
    @patch('src.config.DATABASE_PATH')
    def test_source_url_stored(self, mock_db_path, mock_pdf_path,
                               test_pdf, temp_db_for_registration):
        """Source URL is stored correctly"""
        mock_pdf_path.return_value = test_pdf
        step0_registration.PDF_PATH = test_pdf
        mock_db_path.return_value = temp_db_for_registration

        with patch('src.pipeline.step0_registration.get_connection') as mock_conn:
            conn = sqlite3.connect(str(temp_db_for_registration))
            mock_conn.return_value.__enter__.return_value = conn

            doc_id = run()

            cursor = conn.cursor()
            cursor.execute("SELECT source_url FROM documents WHERE id = ?", (doc_id,))
            url = cursor.fetchone()[0]

            assert url == "https://health.go.ug/guidelines/"
            conn.close()

    @patch('src.pipeline.step0_registration.PDF_PATH')
    @patch('src.config.DATABASE_PATH')
    def test_created_at_timestamp(self, mock_db_path, mock_pdf_path,
                                  test_pdf, temp_db_for_registration):
        """Created timestamp is stored"""
        mock_pdf_path.return_value = test_pdf
        step0_registration.PDF_PATH = test_pdf
        mock_db_path.return_value = temp_db_for_registration

        with patch('src.pipeline.step0_registration.get_connection') as mock_conn:
            conn = sqlite3.connect(str(temp_db_for_registration))
            mock_conn.return_value.__enter__.return_value = conn

            doc_id = run()

            cursor = conn.cursor()
            cursor.execute("SELECT created_at FROM documents WHERE id = ?", (doc_id,))
            timestamp = cursor.fetchone()[0]

            assert timestamp is not None
            assert "T" in timestamp  # ISO format
            conn.close()


class TestRegistrationErrorHandling:
    """Tests for error handling in registration"""

    @patch('src.pipeline.step0_registration.PDF_PATH')
    def test_registration_error_on_read_failure(self, mock_pdf_path):
        """Error raised when PDF cannot be read (directory instead of file)"""
        # Create a directory instead of file (will cause IsADirectoryError)
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)

            mock_pdf_path.return_value = temp_path
            step0_registration.PDF_PATH = temp_path

            # Should raise IOError (IsADirectoryError is subclass of IOError)
            with pytest.raises((RegistrationError, IOError)):
                run()

    @patch('src.pipeline.step0_registration.PDF_PATH')
    @patch('src.config.DATABASE_PATH')
    def test_transaction_error_handling(self, mock_db_path, mock_pdf_path,
                                       test_pdf, temp_db_for_registration):
        """RegistrationError raised on database failures"""
        mock_pdf_path.return_value = test_pdf
        step0_registration.PDF_PATH = test_pdf
        mock_db_path.return_value = temp_db_for_registration

        # Mock get_connection to raise error
        with patch('src.pipeline.step0_registration.get_connection') as mock_conn:
            mock_conn.return_value.__enter__.side_effect = sqlite3.Error("DB connection failed")

            # Should raise RegistrationError
            with pytest.raises(RegistrationError) as exc_info:
                run()

            assert "Database insertion failed" in str(exc_info.value)


class TestChecksumComputation:
    """Tests for checksum computation in registration context"""

    @patch('src.pipeline.step0_registration.PDF_PATH')
    @patch('src.config.DATABASE_PATH')
    def test_checksum_sha256_length(self, mock_db_path, mock_pdf_path,
                                    test_pdf, temp_db_for_registration):
        """Checksum is exactly 64 hex characters (SHA-256)"""
        mock_pdf_path.return_value = test_pdf
        step0_registration.PDF_PATH = test_pdf
        mock_db_path.return_value = temp_db_for_registration

        with patch('src.pipeline.step0_registration.get_connection') as mock_conn:
            conn = sqlite3.connect(str(temp_db_for_registration))
            mock_conn.return_value.__enter__.return_value = conn

            doc_id = run()

            cursor = conn.cursor()
            cursor.execute("SELECT checksum_sha256 FROM documents WHERE id = ?", (doc_id,))
            checksum = cursor.fetchone()[0]

            assert len(checksum) == 64
            assert all(c in '0123456789abcdef' for c in checksum)

            conn.close()

    @patch('src.pipeline.step0_registration.PDF_PATH')
    @patch('src.config.DATABASE_PATH')
    def test_checksum_deterministic(self, mock_db_path, mock_pdf_path,
                                   test_pdf, temp_db_for_registration):
        """Same PDF produces same checksum"""
        mock_pdf_path.return_value = test_pdf
        step0_registration.PDF_PATH = test_pdf
        mock_db_path.return_value = temp_db_for_registration

        with patch('src.pipeline.step0_registration.get_connection') as mock_conn:
            conn = sqlite3.connect(str(temp_db_for_registration))
            mock_conn.return_value.__enter__.return_value = conn

            # First registration
            doc_id_1 = run()
            cursor = conn.cursor()
            cursor.execute("SELECT checksum_sha256 FROM documents WHERE id = ?", (doc_id_1,))
            checksum_1 = cursor.fetchone()[0]

            # Clear database
            cursor.execute("DELETE FROM documents")
            conn.commit()

            # Second registration (same file)
            doc_id_2 = run()
            cursor.execute("SELECT checksum_sha256 FROM documents WHERE id = ?", (doc_id_2,))
            checksum_2 = cursor.fetchone()[0]

            # Checksums should match
            assert checksum_1 == checksum_2

            conn.close()
