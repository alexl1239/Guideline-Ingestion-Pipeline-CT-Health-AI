"""
Database Operations for Table Linearization (Step 3)

Option A design: Step 3 (tables) runs BEFORE Step 4 (cleanup). It reads
table blocks from raw_blocks, sends them to an LLM for linearization, and
writes the prose result to raw_blocks.text_content. Step 4 then picks up
the linearized text naturally via clean_block() during parent chunk
construction — no markers, no in-place patching, accurate token counts
from the start.
"""

from typing import Dict, List, Any, Optional

from src.database import get_connection
from src.utils.logging_config import logger


def get_table_blocks_for_document(document_id: str) -> List[Dict[str, Any]]:
    """
    Get all table raw blocks for a document, with section context.

    The heading_path is included so the LLM prompt can specify the clinical
    topic (e.g. "Malaria > Treatment") for accurate linearization.

    Args:
        document_id: Document UUID

    Returns:
        List of dicts with id, markdown_content, text_content, page_number,
        page_range, section_id, heading_path
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                rb.id,
                rb.block_type,
                rb.markdown_content,
                rb.text_content,
                rb.page_number,
                rb.page_range,
                rb.section_id,
                s.heading_path
            FROM raw_blocks rb
            LEFT JOIN sections s ON rb.section_id = s.id
            WHERE rb.document_id = ?
              AND rb.block_type = 'table'
            ORDER BY rb.page_number, rb.id
        """, (document_id,))

        blocks = [dict(row) for row in cursor.fetchall()]

    logger.debug(f"Found {len(blocks)} table blocks for document {document_id}")
    return blocks


def update_raw_block_text_content(block_id: int, text: str) -> None:
    """
    Write linearized table prose to raw_blocks.text_content for a single block.

    Step 4's clean_block() reads text_content first when block_type='table',
    so this is how Step 3's output reaches the parent chunks.

    Args:
        block_id: raw_blocks primary key
        text: Linearized table prose (markdown)

    Raises:
        Exception: If the update fails (caller should handle rollback)
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE raw_blocks
            SET text_content = ?
            WHERE id = ?
        """, (text, block_id))
        conn.commit()

    logger.debug(f"Updated raw_block {block_id} text_content ({len(text)} chars)")


def batch_update_raw_blocks_text_content(updates: List[Dict[str, Any]]) -> int:
    """
    Update text_content on multiple raw blocks in a single transaction.

    Args:
        updates: List of dicts with 'id' and 'text_content' keys

    Returns:
        Number of blocks updated

    Raises:
        Exception: If batch update fails (transaction rolled back)
    """
    if not updates:
        return 0

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")

        try:
            for update in updates:
                cursor.execute("""
                    UPDATE raw_blocks
                    SET text_content = ?
                    WHERE id = ?
                """, (update['text_content'], update['id']))

            conn.commit()
            logger.debug(f"Batch updated text_content on {len(updates)} raw blocks")
            return len(updates)

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to batch update raw blocks: {e}")
            raise


def count_unlinearized_tables(document_id: str) -> int:
    """
    Count table blocks that have not yet been linearized.

    Useful as a precondition check before running Step 4 — if this is > 0
    after Step 3 should have run, something went wrong.

    Args:
        document_id: Document UUID

    Returns:
        Number of table blocks where text_content is NULL or empty
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM raw_blocks
            WHERE document_id = ?
              AND block_type = 'table'
              AND (text_content IS NULL OR TRIM(text_content) = '')
        """, (document_id,))
        return cursor.fetchone()[0]


def get_document_id_for_tables(db_path: Optional[str] = None) -> Optional[str]:
    """
    Auto-detect document ID if only one document exists.

    Mirrors the helper in src/utils/cleanup/database.py so Step 3 has its
    own entry point without depending on the cleanup package.

    Args:
        db_path: Optional database path override

    Returns:
        Document ID string or None if multiple/no documents
    """
    with get_connection(db_path=db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM documents")
        docs = cursor.fetchall()

        if len(docs) == 0:
            logger.error("No documents found in database")
            return None
        elif len(docs) == 1:
            doc_id = docs[0][0]
            logger.info(f"Auto-detected document: {docs[0][1]} ({doc_id})")
            return doc_id
        else:
            logger.error("Multiple documents found. Please specify --doc-id:")
            for doc in docs:
                logger.info(f"  {doc[0]}: {doc[1]}")
            return None
