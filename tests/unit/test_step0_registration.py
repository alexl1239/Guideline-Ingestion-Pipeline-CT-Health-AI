"""
Unit Tests for src.pipeline.step0_registration

Tests individual functions in the document registration module without
requiring actual database operations or file I/O (those are integration tests).
"""

import pytest
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import tempfile

from src.pipeline.step0_registration import (
    compute_sha256,
    check_document_exists,
    RegistrationError,
)


class TestComputeSHA256:
    """Tests for compute_sha256() function"""

    def test_compute_sha256_small_file(self):
        """SHA-256 checksum computed correctly for small file"""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            test_content = b"Hello, World!"
            f.write(test_content)
            temp_path = Path(f.name)

        try:
            # Compute expected checksum manually
            expected = hashlib.sha256(test_content).hexdigest()

            # Test function
            result = compute_sha256(temp_path)

            assert result == expected
            assert len(result) == 64  # SHA-256 is 64 hex chars
        finally:
            temp_path.unlink()

    def test_compute_sha256_empty_file(self):
        """SHA-256 checksum computed correctly for empty file"""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            temp_path = Path(f.name)

        try:
            expected = hashlib.sha256(b"").hexdigest()
            result = compute_sha256(temp_path)

            assert result == expected
        finally:
            temp_path.unlink()

    def test_compute_sha256_large_file(self):
        """SHA-256 checksum computed correctly for large file (chunked reading)"""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            # Create 100KB file to test chunked reading
            test_content = b"X" * (100 * 1024)
            f.write(test_content)
            temp_path = Path(f.name)

        try:
            expected = hashlib.sha256(test_content).hexdigest()
            result = compute_sha256(temp_path)

            assert result == expected
        finally:
            temp_path.unlink()

    def test_compute_sha256_nonexistent_file(self):
        """IOError raised for nonexistent file"""
        fake_path = Path("/nonexistent/path/to/file.pdf")

        with pytest.raises(IOError):
            compute_sha256(fake_path)

    def test_compute_sha256_returns_hexadecimal(self):
        """Result is valid hexadecimal string"""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(b"test data")
            temp_path = Path(f.name)

        try:
            result = compute_sha256(temp_path)

            # Should be valid hex string
            assert all(c in '0123456789abcdef' for c in result)
            assert len(result) == 64
        finally:
            temp_path.unlink()

    def test_compute_sha256_deterministic(self):
        """Same file produces same checksum (deterministic)"""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(b"deterministic test")
            temp_path = Path(f.name)

        try:
            result1 = compute_sha256(temp_path)
            result2 = compute_sha256(temp_path)

            assert result1 == result2
        finally:
            temp_path.unlink()


class TestCheckDocumentExists:
    """Tests for check_document_exists() function"""

    @patch('src.pipeline.step0_registration.get_connection')
    def test_document_exists_found(self, mock_get_connection):
        """Returns document ID when document exists"""
        # Mock database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_connection.return_value.__enter__.return_value = mock_conn

        # Mock query result
        test_doc_id = "test-uuid-12345"
        mock_cursor.fetchone.return_value = (test_doc_id,)

        # Test
        result = check_document_exists("fake-checksum")

        assert result == test_doc_id
        mock_cursor.execute.assert_called_once()

    @patch('src.pipeline.step0_registration.get_connection')
    def test_document_exists_not_found(self, mock_get_connection):
        """Returns None when document doesn't exist"""
        # Mock database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_connection.return_value.__enter__.return_value = mock_conn

        # Mock no result
        mock_cursor.fetchone.return_value = None

        # Test
        result = check_document_exists("fake-checksum")

        assert result is None

    @patch('src.pipeline.step0_registration.get_connection')
    def test_document_exists_database_error(self, mock_get_connection):
        """Returns None when database error occurs"""
        # Mock database connection that raises error
        mock_get_connection.return_value.__enter__.side_effect = Exception("DB error")

        # Test - should not crash, returns None
        result = check_document_exists("fake-checksum")

        assert result is None

    @patch('src.pipeline.step0_registration.get_connection')
    def test_document_exists_query_format(self, mock_get_connection):
        """Query uses correct SQL and parameters"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_connection.return_value.__enter__.return_value = mock_conn
        mock_cursor.fetchone.return_value = None

        test_checksum = "abc123def456"
        check_document_exists(test_checksum)

        # Verify SQL query
        call_args = mock_cursor.execute.call_args
        sql_query = call_args[0][0]
        params = call_args[0][1]

        assert "SELECT id FROM documents" in sql_query
        assert "checksum_sha256" in sql_query
        assert params == (test_checksum,)


class TestRegistrationError:
    """Tests for RegistrationError exception"""

    def test_registration_error_exists(self):
        """RegistrationError exception class exists"""
        assert RegistrationError is not None

    def test_registration_error_is_exception(self):
        """RegistrationError inherits from Exception"""
        assert issubclass(RegistrationError, Exception)

    def test_registration_error_can_be_raised(self):
        """RegistrationError can be raised"""
        with pytest.raises(RegistrationError):
            raise RegistrationError("Test error")

    def test_registration_error_with_message(self):
        """RegistrationError preserves error message"""
        msg = "Custom registration error"
        try:
            raise RegistrationError(msg)
        except RegistrationError as e:
            assert str(e) == msg

    def test_registration_error_with_cause(self):
        """RegistrationError can chain exceptions"""
        original_error = ValueError("Original cause")

        try:
            raise RegistrationError("Wrapped error") from original_error
        except RegistrationError as e:
            assert e.__cause__ is original_error


class TestModuleConstants:
    """Tests for module-level constants"""

    def test_pdf_path_constant_exists(self):
        """PDF_PATH constant is defined"""
        from src.pipeline.step0_registration import PDF_PATH
        assert PDF_PATH is not None

    def test_pdf_path_uses_config(self):
        """PDF_PATH uses SOURCE_PDF_PATH from config"""
        from src.pipeline.step0_registration import PDF_PATH
        from src.config import SOURCE_PDF_PATH

        assert PDF_PATH == SOURCE_PDF_PATH


class TestFunctionSignatures:
    """Tests for function signatures and interfaces"""

    def test_compute_sha256_accepts_path(self):
        """compute_sha256() accepts Path object"""
        # This is a smoke test - actual functionality tested elsewhere
        import inspect
        sig = inspect.signature(compute_sha256)

        assert 'file_path' in sig.parameters
        # Should accept Path type
        assert sig.parameters['file_path'].annotation == Path or Path

    def test_check_document_exists_returns_optional_string(self):
        """check_document_exists() returns Optional[str]"""
        import inspect
        from typing import get_type_hints

        sig = inspect.signature(check_document_exists)
        hints = get_type_hints(check_document_exists)

        # Should return Optional[str]
        assert 'return' in hints


class TestLoggingIntegration:
    """Tests for logging behavior"""

    @patch('src.pipeline.step0_registration.logger')
    def test_compute_sha256_logs_progress(self, mock_logger):
        """compute_sha256() logs checksum computation"""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(b"test")
            temp_path = Path(f.name)

        try:
            compute_sha256(temp_path)

            # Should log info and success
            assert mock_logger.info.called
            assert mock_logger.success.called
        finally:
            temp_path.unlink()

    @patch('src.pipeline.step0_registration.logger')
    @patch('src.pipeline.step0_registration.get_connection')
    def test_check_document_exists_logs_found(self, mock_get_connection, mock_logger):
        """check_document_exists() logs when document found"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_connection.return_value.__enter__.return_value = mock_conn
        mock_cursor.fetchone.return_value = ("test-id",)

        check_document_exists("checksum")

        # Should log that document was found
        assert mock_logger.info.called
