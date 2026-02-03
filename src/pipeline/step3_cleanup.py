"""
STEP 3 — CLEANUP AND PARENT CHUNK CONSTRUCTION

Removes noise, normalizes markdown content, and constructs parent chunks
from raw blocks for RAG retrieval.

Document-agnostic: Works with any clinical guideline document structure.

Process:
1. Load sections and raw_blocks from database
2. Filter out page headers/footers (block_type in {page_header, page_footer})
3. Normalize markdown: bullets, whitespace, heading levels
4. Insert figure/caption placeholders for important images
5. Concatenate cleaned blocks per level-2 section (topic)
6. Split into parent chunks targeting 1000-1500 tokens, hard max 2000
7. Write parent chunks to database with token counts

Input: Populated raw_blocks table with section_id assignments (from Step 2)
Output: Populated parent_chunks table

Transaction Boundary: Per batch of 10 sections

Architecture:
- Uses modular utilities from src/utils/cleanup/ for text normalization,
  chunking logic, and database operations
- Uses shared tokenization from src/utils/tokenization.py
- Main file contains orchestration logic and CLI interface only
"""

import argparse
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

from src.config import (
    DATABASE_PATH,
    PARENT_TOKEN_HARD_MAX,
    CLEANUP_BATCH_SIZE,
)
from src.utils.cleanup import (
    get_level2_sections,
    check_existing_parent_chunks,
    delete_parent_chunks_for_document,
    build_section_content,
    create_parent_chunks,
    insert_parent_chunks_batch,
    export_parent_chunks_to_markdown,
    get_document_id,
)
from src.utils.tokenization import get_tokenizer
from src.utils.logging_config import logger, setup_logger


class CleanupError(Exception):
    """Raised when cleanup and parent chunk formation fails."""
    pass


def run(
    db_path: Optional[Path] = None,
    doc_id: Optional[str] = None,
    export_path: Optional[Path] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Execute Step 3: Cleanup and Parent Chunk Construction.

    Args:
        db_path: Path to database (defaults to config)
        doc_id: Document ID (auto-detected if not provided)
        export_path: Path to export parent chunks markdown (optional)
        overwrite: If True, delete existing parent chunks first

    Returns:
        Dict with statistics:
            - document_id: Document UUID
            - sections_processed: Number of level-2 sections processed
            - parent_chunks_created: Number of parent chunks created
            - token_min/max/median/mean: Token distribution statistics
            - chunks_over_limit: Number of chunks exceeding hard_max (should be 0)
            - duration_seconds: Processing time

    Raises:
        CleanupError: If cleanup fails or prerequisites not met
    """
    db_path = db_path or DATABASE_PATH
    start_time = time.time()

    logger.info("=" * 80)
    logger.info("STEP 3: CLEANUP AND PARENT CHUNK CONSTRUCTION")
    logger.info("=" * 80)

    # Get or validate document ID
    if doc_id is None:
        doc_id = get_document_id(db_path)
        if doc_id is None:
            raise CleanupError("Could not determine document ID")

    # Check for existing parent chunks
    existing_count = check_existing_parent_chunks(doc_id)
    if existing_count > 0:
        if overwrite:
            logger.warning(
                f"Found {existing_count} existing parent chunks - deleting (--overwrite)"
            )
            delete_parent_chunks_for_document(doc_id)
        else:
            logger.error(
                f"Found {existing_count} existing parent chunks for document {doc_id}. "
                f"Use --overwrite to replace them."
            )
            raise CleanupError("Parent chunks already exist. Use --overwrite to replace.")

    # Get level-2 sections (topics)
    logger.info("Loading level-2 sections (topics)...")
    sections = get_level2_sections(doc_id)

    if not sections:
        logger.error("No level-2 sections found. Please run Step 2 first.")
        raise CleanupError("No level-2 sections found")

    logger.success(f"Found {len(sections)} level-2 sections")

    # Initialize tokenizer
    tokenizer = get_tokenizer()
    logger.debug(f"Initialized tokenizer: {tokenizer.name}")

    # Process sections in batches (as per CLAUDE.md transaction boundaries)
    total_chunks_created = 0
    all_token_counts = []
    batch_size = CLEANUP_BATCH_SIZE

    for batch_start in range(0, len(sections), batch_size):
        batch_end = min(batch_start + batch_size, len(sections))
        batch_sections = sections[batch_start:batch_end]
        batch_num = batch_start // batch_size + 1
        total_batches = (len(sections) + batch_size - 1) // batch_size

        logger.info(
            f"Processing batch {batch_num}/{total_batches} "
            f"({len(batch_sections)} sections)..."
        )

        batch_chunks = []

        for section in batch_sections:
            section_id = section['id']
            heading = section['heading']

            try:
                # Build content for this section
                full_content, units = build_section_content(section, tokenizer)

                if not units:
                    logger.debug(f"No content for section: {heading}")
                    continue

                # Create parent chunks from units
                chunks = create_parent_chunks(section, units, tokenizer)

                for chunk in chunks:
                    all_token_counts.append(chunk['token_count'])

                batch_chunks.extend(chunks)

                logger.debug(
                    f"  Section '{heading[:50]}...': "
                    f"{len(units)} units -> {len(chunks)} chunks"
                )

            except Exception as e:
                logger.error(
                    f"Failed to process section {section_id} '{heading}': {e}",
                    exc_info=True
                )
                raise CleanupError(
                    f"Failed to process section {section_id} '{heading}'"
                ) from e

        # Insert batch
        if batch_chunks:
            try:
                inserted = insert_parent_chunks_batch(batch_chunks)
                total_chunks_created += inserted
                logger.success(f"  Batch {batch_num}: Inserted {inserted} parent chunks")
            except Exception as e:
                logger.error(f"Failed to insert batch {batch_num}: {e}", exc_info=True)
                raise CleanupError(f"Failed to insert batch {batch_num}") from e

    # Auto-export to markdown for manual review (deliverable requirement)
    from src.config import EXPORTS_DIR
    export_dir = export_path or EXPORTS_DIR
    export_file = export_dir / "parent_chunks_all.md"
    try:
        export_parent_chunks_to_markdown(doc_id, export_file)
        logger.success(f"Exported parent chunks to {export_file}")
    except Exception as e:
        logger.warning(f"Failed to export parent chunks: {e}")

    # Compute statistics
    duration = time.time() - start_time

    stats = {
        'document_id': doc_id,
        'sections_processed': len(sections),
        'parent_chunks_created': total_chunks_created,
        'token_min': min(all_token_counts) if all_token_counts else 0,
        'token_max': max(all_token_counts) if all_token_counts else 0,
        'token_median': statistics.median(all_token_counts) if all_token_counts else 0,
        'token_mean': statistics.mean(all_token_counts) if all_token_counts else 0,
        'chunks_over_limit': sum(1 for t in all_token_counts if t > PARENT_TOKEN_HARD_MAX),
        'duration_seconds': duration,
    }

    # Log summary
    logger.info("=" * 80)
    logger.info("STEP 3 COMPLETE")
    logger.info("=" * 80)
    logger.success(f"Level-2 sections processed: {stats['sections_processed']}")
    logger.success(f"Parent chunks created: {stats['parent_chunks_created']}")
    logger.info(f"Token distribution:")
    logger.info(f"  Min: {stats['token_min']}")
    logger.info(f"  Max: {stats['token_max']}")
    logger.info(f"  Median: {stats['token_median']:.0f}")
    logger.info(f"  Mean: {stats['token_mean']:.1f}")

    if stats['chunks_over_limit'] > 0:
        logger.error(
            f"CHUNKS OVER {PARENT_TOKEN_HARD_MAX} TOKEN LIMIT: {stats['chunks_over_limit']}"
        )
    else:
        logger.success(f"All chunks within {PARENT_TOKEN_HARD_MAX} token limit")

    logger.info(f"Duration: {duration:.2f} seconds")
    logger.info("=" * 80)

    return stats


def main():
    """CLI entry point for Step 3."""
    parser = argparse.ArgumentParser(
        description="Step 3: Cleanup and Parent Chunk Construction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with auto-detected document ID
    python -m src.pipeline.step3_cleanup

    # Run with specific document ID
    python -m src.pipeline.step3_cleanup --doc-id 4e2ce587-fc2c-4f79-8f2f-8ac25d5252b0

    # Overwrite existing chunks and export
    python -m src.pipeline.step3_cleanup --overwrite --export data/exports/

    # Specify custom database path
    python -m src.pipeline.step3_cleanup --db data/ucg23_rag.db
        """
    )

    parser.add_argument(
        '--db',
        type=Path,
        help="Path to SQLite database (defaults to config)"
    )
    parser.add_argument(
        '--doc-id',
        type=str,
        help="Document ID (auto-detected if only one document exists)"
    )
    parser.add_argument(
        '--export',
        type=Path,
        help="Export parent chunks to this directory"
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help="Delete existing parent chunks and rebuild"
    )

    args = parser.parse_args()

    # Initialize logging
    setup_logger()

    try:
        stats = run(
            db_path=args.db,
            doc_id=args.doc_id,
            export_path=args.export,
            overwrite=args.overwrite,
        )
        logger.info("Step 3 completed successfully")
        sys.exit(0)

    except CleanupError as e:
        logger.error(f"Step 3 failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error in Step 3: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
