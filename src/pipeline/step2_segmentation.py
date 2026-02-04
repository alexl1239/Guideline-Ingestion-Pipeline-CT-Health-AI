"""
STEP 2 — STRUCTURAL SEGMENTATION

Reconstructs logical hierarchy (Chapters → Topics → Subsections) from Docling's
native layout analysis.

Document-agnostic: Works with any clinical guideline document structure.

Process:
1. Load Docling JSON from database
2. Extract section hierarchy using Docling's native level fields (no ToC parsing)
3. Insert sections into database (transaction per chapter)
4. Update raw_blocks.section_id for all blocks in each chapter
5. Export section tree to data/exports/section_tree.md for validation
6. Log statistics (chapter/topic/subsection counts)

Input: Populated raw_blocks table (from Step 1)
Output: Populated sections table with hierarchical structure

Transaction Boundary: Per chapter

Note: This uses Docling's native hierarchy detection, eliminating fragile ToC parsing.
"""

from typing import Dict, Any, List, Tuple
import sqlite3
from pathlib import Path

from src.utils.logging_config import logger
from src.config import EXPORTS_DIR
from src.database.operations import (
    get_registered_document,
    get_document_docling_json,
    insert_section,
    update_blocks_section_id,
)
from src.database import get_connection
from src.utils.segmentation.native_hierarchy import (
    extract_native_hierarchy,
    get_hierarchy_summary,
)
from src.utils.segmentation import (
    assign_blocks_to_sections,
)


class SegmentationError(Exception):
    """Raised when segmentation fails."""
    pass


def _export_section_tree(sections: List[Dict[str, Any]], output_path: Path) -> None:
    """
    Export section hierarchy as human-readable tree for validation.

    Args:
        sections: List of section dicts with level, heading, page_start, page_end
        output_path: Path to write section_tree.md

    Example output:
        Chapter 1: Emergencies (pages 10-50)
          1.1 Anaphylactic Shock (pages 15-20)
            Definition (page 16)
            Management (page 17)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Clinical Guideline Section Hierarchy\n\n")
        f.write(f"Total Sections: {len(sections)}\n\n")

        # Count by level
        level_counts = {}
        for section in sections:
            level = section['level']
            level_counts[level] = level_counts.get(level, 0) + 1

        f.write("## Statistics\n\n")
        f.write(f"- Level 1 (Chapters): {level_counts.get(1, 0)}\n")
        f.write(f"- Level 2 (Topics): {level_counts.get(2, 0)}\n")
        f.write(f"- Level 3 (Numbered subsections / Standard subsections under L2): {level_counts.get(3, 0)}\n")
        f.write(f"- Level 4 (Numbered sub-subsections / Standard subsections under L3): {level_counts.get(4, 0)}\n")
        f.write(f"- Level 5 (Standard subsections under L4): {level_counts.get(5, 0)}\n\n")

        f.write("## Hierarchy\n\n")

        # Write tree structure
        for section in sections:
            level = section['level']
            heading = section['heading']
            page_start = section['page_start']
            page_end = section['page_end']

            # Indent based on level (2 spaces per level, starting at level 1)
            indent = "  " * (level - 1)

            # Format page range
            if page_start == page_end:
                page_info = f"page {page_start}"
            else:
                page_info = f"pages {page_start}-{page_end}"

            f.write(f"{indent}{heading} ({page_info})\n")

    logger.info(f"Section tree exported to: {output_path}")


def _get_all_raw_blocks(document_id: str) -> List[Dict[str, Any]]:
    """
    Get all raw blocks for section assignment.

    Args:
        document_id: Document ID

    Returns:
        List of all raw blocks with id, page_number, block_type
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, page_number, block_type, text_content
            FROM raw_blocks
            WHERE document_id = ?
            ORDER BY page_number, id
        """, (document_id,))

        rows = cursor.fetchall()

        blocks = []
        for row in rows:
            blocks.append({
                'id': row[0],
                'page_number': row[1],
                'block_type': row[2],
                'text_content': row[3],
            })

        return blocks


def _insert_chapter_with_descendants(
    cursor: sqlite3.Cursor,
    document_id: str,
    chapter: Dict[str, Any],
    all_sections: List[Dict[str, Any]],
    all_blocks: List[Dict[str, Any]],
    section_id_mapping: Dict[int, int]
) -> Tuple[int, int, int]:
    """
    Insert chapter and all descendant sections in a single transaction.

    Args:
        cursor: Database cursor (within transaction)
        document_id: Document ID
        chapter: Chapter section dict
        all_sections: All sections in hierarchy
        all_blocks: All raw blocks for section assignment
        section_id_mapping: Maps temp section ID to database section ID

    Returns:
        Tuple of (sections_inserted, blocks_updated, orphaned_blocks)
    """
    sections_inserted = 0
    blocks_updated = 0
    orphaned_blocks = 0

    # Get chapter page range for block assignment
    chapter_page_start = chapter['page_start']
    chapter_page_end = chapter['page_end']

    # Get chapter's order index range to find descendants
    chapter_order_idx = chapter['order_index']

    # Find the next chapter (level 1) to determine where descendants end
    next_chapter_idx = None
    for s in all_sections:
        if s['level'] == 1 and s['order_index'] > chapter_order_idx:
            next_chapter_idx = s['order_index']
            break

    # Filter sections by hierarchy (order_index), NOT by page range
    # This handles cases where subsections appear outside the chapter's page bounds
    if next_chapter_idx:
        chapter_sections = [
            s for s in all_sections
            if chapter_order_idx <= s['order_index'] < next_chapter_idx
        ]
    else:
        # Last chapter: include all remaining sections
        chapter_sections = [
            s for s in all_sections
            if s['order_index'] >= chapter_order_idx
        ]

    # Already sorted by order_index from hierarchy extraction

    # Insert all sections in this chapter (skip if already inserted)
    for section in chapter_sections:
        temp_id = id(section)  # Python object ID used as temp key

        # Skip if already inserted (prevents duplicates on boundary pages)
        if temp_id in section_id_mapping:
            continue

        section_id = insert_section(
            cursor=cursor,
            document_id=document_id,
            level=section['level'],
            heading=section['heading'],
            heading_path=section['heading_path'],
            order_index=section['order_index'],
            page_start=section['page_start'],
            page_end=section['page_end'],
            metadata=section.get('metadata')
        )

        # Map temporary ID to database ID
        section_id_mapping[temp_id] = section_id

        sections_inserted += 1

    # Assign blocks to sections in this chapter
    blocks_in_chapter = [
        b for b in all_blocks
        if chapter_page_start <= b['page_number'] <= chapter_page_end
    ]

    # Build mapping of temp_section_id -> block_ids
    block_assignments = assign_blocks_to_sections(blocks_in_chapter, chapter_sections)

    # Update raw_blocks.section_id using database IDs
    for temp_section_id, block_ids in block_assignments.items():
        if temp_section_id in section_id_mapping:
            db_section_id = section_id_mapping[temp_section_id]
            updated = update_blocks_section_id(cursor, db_section_id, block_ids)
            blocks_updated += updated
        else:
            logger.warning(f"Section ID mapping not found for temp_id: {temp_section_id}")
            orphaned_blocks += len(block_ids)

    return sections_inserted, blocks_updated, orphaned_blocks


def run() -> None:
    """
    Execute Step 2: Structural Segmentation.

    Process:
    1. Load Docling JSON from database
    2. Extract native hierarchy from Docling's layout analysis
    3. Insert sections into database (per-chapter transactions)
    4. Update raw_blocks.section_id
    5. Export section tree for validation
    6. Log statistics

    Raises:
        SegmentationError: If segmentation fails
    """
    logger.info("=" * 80)
    logger.info("STEP 2: STRUCTURAL SEGMENTATION (Native Hierarchy)")
    logger.info("=" * 80)

    # 1. Get registered document
    logger.info("Checking for registered document...")
    document_id = get_registered_document()

    if not document_id:
        logger.error("❌ No registered document found. Please run Step 0 first.")
        raise SegmentationError("No registered document found. Run Step 0 (registration) first.")

    logger.success(f"✓ Found registered document: {document_id}")

    # 2. Load Docling JSON
    logger.info("Loading Docling JSON from database...")
    try:
        docling_json = get_document_docling_json(document_id)

        if not docling_json:
            logger.error("❌ Docling JSON not found. Please run Step 1 first.")
            raise SegmentationError("Docling JSON not found. Run Step 1 (parsing) first.")

        logger.success("✓ Loaded Docling JSON")

        # Display VLM settings if available
        pipeline_meta = docling_json.get('pipeline_metadata', {})
        if pipeline_meta:
            vlm_enabled = pipeline_meta.get('vlm_enabled', False)
            table_mode = pipeline_meta.get('table_mode', 'unknown')
            parsed_at = pipeline_meta.get('parsed_at', 'unknown')

            if vlm_enabled:
                logger.info(f"📊 VLM was ENABLED during parsing (table mode: {table_mode})")
            else:
                logger.info(f"📊 VLM was DISABLED during parsing (default mode)")
            logger.info(f"   Parsed at: {parsed_at}")
        else:
            logger.warning("⚠ No pipeline metadata found (parsed before VLM tracking)")

    except Exception as e:
        logger.error(f"❌ Failed to load Docling JSON: {e}")
        raise SegmentationError(f"Failed to load Docling JSON: {e}") from e

    # 3. Extract native hierarchy from Docling
    logger.info("Extracting native hierarchy from Docling layout analysis...")
    try:
        all_sections = extract_native_hierarchy(docling_json)

        if not all_sections:
            logger.error("❌ No sections identified in hierarchy")
            raise SegmentationError("No sections identified in hierarchy")

        # Count by level
        level_counts = {}
        for section in all_sections:
            level = section['level']
            level_counts[level] = level_counts.get(level, 0) + 1

        logger.success(f"✓ Extracted hierarchy with {len(all_sections)} sections:")
        logger.info(f"  - Level 1 (Chapters): {level_counts.get(1, 0)}")
        logger.info(f"  - Level 2 (Topics): {level_counts.get(2, 0)}")
        logger.info(f"  - Level 3+ (Subsections): {sum(c for l, c in level_counts.items() if l >= 3)}")

        # Show hierarchy summary
        logger.info("\n" + get_hierarchy_summary(all_sections))

    except Exception as e:
        logger.error(f"❌ Failed to extract native hierarchy: {e}")
        raise SegmentationError(f"Failed to extract native hierarchy: {e}") from e

    # 4. Load all blocks for assignment
    logger.info("Loading raw blocks for section assignment...")
    try:
        all_blocks = _get_all_raw_blocks(document_id)
        logger.success(f"✓ Loaded {len(all_blocks)} raw blocks")
    except Exception as e:
        logger.error(f"❌ Failed to load raw blocks: {e}")
        raise SegmentationError(f"Failed to load raw blocks: {e}") from e

    # 5. Insert sections and update blocks (per-chapter transactions)
    logger.info("Inserting sections into database (per-chapter transactions)...")

    # Get all chapters
    chapters = [s for s in all_sections if s['level'] == 1]

    if not chapters:
        logger.error("❌ No chapters found in hierarchy")
        raise SegmentationError("No chapters found in hierarchy")

    # Clear existing sections for this document before inserting new ones
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM sections WHERE document_id = ?",
            (document_id,)
        )
        # Also reset section_id on raw_blocks
        cursor.execute(
            "UPDATE raw_blocks SET section_id = NULL WHERE document_id = ?",
            (document_id,)
        )
        conn.commit()
        logger.info(f"Cleared existing sections for document {document_id}")

    # Track overall statistics
    total_sections = 0
    total_blocks_updated = 0
    total_orphaned = 0
    section_id_mapping = {}  # Maps temp section ID to database section ID

    with get_connection() as conn:
        for i, chapter in enumerate(chapters, 1):
            chapter_heading = chapter['heading']
            logger.info(f"Processing chapter {i}/{len(chapters)}: {chapter_heading}")

            cursor = conn.cursor()

            try:
                # Begin transaction
                cursor.execute("BEGIN TRANSACTION")

                # Insert chapter and descendants
                sections_inserted, blocks_updated, orphaned = _insert_chapter_with_descendants(
                    cursor=cursor,
                    document_id=document_id,
                    chapter=chapter,
                    all_sections=all_sections,
                    all_blocks=all_blocks,
                    section_id_mapping=section_id_mapping
                )

                # Commit transaction
                conn.commit()

                # Update statistics
                total_sections += sections_inserted
                total_blocks_updated += blocks_updated
                total_orphaned += orphaned

                logger.success(
                    f"  ✓ Chapter {i}/{len(chapters)}: "
                    f"{sections_inserted} sections, {blocks_updated} blocks assigned"
                )

                if orphaned > 0:
                    logger.warning(f"  ⚠ {orphaned} blocks could not be assigned")

            except Exception as e:
                # Rollback on error
                conn.rollback()
                logger.error(f"  ❌ Failed to process chapter '{chapter_heading}': {e}")
                raise SegmentationError(f"Failed to process chapter '{chapter_heading}': {e}") from e

    logger.success(
        f"✓ Inserted {total_sections} sections and updated {total_blocks_updated} blocks"
    )

    if total_orphaned > 0:
        logger.warning(f"⚠ {total_orphaned} blocks could not be assigned to any section")

    # 6. Export section tree
    logger.info("Exporting section tree for validation...")
    try:
        section_tree_path = EXPORTS_DIR / "section_tree.md"
        _export_section_tree(all_sections, section_tree_path)
        logger.success(f"✓ Section tree exported to: {section_tree_path}")
    except Exception as e:
        logger.warning(f"⚠ Failed to export section tree: {e}")
        # Non-critical error, continue

    # 7. Log final statistics
    logger.info("=" * 80)
    logger.info("STEP 2 COMPLETE (Native Hierarchy)")
    logger.info("=" * 80)
    logger.success(
        f"✓ Successfully segmented {total_sections} sections using Docling's native layout analysis"
    )
    logger.info(
        f"  - {level_counts.get(1, 0)} chapters, {level_counts.get(2, 0)} topics, "
        f"{sum(c for l, c in level_counts.items() if l >= 3)} subsections"
    )
    logger.success(f"✓ Assigned {total_blocks_updated} blocks to sections")
    logger.info(f"Section tree: {EXPORTS_DIR / 'section_tree.md'}")
    logger.info("\nNote: This implementation uses Docling's native hierarchy detection,")
    logger.info("eliminating fragile ToC parsing and page offset calculations.")
    logger.info("")


if __name__ == "__main__":
    # Initialize logging when run directly
    from src.utils.logging_config import setup_logger
    setup_logger()

    try:
        run()
        logger.info("✓ Step 2 completed successfully")
    except Exception as e:
        logger.error(f"❌ Step 2 failed: {e}")
        exit(1)
