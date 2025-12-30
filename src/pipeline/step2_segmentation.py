"""
STEP 2 — STRUCTURAL SEGMENTATION

Reconstructs logical hierarchy (Chapters → Diseases → Subsections) from parsed blocks
and Table of Contents data.

Process:
1. Load section headers and Docling JSON from database
2. Extract Table of Contents from Docling JSON
3. Build complete hierarchy using heading patterns and ToC matching
4. Insert sections into database (transaction per chapter)
5. Update raw_blocks.section_id for all blocks in each chapter
6. Export section tree to data/exports/section_tree.md for validation
7. Log statistics (chapter/disease/subsection counts)

Input: Populated raw_blocks table (from Step 1)
Output: Populated sections table with hierarchical structure

Transaction Boundary: Per chapter (as per CLAUDE.md)
"""

from typing import Dict, Any, List, Tuple
import sqlite3
from pathlib import Path

from src.utils.logging_config import logger
from src.config import EXPORTS_DIR
from src.database.operations import (
    get_registered_document,
    get_section_header_blocks,
    get_document_docling_json,
    insert_section,
    update_blocks_section_id,
)
from src.database import get_connection
from src.utils.segmentation import (
    extract_toc_from_docling,
    validate_toc_entries,
    get_toc_summary,
    build_complete_hierarchy,
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
        f.write("# UCG-23 Section Hierarchy\n\n")
        f.write(f"Total Sections: {len(sections)}\n\n")

        # Count by level
        level_counts = {}
        for section in sections:
            level = section['level']
            level_counts[level] = level_counts.get(level, 0) + 1

        f.write("## Statistics\n\n")
        f.write(f"- Level 1 (Chapters): {level_counts.get(1, 0)}\n")
        f.write(f"- Level 2 (Diseases/Topics): {level_counts.get(2, 0)}\n")
        f.write(f"- Level 3+ (Subsections): {sum(c for l, c in level_counts.items() if l >= 3)}\n\n")

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
            SELECT id, page_number, block_type
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

    # Get chapter page range for filtering descendants
    chapter_page_start = chapter['page_start']
    chapter_page_end = chapter['page_end']

    # Filter sections within this chapter
    chapter_sections = [
        s for s in all_sections
        if s['page_start'] >= chapter_page_start and s['page_start'] <= chapter_page_end
    ]

    # Sort by order_index to maintain hierarchy order
    chapter_sections.sort(key=lambda s: s['order_index'])

    # Insert all sections in this chapter
    for section in chapter_sections:
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
        temp_id = id(section)  # Python object ID used as temp key
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
    1. Load section headers and Docling JSON
    2. Extract ToC from Docling JSON
    3. Build complete hierarchy
    4. Insert sections into database (per-chapter transactions)
    5. Update raw_blocks.section_id
    6. Export section tree for validation
    7. Log statistics

    Raises:
        SegmentationError: If segmentation fails
    """
    logger.info("=" * 80)
    logger.info("STEP 2: STRUCTURAL SEGMENTATION")
    logger.info("=" * 80)

    # 1. Get registered document
    logger.info("Checking for registered document...")
    document_id = get_registered_document()

    if not document_id:
        logger.error("❌ No registered document found. Please run Step 0 first.")
        raise SegmentationError("No registered document found. Run Step 0 (registration) first.")

    logger.success(f"✓ Found registered document: {document_id}")

    # 2. Load section headers
    logger.info("Loading section header blocks...")
    try:
        header_blocks = get_section_header_blocks(document_id)

        if not header_blocks:
            logger.error("❌ No section headers found. Please run Step 1 first.")
            raise SegmentationError("No section headers found. Run Step 1 (parsing) first.")

        logger.success(f"✓ Loaded {len(header_blocks)} section headers")
    except Exception as e:
        logger.error(f"❌ Failed to load section headers: {e}")
        raise SegmentationError(f"Failed to load section headers: {e}") from e

    # 3. Extract Table of Contents
    logger.info("Extracting Table of Contents from Docling JSON...")
    try:
        docling_json = get_document_docling_json(document_id)

        if not docling_json:
            logger.error("❌ Docling JSON not found. Please run Step 1 first.")
            raise SegmentationError("Docling JSON not found. Run Step 1 (parsing) first.")

        toc_entries = extract_toc_from_docling(docling_json)

        if toc_entries:
            is_valid = validate_toc_entries(toc_entries)
            if is_valid:
                logger.success(f"✓ Extracted {len(toc_entries)} ToC entries")
                logger.info(get_toc_summary(toc_entries))
            else:
                logger.warning("⚠ ToC entries failed validation, using as-is")
        else:
            logger.warning("⚠ No ToC entries found, will use fallback detection")
    except Exception as e:
        logger.error(f"❌ Failed to extract ToC: {e}")
        raise SegmentationError(f"Failed to extract ToC: {e}") from e

    # 4. Build complete hierarchy
    logger.info("Building section hierarchy...")
    try:
        all_sections = build_complete_hierarchy(header_blocks, toc_entries)

        if not all_sections:
            logger.error("❌ No sections identified in hierarchy")
            raise SegmentationError("No sections identified in hierarchy")

        # Count by level
        level_counts = {}
        for section in all_sections:
            level = section['level']
            level_counts[level] = level_counts.get(level, 0) + 1

        logger.success(f"✓ Built hierarchy with {len(all_sections)} sections:")
        logger.info(f"  - Level 1 (Chapters): {level_counts.get(1, 0)}")
        logger.info(f"  - Level 2 (Diseases): {level_counts.get(2, 0)}")
        logger.info(f"  - Level 3+ (Subsections): {sum(c for l, c in level_counts.items() if l >= 3)}")
    except Exception as e:
        logger.error(f"❌ Failed to build hierarchy: {e}")
        raise SegmentationError(f"Failed to build hierarchy: {e}") from e

    # 5. Load all blocks for assignment
    logger.info("Loading raw blocks for section assignment...")
    try:
        all_blocks = _get_all_raw_blocks(document_id)
        logger.success(f"✓ Loaded {len(all_blocks)} raw blocks")
    except Exception as e:
        logger.error(f"❌ Failed to load raw blocks: {e}")
        raise SegmentationError(f"Failed to load raw blocks: {e}") from e

    # 6. Insert sections and update blocks (per-chapter transactions)
    logger.info("Inserting sections into database (per-chapter transactions)...")

    # Get all chapters
    chapters = [s for s in all_sections if s['level'] == 1]

    if not chapters:
        logger.error("❌ No chapters found in hierarchy")
        raise SegmentationError("No chapters found in hierarchy")

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

    # 7. Export section tree
    logger.info("Exporting section tree for validation...")
    try:
        section_tree_path = EXPORTS_DIR / "section_tree.md"
        _export_section_tree(all_sections, section_tree_path)
        logger.success(f"✓ Section tree exported to: {section_tree_path}")
    except Exception as e:
        logger.warning(f"⚠ Failed to export section tree: {e}")
        # Non-critical error, continue

    # 8. Log final statistics
    logger.info("=" * 80)
    logger.info("STEP 2 COMPLETE")
    logger.info("=" * 80)
    logger.success(
        f"✓ Successfully segmented {total_sections} sections "
        f"({level_counts.get(1, 0)} chapters, {level_counts.get(2, 0)} diseases, "
        f"{sum(c for l, c in level_counts.items() if l >= 3)} subsections)"
    )
    logger.success(f"✓ Assigned {total_blocks_updated} blocks to sections")
    logger.info(f"Section tree: {EXPORTS_DIR / 'section_tree.md'}")
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
