"""
Database Operations Module

Provides reusable database helper functions for common ETL operations:
- Batch insertion with transaction handling
- Document updates
- Statistics collection
- Error handling and rollback

These functions abstract away the complexity of transaction management
and provide consistent error handling across pipeline steps.
"""

import json
from typing import Dict, List, Any, Optional, Tuple

from src.database.connections import get_connection
from src.utils.logging_config import logger


class DatabaseError(Exception):
    """Raised when database operations fail."""
    pass


def get_registered_document() -> Optional[str]:
    """
    Get the most recently registered document ID from the database.

    Returns:
        Document ID (UUID string) if exists, None otherwise

    Example:
        >>> doc_id = get_registered_document()
        >>> if doc_id:
        ...     print(f"Found document: {doc_id}")
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM documents ORDER BY created_at DESC LIMIT 1")
            result = cursor.fetchone()

            if result:
                return result[0]
            return None

    except Exception as e:
        logger.error(f"Failed to get registered document: {e}")
        return None


def update_docling_json(document_id: str, doc_json: Dict[str, Any]) -> None:
    """
    Update documents.docling_json with full Docling output.

    Stores the complete Docling parser output as JSON for traceability
    and debugging. This enables re-processing without re-parsing the PDF.

    Args:
        document_id: UUID of the document
        doc_json: Full Docling JSON output as dict

    Raises:
        DatabaseError: If update fails

    Example:
        >>> doc_json = {"name": "UCG-23", "elements": [...]}
        >>> update_docling_json(document_id, doc_json)
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            logger.info("Updating documents.docling_json with full Docling output...")
            cursor.execute("BEGIN")

            cursor.execute(
                "UPDATE documents SET docling_json = ? WHERE id = ?",
                (json.dumps(doc_json, ensure_ascii=False), document_id)
            )

            # Verify update succeeded
            if cursor.rowcount == 0:
                raise DatabaseError(f"No document found with id: {document_id}")

            logger.success("✓ documents.docling_json updated")

    except Exception as e:
        logger.error(f"Failed to update docling_json: {e}")
        raise DatabaseError(f"Failed to update docling_json: {e}") from e


def batch_insert_raw_blocks(
    blocks: List[Dict[str, Any]],
    batch_size: int = 100
) -> Tuple[int, int]:
    """
    Insert blocks into raw_blocks table in batches with transaction handling.

    Each batch is wrapped in a transaction. If a batch fails, it's rolled back
    and the function continues with the next batch. This ensures partial success
    rather than all-or-nothing behavior.

    Args:
        blocks: List of block dicts to insert with keys:
            - document_id: UUID of the document
            - block_type: Docling's native label
            - text_content: Plain text (optional)
            - markdown_content: Markdown text (optional)
            - page_number: Source page number
            - page_range: For multi-page elements (optional)
            - docling_level: Hierarchy level (optional)
            - bbox: Bounding box JSON (optional)
            - is_continuation: Boolean for multi-page tables
            - element_id: Docling's element identifier (optional)
            - metadata: Additional metadata JSON
        batch_size: Number of blocks per transaction (default: 100)

    Returns:
        Tuple of (total_inserted, total_failed)

    Raises:
        DatabaseError: If all batches fail

    Example:
        >>> blocks = [
        ...     {
        ...         'document_id': 'uuid-123',
        ...         'block_type': 'text',
        ...         'text_content': 'Some text...',
        ...         'page_number': 5,
        ...         ...
        ...     }
        ... ]
        >>> inserted, failed = batch_insert_raw_blocks(blocks, batch_size=100)
        >>> print(f"Inserted: {inserted}, Failed: {failed}")
    """
    total_inserted = 0
    total_failed = 0

    logger.info(f"Inserting {len(blocks)} blocks in batches of {batch_size}...")

    # Process in batches
    for batch_start in range(0, len(blocks), batch_size):
        batch_end = min(batch_start + batch_size, len(blocks))
        batch = blocks[batch_start:batch_end]
        batch_num = batch_start // batch_size + 1

        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN")

                for block in batch:
                    cursor.execute(
                        """
                        INSERT INTO raw_blocks (
                            document_id, block_type, text_content, markdown_content,
                            page_number, page_range, docling_level, bbox,
                            is_continuation, element_id, metadata
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            block['document_id'],
                            block['block_type'],
                            block['text_content'],
                            block['markdown_content'],
                            block['page_number'],
                            block['page_range'],
                            block['docling_level'],
                            block['bbox'],
                            block['is_continuation'],
                            block['element_id'],
                            block['metadata'],
                        )
                    )

                total_inserted += len(batch)
                logger.info(
                    f"  Batch {batch_num}: Inserted {len(batch)} blocks "
                    f"({total_inserted}/{len(blocks)})"
                )

        except Exception as e:
            total_failed += len(batch)
            logger.error(f"  Batch {batch_num} FAILED: {e}")
            logger.warning(f"  Rolled back {len(batch)} blocks")
            continue

    # Summary
    if total_failed > 0:
        logger.warning(f"⚠ {total_failed} blocks failed to insert")

    if total_inserted == 0:
        raise DatabaseError("All batches failed - no blocks were inserted")

    logger.success(f"✓ Successfully inserted {total_inserted} blocks")
    return (total_inserted, total_failed)


def check_blocks_exist(document_id: str) -> int:
    """
    Check how many blocks already exist for a document.

    Useful for idempotency checks - skip re-parsing if blocks already exist.

    Args:
        document_id: UUID of the document

    Returns:
        Number of existing blocks (0 if none)

    Example:
        >>> count = check_blocks_exist(doc_id)
        >>> if count > 0:
        ...     print(f"Already parsed: {count} blocks exist")
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM raw_blocks WHERE document_id = ?",
                (document_id,)
            )
            return cursor.fetchone()[0]
    except Exception as e:
        logger.debug(f"Could not check existing blocks: {e}")
        return 0


def collect_block_statistics(document_id: str) -> Dict[str, Any]:
    """
    Collect comprehensive statistics about parsed blocks.

    Gathers counts, page coverage, content validation, and block type
    distribution for reporting and validation.

    Args:
        document_id: UUID of the document

    Returns:
        Dict with statistics:
            - total_blocks: Total number of blocks
            - type_counts: Dict of {block_type: count}
            - page_start: First page number
            - page_end: Last page number
            - page_count: Total pages covered
            - has_text_content: Blocks with text_content
            - has_markdown_content: Blocks with markdown_content
            - missing_content: Blocks missing both content fields

    Example:
        >>> stats = collect_block_statistics(doc_id)
        >>> print(f"Total blocks: {stats['total_blocks']}")
        >>> print(f"Page coverage: {stats['page_start']}-{stats['page_end']}")
    """
    stats = {}

    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # Total blocks
            cursor.execute(
                "SELECT COUNT(*) FROM raw_blocks WHERE document_id = ?",
                (document_id,)
            )
            stats['total_blocks'] = cursor.fetchone()[0]

            # Counts by block_type
            cursor.execute(
                """
                SELECT block_type, COUNT(*) as count
                FROM raw_blocks
                WHERE document_id = ?
                GROUP BY block_type
                ORDER BY count DESC
                """,
                (document_id,)
            )
            type_counts = {}
            for row in cursor.fetchall():
                type_counts[row[0]] = row[1]
            stats['type_counts'] = type_counts

            # Page coverage
            cursor.execute(
                """
                SELECT MIN(page_number), MAX(page_number)
                FROM raw_blocks
                WHERE document_id = ?
                """,
                (document_id,)
            )
            result = cursor.fetchone()
            stats['page_start'] = result[0]
            stats['page_end'] = result[1]
            stats['page_count'] = (result[1] - result[0] + 1) if result[0] and result[1] else 0

            # Content validation
            cursor.execute(
                """
                SELECT
                    COUNT(CASE WHEN text_content IS NOT NULL THEN 1 END) as has_text,
                    COUNT(CASE WHEN markdown_content IS NOT NULL THEN 1 END) as has_markdown,
                    COUNT(CASE WHEN text_content IS NULL AND markdown_content IS NULL THEN 1 END) as missing_content
                FROM raw_blocks
                WHERE document_id = ?
                """,
                (document_id,)
            )
            result = cursor.fetchone()
            stats['has_text_content'] = result[0]
            stats['has_markdown_content'] = result[1]
            stats['missing_content'] = result[2]

    except Exception as e:
        logger.error(f"Failed to collect statistics: {e}")
        return stats

    return stats


def log_block_statistics(stats: Dict[str, Any]) -> None:
    """
    Log block statistics in a formatted, human-readable way.

    Args:
        stats: Statistics dict from collect_block_statistics()

    Example:
        >>> stats = collect_block_statistics(doc_id)
        >>> log_block_statistics(stats)
        # Outputs formatted table to logs
    """
    logger.info("")
    logger.info("=" * 80)
    logger.info("PARSING STATISTICS")
    logger.info("=" * 80)

    logger.info(f"Total blocks parsed:      {stats.get('total_blocks', 0):,}")
    logger.info(
        f"Page coverage:            {stats.get('page_start', 0)} - "
        f"{stats.get('page_end', 0)} ({stats.get('page_count', 0)} pages)"
    )
    logger.info(f"Blocks with text:         {stats.get('has_text_content', 0):,}")
    logger.info(f"Blocks with markdown:     {stats.get('has_markdown_content', 0):,}")

    if stats.get('missing_content', 0) > 0:
        logger.warning(f"⚠ Blocks missing content: {stats['missing_content']}")

    logger.info("")
    logger.info("Block type distribution:")

    type_counts = stats.get('type_counts', {})
    for block_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / stats.get('total_blocks', 1)) * 100
        logger.info(f"  {block_type:20s}: {count:6,} ({percentage:5.1f}%)")

    logger.info("=" * 80)
    logger.info("")


def get_document_info(document_id: str) -> Optional[Dict[str, Any]]:
    """
    Get complete document information from the database.

    Args:
        document_id: UUID of the document

    Returns:
        Dict with document info or None if not found:
            - id: Document UUID
            - title: Document title
            - version_label: Version string
            - checksum_sha256: PDF checksum
            - created_at: Registration timestamp
            - has_docling_json: Boolean indicating if Docling JSON exists

    Example:
        >>> info = get_document_info(doc_id)
        >>> print(f"Title: {info['title']}")
        >>> print(f"Version: {info['version_label']}")
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, title, version_label, checksum_sha256, created_at,
                       (docling_json IS NOT NULL) as has_docling_json
                FROM documents
                WHERE id = ?
                """,
                (document_id,)
            )
            result = cursor.fetchone()

            if result:
                return {
                    'id': result[0],
                    'title': result[1],
                    'version_label': result[2],
                    'checksum_sha256': result[3],
                    'created_at': result[4],
                    'has_docling_json': bool(result[5]),
                }
            return None

    except Exception as e:
        logger.error(f"Failed to get document info: {e}")
        return None


__all__ = [
    "get_registered_document",
    "update_docling_json",
    "batch_insert_raw_blocks",
    "check_blocks_exist",
    "collect_block_statistics",
    "log_block_statistics",
    "get_document_info",
    "DatabaseError",
]
