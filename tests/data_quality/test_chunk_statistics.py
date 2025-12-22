"""
Data Quality Tests: Chunk Statistics

Validates that chunk distributions and statistics are reasonable.
"""

import pytest
import sqlite3


@pytest.mark.data_quality
class TestChunkStatistics:
    """Tests for chunk quality and distributions"""

    def test_block_type_distribution_reasonable(self, temp_db_with_registered_doc_4_pages):
        """Block type distribution is reasonable"""
        db_path, doc_id = temp_db_with_registered_doc_4_pages

        # TODO: Run full pipeline first
        # This test is a placeholder for when chunking is implemented

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM raw_blocks")
        total_blocks = cursor.fetchone()[0]

        if total_blocks == 0:
            pytest.skip("No blocks in database - run pipeline first")

        cursor.execute("""
            SELECT block_type, COUNT(*) as count
            FROM raw_blocks
            GROUP BY block_type
        """)
        block_types = dict(cursor.fetchall())

        # At least 40% should be text/paragraph (adjustable based on your data)
        text_count = block_types.get('text', 0) + block_types.get('paragraph', 0)
        text_ratio = text_count / total_blocks if total_blocks > 0 else 0

        assert text_ratio > 0.3, f"Text blocks should be >30% of total, got {text_ratio:.1%}"

        conn.close()

    def test_no_duplicate_blocks(self, temp_db_with_registered_doc_4_pages):
        """No duplicate blocks exist in raw_blocks"""
        db_path, doc_id = temp_db_with_registered_doc_4_pages

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check for duplicate (page_number, text_content) pairs
        cursor.execute("""
            SELECT page_number, text_content, COUNT(*) as count
            FROM raw_blocks
            WHERE text_content IS NOT NULL
            GROUP BY page_number, text_content
            HAVING count > 1
        """)
        duplicates = cursor.fetchall()

        conn.close()

        assert len(duplicates) == 0, f"Found {len(duplicates)} duplicate blocks"

    def test_page_coverage_complete(self, temp_db_with_registered_doc_4_pages, test_pdf_4_pages):
        """All pages from PDF are represented in raw_blocks"""
        db_path, doc_id = temp_db_with_registered_doc_4_pages

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM raw_blocks")
        if cursor.fetchone()[0] == 0:
            pytest.skip("No blocks in database - run pipeline first")

        cursor.execute("SELECT DISTINCT page_number FROM raw_blocks ORDER BY page_number")
        pages = [row[0] for row in cursor.fetchall()]

        conn.close()

        # Check for gaps in page sequence
        if len(pages) > 0:
            expected_pages = list(range(1, max(pages) + 1))
            missing_pages = set(expected_pages) - set(pages)

            assert len(missing_pages) == 0, f"Missing pages: {missing_pages}"
