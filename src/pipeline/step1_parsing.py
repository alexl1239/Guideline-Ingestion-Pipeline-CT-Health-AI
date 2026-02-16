"""
STEP 1 — PARSING

Parses clinical guideline PDFs using Docling and inserts parsed blocks into raw_blocks table.

Document-agnostic: Works with any clinical guideline PDF registered in Step 0.

Process:
1. Load registered document from database
2. Parse PDF using Docling → get full DoclingDocument JSON
3. Update documents.docling_json with full Docling output
4. Iterate through Docling elements and map to raw_blocks schema
5. Batch insert into raw_blocks (100 blocks per transaction)
6. Log statistics (counts by block_type, pages covered)

Input: Registered document in database (from Step 0)
Output: Populated raw_blocks table with Docling native labels
"""

from src.utils.logging_config import logger
from src.config import SOURCE_PDF_PATH, PARSING_BATCH_SIZE
from src.parsers.docling_parser import DoclingParser
from src.database.operations import (
    get_registered_document,
    update_docling_json,
    batch_insert_raw_blocks,
    check_blocks_exist,
    collect_block_statistics,
    log_block_statistics,
)
from src.utils.parsing.docling_mapper import extract_blocks_from_json


class ParsingError(Exception):
    """Raised when parsing fails."""
    pass


def run() -> None:
    """
    Execute Step 1: Parsing.

    Process:
    1. Get registered document from database
    2. Parse PDF using Docling
    3. Update documents.docling_json
    4. Extract blocks from Docling JSON
    5. Batch insert into raw_blocks
    6. Collect and log statistics

    Raises:
        ParsingError: If parsing fails
    """
    logger.info("=" * 80)
    logger.info("STEP 1: PARSING")
    logger.info("=" * 80)

    # 1. Get registered document
    logger.info("Checking for registered document...")
    document_id = get_registered_document()

    if not document_id:
        logger.error("❌ No registered document found. Please run Step 0 first.")
        raise ParsingError("No registered document found. Run Step 0 (registration) first.")

    logger.success(f"✓ Found registered document: {document_id}")

    # Check if already parsed (idempotency)
    existing_count = check_blocks_exist(document_id)
    if existing_count > 0:
        logger.warning(f"⚠ raw_blocks already contains {existing_count} blocks for this document")
        logger.warning("Skipping parsing (idempotent)")
        logger.info("=" * 80)
        return

    # 2. Parse PDF using Docling
    if not SOURCE_PDF_PATH.exists():
        logger.error(f"❌ PDF not found: {SOURCE_PDF_PATH}")
        raise ParsingError(f"PDF not found at {SOURCE_PDF_PATH}")

    logger.info(f"Parsing PDF: {SOURCE_PDF_PATH.name}")

    try:
        parser = DoclingParser()
        parse_result = parser.parse(SOURCE_PDF_PATH)
        logger.success(f"✓ PDF parsed successfully: {parse_result.num_pages} pages")
    except Exception as e:
        logger.error(f"❌ Docling parsing failed: {e}")
        raise ParsingError(f"Docling parsing failed: {e}") from e

    # 3. Update documents.docling_json
    try:
        update_docling_json(document_id, parse_result.doc_json)
    except Exception as e:
        logger.error(f"❌ Failed to update docling_json: {e}")
        raise ParsingError(f"Failed to update docling_json: {e}") from e

    # 4. Extract blocks from Docling JSON
    logger.info("Extracting blocks from Docling output...")
    try:
        blocks = extract_blocks_from_json(parse_result.doc_json, document_id)

        if not blocks:
            logger.error("❌ No blocks extracted from Docling output")
            raise ParsingError("No blocks extracted from Docling output")

        logger.success(f"✓ Extracted {len(blocks)} blocks")
    except Exception as e:
        logger.error(f"❌ Failed to extract blocks: {e}")
        raise ParsingError(f"Failed to extract blocks: {e}") from e

    # 5. Batch insert into raw_blocks
    try:
        total_inserted, total_failed = batch_insert_raw_blocks(blocks, batch_size=PARSING_BATCH_SIZE)

        if total_failed > 0:
            logger.warning(f"⚠ {total_failed} blocks failed to insert")

        if total_inserted == 0:
            logger.error("❌ No blocks were inserted")
            raise ParsingError("No blocks were inserted")

    except Exception as e:
        logger.error(f"❌ Batch insertion failed: {e}")
        raise ParsingError(f"Batch insertion failed: {e}") from e

    # 6. Collect and log statistics
    logger.info("Collecting parsing statistics...")
    stats = collect_block_statistics(document_id)
    log_block_statistics(stats)

    logger.info("=" * 80)
    logger.info("STEP 1 COMPLETE")
    logger.info("=" * 80)
    logger.success(
        f"✓ Successfully parsed {stats.get('total_blocks', 0):,} blocks "
        f"from {stats.get('page_count', 0)} pages"
    )
    logger.info("")


if __name__ == "__main__":
    # Initialize logging when run directly
    from src.utils.logging_config import setup_logger
    setup_logger()

    try:
        run()
        logger.info("✓ Step 1 completed successfully")
    except Exception as e:
        logger.error(f"❌ Step 1 failed: {e}")
        exit(1)
