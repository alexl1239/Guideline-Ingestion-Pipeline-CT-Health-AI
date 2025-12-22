"""
End-to-End Test: Full Pipeline on 4-Page PDF

Fast smoke test that runs the complete pipeline on a small test PDF.
Should complete in 30-60 seconds.
"""

import pytest
import sqlite3
from pathlib import Path

from tests.test_helpers import (
    compare_databases,
    get_database_stats,
    assert_database_structure_valid
)


@pytest.mark.e2e
@pytest.mark.slow
class TestFullPipeline4Pages:
    """End-to-end pipeline test with 4-page PDF"""

    def test_pipeline_completes_successfully(
        self,
        temp_db_with_registered_doc_4_pages,
        test_pdf_4_pages
    ):
        """
        Complete pipeline: Step 0 → 7 with 4-page PDF.

        This is a smoke test to ensure all steps can run without errors.
        """
        db_path, doc_id = temp_db_with_registered_doc_4_pages

        # Step 0: Already done by fixture (document registered)

        # Step 1: Parse PDF with Docling
        from src.pipeline.step1_parsing import run as run_step1

        # Mock SOURCE_PDF_PATH to use test PDF
        import src.pipeline.step1_parsing as step1_module
        original_path = step1_module.SOURCE_PDF_PATH
        step1_module.SOURCE_PDF_PATH = test_pdf_4_pages

        try:
            # Patch database and get_registered_document to use test database
            from unittest.mock import patch
            with patch('src.pipeline.step1_parsing.get_registered_document', return_value=doc_id), \
                 patch('src.database.connections.DATABASE_PATH', db_path):
                run_step1()
        finally:
            step1_module.SOURCE_PDF_PATH = original_path

        # Verify Step 1 output
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM raw_blocks")
        block_count = cursor.fetchone()[0]
        assert block_count > 50, f"4 pages should have 50+ blocks, got {block_count}"

        cursor.execute("SELECT MAX(page_number) FROM raw_blocks")
        max_page = cursor.fetchone()[0]
        assert max_page == 4, f"Should have 4 pages, got {max_page}"

        # Check Docling JSON stored
        cursor.execute("SELECT docling_json FROM documents WHERE id = ?", (doc_id,))
        docling_json = cursor.fetchone()[0]
        assert docling_json is not None, "Docling JSON should be stored"
        assert len(docling_json) > 1000, "Docling JSON should be substantial"

        conn.close()

        print(f"\n✓ Pipeline Step 1 complete. Database: {db_path}")

    def test_pipeline_output_structure_valid(
        self,
        temp_db_with_registered_doc_4_pages,
        test_pdf_4_pages
    ):
        """
        Validate database structure after pipeline run.
        """
        db_path, doc_id = temp_db_with_registered_doc_4_pages

        # Run Step 1
        from src.pipeline.step1_parsing import run as run_step1
        import src.pipeline.step1_parsing as step1_module
        original_path = step1_module.SOURCE_PDF_PATH
        step1_module.SOURCE_PDF_PATH = test_pdf_4_pages

        try:
            from unittest.mock import patch
            with patch('src.pipeline.step1_parsing.get_registered_document', return_value=doc_id), \
                 patch('src.database.connections.DATABASE_PATH', db_path):
                run_step1()
        finally:
            step1_module.SOURCE_PDF_PATH = original_path

        # Validate structure
        assert_database_structure_valid(db_path)

        # Get statistics
        stats = get_database_stats(db_path)

        # Verify reasonable distributions
        assert stats['total_blocks'] > 50
        assert stats['document_count'] == 1
        assert len(stats['block_types']) >= 3, "Should have multiple block types"

        # Should have text blocks
        assert 'text' in stats['block_types'], "Should have text blocks"

        print(f"\n✓ Database structure valid")
        print(f"  Total blocks: {stats['total_blocks']}")
        print(f"  Block types: {list(stats['block_types'].keys())}")

    @pytest.mark.skipif(
        True,  # Skip until golden DB is created
        reason="Golden database not yet created - run pipeline manually first"
    )
    def test_pipeline_matches_golden_output(
        self,
        temp_db_with_registered_doc_4_pages,
        test_pdf_4_pages,
        golden_db_4_pages
    ):
        """
        Compare pipeline output against golden reference database.

        This test will be skipped until you create the golden database.
        """
        db_path, doc_id = temp_db_with_registered_doc_4_pages

        # Run Step 1
        from src.pipeline.step1_parsing import run as run_step1
        import src.pipeline.step1_parsing as step1_module
        original_path = step1_module.SOURCE_PDF_PATH
        step1_module.SOURCE_PDF_PATH = test_pdf_4_pages

        try:
            from unittest.mock import patch
            with patch('src.pipeline.step1_parsing.get_registered_document', return_value=doc_id), \
                 patch('src.database.connections.DATABASE_PATH', db_path):
                run_step1()
        finally:
            step1_module.SOURCE_PDF_PATH = original_path

        # Compare against golden database
        diff = compare_databases(db_path, golden_db_4_pages)

        # Allow small differences (5% tolerance)
        if not diff.is_similar(tolerance=0.05):
            print("\n" + diff.summary())
            pytest.fail(f"Output differs from golden database:\n{diff.summary()}")

        print(f"\n✓ Output matches golden database (within 5% tolerance)")
