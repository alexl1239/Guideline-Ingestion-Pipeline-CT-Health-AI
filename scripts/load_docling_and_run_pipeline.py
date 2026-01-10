#!/usr/bin/env python3
"""
Load Pre-parsed Docling Output and Run Pipeline Steps

This script:
1. Loads existing Docling JSON from data/docling_outputs/ucg23_docling.json
2. Populates raw_blocks table (Step 1)
3. Runs structural segmentation (Step 2)
4. Runs cleanup and parent chunk formation (Step 3)

This is a convenience script to avoid re-parsing the PDF when Docling output already exists.
"""

import json
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import DATABASE_PATH
from src.database.connections import get_connection
from src.utils.logging_config import setup_logger, logger
from src.utils.parsing.docling_mapper import extract_blocks_from_json


DOCLING_JSON_PATH = project_root / "data" / "docling_outputs" / "ucg23_docling.json"
OUTPUT_DIR = project_root / "scripts" / "inspect_database" / "output"


def get_document_id():
    """Get the registered document ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM documents LIMIT 1")
        row = cursor.fetchone()
        if row:
            return row[0], row[1]
        return None, None


def check_raw_blocks_exist(doc_id: str) -> int:
    """Check if raw_blocks already exist for document."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM raw_blocks WHERE document_id = ?", (doc_id,))
        return cursor.fetchone()[0]


def load_docling_json():
    """Load Docling JSON from file."""
    logger.info(f"Loading Docling JSON from {DOCLING_JSON_PATH}")

    if not DOCLING_JSON_PATH.exists():
        raise FileNotFoundError(f"Docling JSON not found: {DOCLING_JSON_PATH}")

    with open(DOCLING_JSON_PATH, 'r', encoding='utf-8') as f:
        doc_json = json.load(f)

    logger.success(f"Loaded Docling JSON ({DOCLING_JSON_PATH.stat().st_size / 1024 / 1024:.1f} MB)")
    return doc_json


def populate_raw_blocks(doc_id: str, doc_json: dict):
    """Populate raw_blocks table from Docling JSON."""
    logger.info("Extracting blocks from Docling JSON...")

    # Extract blocks
    blocks = extract_blocks_from_json(doc_json, doc_id)

    if not blocks:
        raise ValueError("No blocks extracted from Docling JSON")

    logger.info(f"Inserting {len(blocks)} blocks into raw_blocks...")

    # Batch insert
    batch_size = 100
    inserted = 0

    with get_connection() as conn:
        cursor = conn.cursor()

        for i in range(0, len(blocks), batch_size):
            batch = blocks[i:i + batch_size]

            for block in batch:
                cursor.execute("""
                    INSERT INTO raw_blocks (
                        document_id, block_type, text_content, markdown_content,
                        page_number, page_range, docling_level, bbox,
                        is_continuation, element_id, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
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
                ))

            inserted += len(batch)
            if inserted % 1000 == 0:
                logger.info(f"  Inserted {inserted}/{len(blocks)} blocks...")

        conn.commit()

    logger.success(f"Inserted {inserted} raw_blocks")
    return inserted


def update_docling_json_in_db(doc_id: str, doc_json: dict):
    """Update documents.docling_json with full output."""
    logger.info("Updating documents.docling_json...")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE documents SET docling_json = ? WHERE id = ?",
            (json.dumps(doc_json), doc_id)
        )
        conn.commit()

    logger.success("Updated docling_json in documents table")


def run_step2_segmentation(doc_id: str):
    """Run Step 2: Structural Segmentation."""
    logger.info("=" * 60)
    logger.info("STEP 2: STRUCTURAL SEGMENTATION")
    logger.info("=" * 60)

    # Import and run Step 2
    from src.pipeline.step2_segmentation import run
    run()


def run_step3_cleanup(doc_id: str):
    """Run Step 3: Cleanup and Parent Chunk Formation."""
    logger.info("=" * 60)
    logger.info("STEP 3: CLEANUP AND PARENT CHUNK FORMATION")
    logger.info("=" * 60)

    from src.pipeline.step3_cleanup import run
    stats = run(doc_id=doc_id, overwrite=True)
    return stats


def write_diagnostic_report(doc_id: str, stats: dict):
    """Write diagnostic report to output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        cursor = conn.cursor()

        # Get counts
        cursor.execute("SELECT COUNT(*) FROM raw_blocks WHERE document_id = ?", (doc_id,))
        raw_blocks_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM sections WHERE document_id = ?", (doc_id,))
        sections_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM parent_chunks pc
            JOIN sections s ON pc.section_id = s.id
            WHERE s.document_id = ?
        """, (doc_id,))
        parent_chunks_count = cursor.fetchone()[0]

        # Get sections by level
        cursor.execute("""
            SELECT level, COUNT(*) FROM sections
            WHERE document_id = ?
            GROUP BY level ORDER BY level
        """, (doc_id,))
        sections_by_level = cursor.fetchall()

    report = {
        'document_id': doc_id,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'raw_blocks_count': raw_blocks_count,
        'sections_count': sections_count,
        'sections_by_level': {f"level_{row[0]}": row[1] for row in sections_by_level},
        'parent_chunks_count': parent_chunks_count,
        'step3_stats': stats,
    }

    report_path = OUTPUT_DIR / "pipeline_diagnostic_report.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    logger.info(f"Wrote diagnostic report to {report_path}")
    return report


def main():
    setup_logger()
    start_time = time.time()

    logger.info("=" * 80)
    logger.info("LOADING DOCLING OUTPUT AND RUNNING PIPELINE")
    logger.info("=" * 80)

    # 1. Get document ID
    doc_id, doc_title = get_document_id()
    if not doc_id:
        logger.error("No document registered. Run Step 0 first.")
        return 1

    logger.info(f"Document: {doc_title} ({doc_id})")

    # 2. Check if raw_blocks already exist
    existing_blocks = check_raw_blocks_exist(doc_id)
    if existing_blocks > 0:
        logger.warning(f"raw_blocks already has {existing_blocks} blocks")
        logger.info("Skipping Step 1 (loading Docling)")
    else:
        # Load and populate
        doc_json = load_docling_json()
        update_docling_json_in_db(doc_id, doc_json)
        populate_raw_blocks(doc_id, doc_json)

    # 3. Check if sections exist
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sections WHERE document_id = ?", (doc_id,))
        sections_count = cursor.fetchone()[0]

    if sections_count == 0:
        logger.info("sections table is empty - running Step 2")
        run_step2_segmentation(doc_id)
    else:
        logger.info(f"sections already has {sections_count} rows")

    # 4. Run Step 3 (cleanup and parent chunks)
    stats = run_step3_cleanup(doc_id)

    # 5. Write diagnostic report
    report = write_diagnostic_report(doc_id, stats)

    # 6. Summary
    duration = time.time() - start_time
    logger.info("=" * 80)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Document ID: {doc_id}")
    logger.info(f"Raw blocks: {report['raw_blocks_count']:,}")
    logger.info(f"Sections: {report['sections_count']:,}")
    logger.info(f"Parent chunks: {report['parent_chunks_count']:,}")
    logger.info(f"Duration: {duration:.1f} seconds")

    if report['parent_chunks_count'] == 0:
        logger.error("FAILURE: No parent chunks created!")
        return 1

    logger.success("SUCCESS: Pipeline completed with parent chunks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
