"""
Database Operations for Cleanup (Step 3)

Functions for querying sections, raw blocks, and managing parent chunks.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

from src.database import get_connection
from src.utils.logging_config import logger


def get_level2_sections(document_id: str) -> List[Dict[str, Any]]:
    """
    Get all level-2 sections (disease/topic) for a document.

    Args:
        document_id: Document UUID

    Returns:
        List of section dicts with id, heading, heading_path, page_start, page_end, order_index
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, heading, heading_path, page_start, page_end, order_index
            FROM sections
            WHERE document_id = ? AND level = 2
            ORDER BY order_index
        """, (document_id,))

        rows = cursor.fetchall()
        sections = [dict(row) for row in rows]

    logger.debug(f"Retrieved {len(sections)} level-2 sections for document {document_id}")
    return sections


def get_section_with_descendants(section_id: int) -> List[int]:
    """
    Get a section and all its descendant section IDs.

    Uses heading_path hierarchy to find all child sections.

    Args:
        section_id: Parent section ID

    Returns:
        List of section IDs including parent and all descendants
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get the section's heading_path
        cursor.execute("SELECT heading_path FROM sections WHERE id = ?", (section_id,))
        result = cursor.fetchone()
        if not result:
            logger.warning(f"Section {section_id} not found")
            return [section_id]

        heading_path = result[0]

        # Get all sections that start with this heading_path
        cursor.execute("""
            SELECT id FROM sections
            WHERE heading_path LIKE ? OR heading_path = ?
            ORDER BY order_index
        """, (heading_path + ' > %', heading_path))

        section_ids = [row[0] for row in cursor.fetchall()]

    logger.debug(f"Found {len(section_ids)} sections (including descendants) for section {section_id}")
    return section_ids


def get_raw_blocks_for_sections(section_ids: List[int]) -> List[Dict[str, Any]]:
    """
    Get all raw blocks for a list of sections, ordered by page and block ID.

    Args:
        section_ids: List of section IDs

    Returns:
        List of raw block dicts
    """
    if not section_ids:
        logger.debug("No section IDs provided, returning empty list")
        return []

    with get_connection() as conn:
        cursor = conn.cursor()

        placeholders = ','.join('?' * len(section_ids))
        cursor.execute(f"""
            SELECT id, section_id, block_type, text_content, markdown_content,
                   page_number, page_range, docling_level, metadata
            FROM raw_blocks
            WHERE section_id IN ({placeholders})
            ORDER BY page_number, id
        """, section_ids)

        blocks = [dict(row) for row in cursor.fetchall()]

    logger.debug(f"Retrieved {len(blocks)} raw blocks for {len(section_ids)} sections")
    return blocks


def get_subsections_for_section(section_id: int) -> List[Dict[str, Any]]:
    """
    Get immediate subsections (level >= 3) under a level-2 section.

    Args:
        section_id: Level-2 section ID

    Returns:
        List of subsection dicts with id, level, heading, heading_path, order_index
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get the section's heading_path
        cursor.execute("SELECT heading_path FROM sections WHERE id = ?", (section_id,))
        result = cursor.fetchone()
        if not result:
            logger.warning(f"Section {section_id} not found")
            return []

        heading_path = result[0]

        # Get all subsections (level >= 3)
        cursor.execute("""
            SELECT id, level, heading, heading_path, page_start, page_end, order_index
            FROM sections
            WHERE heading_path LIKE ? AND level >= 3
            ORDER BY order_index
        """, (heading_path + ' > %',))

        subsections = [dict(row) for row in cursor.fetchall()]

    logger.debug(f"Found {len(subsections)} subsections for section {section_id}")
    return subsections


def check_existing_parent_chunks(document_id: str) -> int:
    """
    Check if parent chunks already exist for a document.

    Args:
        document_id: Document UUID

    Returns:
        Count of existing parent chunks
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM parent_chunks pc
            JOIN sections s ON pc.section_id = s.id
            WHERE s.document_id = ?
        """, (document_id,))
        count = cursor.fetchone()[0]

    if count > 0:
        logger.debug(f"Found {count} existing parent chunks for document {document_id}")

    return count


def delete_parent_chunks_for_document(document_id: str) -> int:
    """
    Delete all parent chunks for a document.

    Args:
        document_id: Document UUID

    Returns:
        Number of chunks deleted
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get section IDs for this document
        cursor.execute("SELECT id FROM sections WHERE document_id = ?", (document_id,))
        section_ids = [row[0] for row in cursor.fetchall()]

        if not section_ids:
            logger.debug(f"No sections found for document {document_id}, nothing to delete")
            return 0

        placeholders = ','.join('?' * len(section_ids))
        cursor.execute(f"""
            DELETE FROM parent_chunks
            WHERE section_id IN ({placeholders})
        """, section_ids)

        deleted = cursor.rowcount
        conn.commit()

    logger.info(f"Deleted {deleted} existing parent chunks for document {document_id}")
    return deleted


def insert_parent_chunks_batch(chunks: List[Dict[str, Any]]) -> int:
    """
    Insert a batch of parent chunks into the database.

    Uses transaction for atomicity. Rolls back on any error.

    Args:
        chunks: List of chunk dicts with section_id, content, token_count, etc.

    Returns:
        Number of chunks inserted

    Raises:
        Exception: If insertion fails (transaction rolled back)
    """
    if not chunks:
        logger.debug("No chunks to insert")
        return 0

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")

        try:
            for chunk in chunks:
                cursor.execute("""
                    INSERT INTO parent_chunks (
                        section_id, content, token_count,
                        page_start, page_end, metadata
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    chunk['section_id'],
                    chunk['content'],
                    chunk['token_count'],
                    chunk.get('page_start'),
                    chunk.get('page_end'),
                    json.dumps({
                        'heading_path': chunk.get('heading_path'),
                        'order_index': chunk.get('order_index'),
                    })
                ))

            conn.commit()
            logger.debug(f"Inserted {len(chunks)} parent chunks in batch")
            return len(chunks)

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to insert parent chunks batch: {e}")
            raise


def export_parent_chunks_to_markdown(document_id: str, output_path: Path) -> int:
    """
    Export all parent chunks to a markdown file for review.

    Creates parent directory if it doesn't exist.

    Args:
        document_id: Document UUID
        output_path: Path to write markdown export

    Returns:
        Number of chunks exported
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                pc.id,
                pc.section_id,
                pc.content,
                pc.token_count,
                pc.page_start,
                pc.page_end,
                pc.metadata,
                s.heading_path
            FROM parent_chunks pc
            JOIN sections s ON pc.section_id = s.id
            WHERE s.document_id = ?
            ORDER BY s.order_index, pc.id
        """, (document_id,))

        chunks = cursor.fetchall()

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Parent Chunks Export\n\n")
        f.write(f"**Document ID:** {document_id}\n")
        f.write(f"**Total Chunks:** {len(chunks)}\n")
        f.write(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")

        for chunk in chunks:
            chunk_id = chunk[0]
            section_id = chunk[1]
            content = chunk[2]
            token_count = chunk[3]
            page_start = chunk[4]
            page_end = chunk[5]
            metadata = json.loads(chunk[6]) if chunk[6] else {}
            heading_path = chunk[7]

            f.write(f"## Chunk {chunk_id}\n\n")
            f.write(f"- **chunk_id:** {chunk_id}\n")
            f.write(f"- **section_id:** {section_id}\n")
            f.write(f"- **heading_path:** {heading_path}\n")
            f.write(f"- **token_count:** {token_count}\n")
            f.write(f"- **pages:** {page_start or '?'}-{page_end or '?'}\n")
            if metadata.get('order_index') is not None:
                f.write(f"- **order_index:** {metadata['order_index']}\n")
            f.write("\n### Content\n\n")
            f.write(content)
            f.write("\n\n---\n\n")

    logger.info(f"Exported {len(chunks)} parent chunks to {output_path}")
    return len(chunks)


def get_document_id(db_path: Path) -> Optional[str]:
    """
    Auto-detect document ID if only one document exists.

    Args:
        db_path: Path to database

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
