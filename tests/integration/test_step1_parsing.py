"""
Integration Tests for Step 1: Parsing

Tests Step 1 with REAL Docling parsing (no mocking).
Uses 4-page test PDF to validate actual parsing behavior.
"""

import pytest
import sqlite3
from pathlib import Path
from unittest.mock import patch

from src.pipeline.step1_parsing import run, ParsingError


@pytest.mark.integration
class TestStep1Parsing:
    """Integration tests for Step 1 parsing"""

    def test_step1_parses_4_page_pdf(
        self,
        temp_db_with_registered_doc_4_pages,
        test_pdf_4_pages
    ):
        """
        Step 1 successfully parses 4-page PDF with real Docling.

        This test runs ACTUAL Docling parsing (no mocking).
        """
        db_path, doc_id = temp_db_with_registered_doc_4_pages

        # Patch paths to use test data
        import src.pipeline.step1_parsing as step1_module
        original_pdf_path = step1_module.SOURCE_PDF_PATH
        step1_module.SOURCE_PDF_PATH = test_pdf_4_pages

        try:
            # Patch DATABASE_PATH in connections module where it's used
            with patch('src.pipeline.step1_parsing.get_registered_document', return_value=doc_id), \
                 patch('src.database.connections.DATABASE_PATH', db_path):

                # Run REAL parsing
                run()

            # Verify outputs in database
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Check raw_blocks populated
            cursor.execute("SELECT COUNT(*) FROM raw_blocks")
            block_count = cursor.fetchone()[0]
            assert block_count > 50, f"Expected 50+ blocks for 4 pages, got {block_count}"

            # Check page coverage
            cursor.execute("SELECT MIN(page_number), MAX(page_number) FROM raw_blocks")
            min_page, max_page = cursor.fetchone()
            assert min_page >= 1, "Should start from page 1"
            assert max_page == 4, f"Should have 4 pages, got {max_page}"

            # Check block types exist
            cursor.execute("SELECT DISTINCT block_type FROM raw_blocks")
            block_types = {row[0] for row in cursor.fetchall()}
            assert len(block_types) >= 3, "Should have multiple block types"
            assert 'text' in block_types or 'paragraph' in block_types, "Should have text blocks"

            # Check Docling JSON stored
            cursor.execute("SELECT LENGTH(docling_json) FROM documents WHERE id = ?", (doc_id,))
            json_size = cursor.fetchone()[0]
            assert json_size is not None, "Docling JSON should be stored"
            assert json_size > 1000, f"Docling JSON should be substantial, got {json_size} bytes"

            conn.close()

            print(f"\n✓ Step 1 complete: {block_count} blocks extracted from 4 pages")

        finally:
            step1_module.SOURCE_PDF_PATH = original_pdf_path

    def test_step1_is_idempotent(
        self,
        temp_db_with_registered_doc_4_pages,
        test_pdf_4_pages
    ):
        """
        Running Step 1 twice doesn't duplicate blocks.
        """
        db_path, doc_id = temp_db_with_registered_doc_4_pages

        import src.pipeline.step1_parsing as step1_module
        original_pdf_path = step1_module.SOURCE_PDF_PATH
        step1_module.SOURCE_PDF_PATH = test_pdf_4_pages

        try:
            # Patch DATABASE_PATH in connections module where it's used
            with patch('src.pipeline.step1_parsing.get_registered_document', return_value=doc_id), \
                 patch('src.database.connections.DATABASE_PATH', db_path):

                # First run
                run()

                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM raw_blocks")
                count_first = cursor.fetchone()[0]
                conn.close()

                # Second run (should be skipped)
                run()

                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM raw_blocks")
                count_second = cursor.fetchone()[0]
                conn.close()

                assert count_first == count_second, "Should not duplicate blocks on re-run"
                print(f"\n✓ Idempotency verified: {count_first} blocks (unchanged)")

        finally:
            step1_module.SOURCE_PDF_PATH = original_pdf_path

    def test_step1_fails_without_registered_document(self, temp_db):
        """
        Step 1 fails gracefully when no document registered.
        """
        from src.database.schema import create_schema
        create_schema(db_path=temp_db)

        with patch('src.pipeline.step1_parsing.get_registered_document', return_value=None):
            with pytest.raises(ParsingError) as exc_info:
                run()

            assert "No registered document found" in str(exc_info.value)

    def test_step1_fails_with_missing_pdf(self, temp_db_with_registered_doc_4_pages):
        """
        Step 1 fails gracefully when PDF file missing.
        """
        db_path, doc_id = temp_db_with_registered_doc_4_pages

        import src.pipeline.step1_parsing as step1_module
        original_pdf_path = step1_module.SOURCE_PDF_PATH

        # Point to non-existent PDF
        fake_pdf = Path("/nonexistent/fake.pdf")
        step1_module.SOURCE_PDF_PATH = fake_pdf

        try:
            with patch('src.pipeline.step1_parsing.get_registered_document', return_value=doc_id):
                with pytest.raises(ParsingError) as exc_info:
                    run()

                assert "PDF not found" in str(exc_info.value)

        finally:
            step1_module.SOURCE_PDF_PATH = original_pdf_path


@pytest.mark.integration
class TestStep1OutputQuality:
    """Tests for quality of Step 1 output"""

    def test_all_blocks_have_content(self, temp_db_with_registered_doc_4_pages, test_pdf_4_pages):
        """
        All blocks have either text_content or markdown_content.
        """
        db_path, doc_id = temp_db_with_registered_doc_4_pages

        import src.pipeline.step1_parsing as step1_module
        original_pdf_path = step1_module.SOURCE_PDF_PATH
        step1_module.SOURCE_PDF_PATH = test_pdf_4_pages

        try:
            # Patch DATABASE_PATH in connections module where it's used
            with patch('src.pipeline.step1_parsing.get_registered_document', return_value=doc_id), \
                 patch('src.database.connections.DATABASE_PATH', db_path):

                run()

            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Check for blocks with no content
            cursor.execute("""
                SELECT COUNT(*)
                FROM raw_blocks
                WHERE (text_content IS NULL OR text_content = '')
                AND (markdown_content IS NULL OR markdown_content = '')
            """)
            empty_blocks = cursor.fetchone()[0]

            conn.close()

            assert empty_blocks == 0, f"Found {empty_blocks} blocks with no content"

        finally:
            step1_module.SOURCE_PDF_PATH = original_pdf_path

    def test_page_sequence_complete(self, temp_db_with_registered_doc_4_pages, test_pdf_4_pages):
        """
        No gaps in page sequence.
        """
        db_path, doc_id = temp_db_with_registered_doc_4_pages

        import src.pipeline.step1_parsing as step1_module
        original_pdf_path = step1_module.SOURCE_PDF_PATH
        step1_module.SOURCE_PDF_PATH = test_pdf_4_pages

        try:
            # Patch DATABASE_PATH in connections module where it's used
            with patch('src.pipeline.step1_parsing.get_registered_document', return_value=doc_id), \
                 patch('src.database.connections.DATABASE_PATH', db_path):

                run()

            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            cursor.execute("SELECT DISTINCT page_number FROM raw_blocks ORDER BY page_number")
            pages = [row[0] for row in cursor.fetchall()]

            conn.close()

            # Check for gaps
            if len(pages) > 0:
                expected_pages = list(range(1, max(pages) + 1))
                missing_pages = set(expected_pages) - set(pages)
                assert len(missing_pages) == 0, f"Missing pages in sequence: {missing_pages}"

        finally:
            step1_module.SOURCE_PDF_PATH = original_pdf_path

    def test_block_type_distribution_is_plausible(self, temp_db_with_registered_doc_4_pages, test_pdf_4_pages):
        """
        raw_blocks contains a plausible distribution of Docling block types.

        Validates:
        - Multiple distinct block types exist (≥2)
        - Content blocks (text/paragraph/list_item) are present
        - Content blocks are most common (>50% of total)
        - Section headers exist but are less common (<25% of total)
        """
        db_path, doc_id = temp_db_with_registered_doc_4_pages

        import src.pipeline.step1_parsing as step1_module
        original_pdf_path = step1_module.SOURCE_PDF_PATH
        step1_module.SOURCE_PDF_PATH = test_pdf_4_pages

        try:
            # Patch DATABASE_PATH in connections module where it's used
            with patch('src.pipeline.step1_parsing.get_registered_document', return_value=doc_id), \
                 patch('src.database.connections.DATABASE_PATH', db_path):

                run()

            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Get total block count
            cursor.execute("SELECT COUNT(*) FROM raw_blocks")
            total_blocks = cursor.fetchone()[0]

            # Get block type distribution
            cursor.execute("""
                SELECT block_type, COUNT(*) as count
                FROM raw_blocks
                GROUP BY block_type
                ORDER BY count DESC
            """)
            distribution = {row[0]: row[1] for row in cursor.fetchall()}

            conn.close()

            # Validation 1: Multiple block types exist
            assert len(distribution) >= 2, f"Expected ≥2 block types, got {len(distribution)}: {list(distribution.keys())}"

            # Validation 2: Content blocks exist (text, paragraph, list_item)
            content_count = (distribution.get('text', 0) +
                           distribution.get('paragraph', 0) +
                           distribution.get('list_item', 0))
            assert content_count > 0, "Should have content blocks (text, paragraph, or list_item)"

            # Validation 3: Content blocks should be most common (>50%)
            content_percentage = (content_count / total_blocks) * 100
            assert content_percentage > 50, f"Content blocks should be >50% of total, got {content_percentage:.1f}%"

            # Validation 4: Section headers should exist but be less common (<25%)
            header_count = distribution.get('section_header', 0)
            if header_count > 0:
                header_percentage = (header_count / total_blocks) * 100
                assert header_percentage < 25, f"Section headers should be <25% of total, got {header_percentage:.1f}%"

            print(f"\n✓ Block type distribution is plausible:")
            for block_type, count in distribution.items():
                percentage = (count / total_blocks) * 100
                print(f"  {block_type}: {count} ({percentage:.1f}%)")

        finally:
            step1_module.SOURCE_PDF_PATH = original_pdf_path
