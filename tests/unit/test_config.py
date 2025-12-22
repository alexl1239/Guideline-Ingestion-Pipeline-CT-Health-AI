"""
Unit Tests for src.config

Tests configuration loading, validation, and path resolution.
"""

import pytest
from pathlib import Path


class TestConfigLoading:
    """Tests for configuration loading"""

    def test_config_imports_successfully(self):
        """Config module imports without errors"""
        import src.config
        assert src.config is not None

    def test_database_path_defined(self):
        """DATABASE_PATH is defined"""
        from src.config import DATABASE_PATH
        assert DATABASE_PATH is not None
        assert isinstance(DATABASE_PATH, Path)

    def test_source_pdf_path_defined(self):
        """SOURCE_PDF_PATH is defined"""
        from src.config import SOURCE_PDF_PATH
        assert SOURCE_PDF_PATH is not None
        assert isinstance(SOURCE_PDF_PATH, Path)

    def test_embedding_model_defined(self):
        """EMBEDDING_MODEL_NAME is defined"""
        from src.config import EMBEDDING_MODEL_NAME
        assert EMBEDDING_MODEL_NAME is not None
        assert isinstance(EMBEDDING_MODEL_NAME, str)
        assert EMBEDDING_MODEL_NAME == "text-embedding-3-small"

    def test_embedding_dimension_defined(self):
        """EMBEDDING_DIMENSION is defined"""
        from src.config import EMBEDDING_DIMENSION
        assert EMBEDDING_DIMENSION is not None
        assert EMBEDDING_DIMENSION == 1536

    def test_docling_version_defined(self):
        """DOCLING_VERSION is defined"""
        from src.config import DOCLING_VERSION
        assert DOCLING_VERSION is not None
        assert isinstance(DOCLING_VERSION, str)

    def test_chunk_token_targets_defined(self):
        """Chunk token targets are defined"""
        from src.config import CHILD_TOKEN_TARGET, PARENT_TOKEN_TARGET
        assert CHILD_TOKEN_TARGET is not None
        assert PARENT_TOKEN_TARGET is not None
        assert isinstance(CHILD_TOKEN_TARGET, int)
        assert isinstance(PARENT_TOKEN_TARGET, int)
        assert CHILD_TOKEN_TARGET == 256
        assert PARENT_TOKEN_TARGET == 1500

    def test_batch_sizes_defined(self):
        """Batch sizes are defined"""
        from src.config import PARSING_BATCH_SIZE
        assert PARSING_BATCH_SIZE is not None
        assert isinstance(PARSING_BATCH_SIZE, int)
        assert PARSING_BATCH_SIZE > 0


class TestConfigPaths:
    """Tests for path configuration"""

    def test_data_directory_structure(self):
        """Data directory paths are correctly structured"""
        from src.config import DATABASE_PATH

        # Database should be in data/ directory
        assert "data" in str(DATABASE_PATH)
        assert DATABASE_PATH.suffix == ".db"

    def test_source_pdf_in_raw_directory(self):
        """Source PDF is in data/ucg23_raw/ directory"""
        from src.config import SOURCE_PDF_PATH

        assert "ucg23_raw" in str(SOURCE_PDF_PATH)
        assert SOURCE_PDF_PATH.suffix == ".pdf"
