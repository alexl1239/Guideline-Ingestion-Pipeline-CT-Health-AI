"""
STEP 3 — TABLE LINEARIZATION

Converts each table raw block into natural-language Markdown via the
OpenAI chat API and stores the result in raw_blocks.text_content.

Runs BEFORE Step 4 so that the linearized prose is naturally picked up by
clean_block() during parent chunk construction. Token counts in
parent_chunks therefore reflect the final content from the start — no
in-place patching, no [TABLE] markers.

Process:
1. Load all table raw blocks for the document (with section heading_path)
2. Skip blocks already linearized unless --overwrite
3. For each block: preprocess markdown → LLM linearize → collect
4. Write results to raw_blocks.text_content in batches
5. Report stats: processed, skipped, failed, duration

Document-agnostic: Works with any clinical guideline document.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.config import (
    DATABASE_PATH,
    TABLE_BATCH_SIZE,
    TABLE_LLM_MODEL,
)
from src.utils.tables import (
    get_table_blocks_for_document,
    batch_update_raw_blocks_text_content,
    get_document_id_for_tables,
    normalize_table_markdown,
    linearize_table,
)
from src.utils.logging_config import logger, setup_logger


class TableLinearizationError(Exception):
    """Raised when table linearization fails for unrecoverable reasons."""
    pass


def _has_linearization(block: Dict[str, Any]) -> bool:
    """Return True if the block already has a non-empty text_content."""
    tc = block.get('text_content')
    return bool(tc and tc.strip())


def run(
    db_path: Optional[Path] = None,
    doc_id: Optional[str] = None,
    overwrite: bool = False,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Execute Step 3: Table Linearization.

    Args:
        db_path: Path to database (defaults to config)
        doc_id: Document ID (auto-detected if not provided)
        overwrite: Re-linearize tables that already have text_content
        limit: Process at most N table blocks (useful for smoke tests)
        dry_run: Skip the LLM call and DB write; just report what would happen

    Returns:
        Dict with statistics:
            - document_id, total_tables, processed, skipped, failed,
              duration_seconds, model
    """
    db_path = db_path or DATABASE_PATH
    start_time = time.time()

    logger.info("=" * 80)
    logger.info("STEP 3: TABLE LINEARIZATION")
    logger.info("=" * 80)
    logger.info(f"Model: {TABLE_LLM_MODEL}  |  dry_run={dry_run}  |  overwrite={overwrite}")

    if doc_id is None:
        doc_id = get_document_id_for_tables(db_path)
        if doc_id is None:
            raise TableLinearizationError("Could not determine document ID")

    logger.info("Loading table blocks...")
    blocks = get_table_blocks_for_document(doc_id)
    total = len(blocks)
    logger.success(f"Found {total} table blocks")

    if total == 0:
        logger.warning("No table blocks to linearize — nothing to do")
        return {
            'document_id': doc_id,
            'total_tables': 0,
            'processed': 0,
            'skipped': 0,
            'failed': 0,
            'duration_seconds': time.time() - start_time,
            'model': TABLE_LLM_MODEL,
        }

    # Filter
    todo: List[Dict[str, Any]] = []
    skipped = 0
    for b in blocks:
        if _has_linearization(b) and not overwrite:
            skipped += 1
            continue
        todo.append(b)

    if limit is not None:
        todo = todo[:limit]
        logger.info(f"--limit applied: processing {len(todo)} blocks")

    logger.info(
        f"To process: {len(todo)}  |  Already linearized (skipped): {skipped}"
    )

    pending_updates: List[Dict[str, Any]] = []
    processed = 0
    failed = 0

    for idx, block in enumerate(todo, start=1):
        block_id = block['id']
        page = block['page_number']
        heading_path = block.get('heading_path')
        raw_md = block.get('markdown_content') or ''

        if not raw_md.strip():
            logger.warning(f"  [{idx}/{len(todo)}] Block {block_id} (p.{page}): empty markdown — skipping")
            failed += 1
            continue

        # Preprocess markdown (decode entities, fix headers, etc.)
        cleaned_md = normalize_table_markdown(raw_md)

        logger.info(
            f"  [{idx}/{len(todo)}] Block {block_id} (p.{page}, "
            f"{len(cleaned_md)} chars) → '{(heading_path or '')[:60]}'"
        )

        if dry_run:
            processed += 1
            continue

        try:
            prose = linearize_table(cleaned_md, heading_path=heading_path)
            pending_updates.append({'id': block_id, 'text_content': prose})
            processed += 1
            logger.debug(
                f"    ✓ Linearized to {len(prose)} chars: {prose[:80]}..."
            )

        except Exception as e:
            failed += 1
            logger.error(
                f"    ✗ Linearization failed for block {block_id}: "
                f"{type(e).__name__}: {e}"
            )

        # Flush batch
        if len(pending_updates) >= TABLE_BATCH_SIZE:
            try:
                batch_update_raw_blocks_text_content(pending_updates)
                logger.success(f"  Flushed batch of {len(pending_updates)} updates")
            except Exception as e:
                logger.error(f"  Batch DB update failed: {e}")
                failed += len(pending_updates)
                processed -= len(pending_updates)
            pending_updates = []

    # Final flush
    if pending_updates and not dry_run:
        try:
            batch_update_raw_blocks_text_content(pending_updates)
            logger.success(f"  Flushed final batch of {len(pending_updates)} updates")
        except Exception as e:
            logger.error(f"  Final batch DB update failed: {e}")
            failed += len(pending_updates)
            processed -= len(pending_updates)

    duration = time.time() - start_time

    stats = {
        'document_id': doc_id,
        'total_tables': total,
        'processed': processed,
        'skipped': skipped,
        'failed': failed,
        'duration_seconds': duration,
        'model': TABLE_LLM_MODEL,
    }

    logger.info("=" * 80)
    logger.info("STEP 3 COMPLETE")
    logger.info("=" * 80)
    logger.success(f"Total tables: {total}")
    logger.success(f"Processed:    {processed}")
    logger.info(f"Skipped:      {skipped}")
    if failed > 0:
        logger.error(f"Failed:       {failed}")
    else:
        logger.success(f"Failed:       0")
    logger.info(f"Duration:     {duration:.2f}s")
    logger.info("=" * 80)

    return stats


def main():
    """CLI entry point for Step 3."""
    parser = argparse.ArgumentParser(
        description="Step 3: Table Linearization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run on the active document
    python -m src.pipeline.step3_tables

    # Smoke test: process just 3 tables, no DB writes
    python -m src.pipeline.step3_tables --limit 3 --dry-run

    # Re-linearize everything (e.g., after prompt change)
    python -m src.pipeline.step3_tables --overwrite
        """
    )
    parser.add_argument('--db', type=Path, help="Database path override")
    parser.add_argument('--doc-id', type=str, help="Document ID (auto-detected if single doc)")
    parser.add_argument(
        '--overwrite', action='store_true',
        help="Re-linearize tables that already have text_content"
    )
    parser.add_argument(
        '--limit', type=int,
        help="Process at most N table blocks (smoke test)"
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help="Skip LLM calls and DB writes; report what would happen"
    )

    args = parser.parse_args()
    setup_logger()

    try:
        run(
            db_path=args.db,
            doc_id=args.doc_id,
            overwrite=args.overwrite,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        logger.info("Step 3 completed successfully")
        sys.exit(0)
    except TableLinearizationError as e:
        logger.error(f"Step 3 failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error in Step 3: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
