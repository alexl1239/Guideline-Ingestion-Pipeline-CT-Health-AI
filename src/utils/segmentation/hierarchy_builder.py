"""
Hierarchy Builder for Structural Segmentation

Constructs the section hierarchy (chapters → diseases → subsections) from
heading candidates and Table of Contents entries.

Key Functions:
- identify_chapters: Find chapter-level sections from ToC
- identify_diseases: Find disease/topic sections from ToC, matched by numbering
- identify_subsections: Find subsections within diseases
- build_heading_path: Construct full heading path strings
- assign_blocks_to_sections: Map blocks to sections by page/order
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from src.utils.logging_config import logger
from src.utils.segmentation.heading_patterns import (
    is_chapter_heading,
    is_standard_subsection,
)


def _get_chapter_number(numbering: Optional[str]) -> Optional[str]:
    """
    Extract the chapter number from a numbering string.

    Examples:
        "1" -> "1"
        "1.2" -> "1"
        "1.2.3" -> "1"
        "24.1.2" -> "24"
        None -> None
    """
    if not numbering:
        return None
    parts = numbering.split('.')
    return parts[0] if parts else None


def _get_disease_prefix(numbering: Optional[str]) -> Optional[str]:
    """
    Extract the disease prefix (first two parts) from a numbering string.

    Examples:
        "1.2" -> "1.2"
        "1.2.3" -> "1.2"
        "24.1.2.1" -> "24.1"
        None -> None
    """
    if not numbering:
        return None
    parts = numbering.split('.')
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return None


def identify_chapters(
    header_blocks: List[Dict[str, Any]],
    toc_entries: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Identify chapter-level sections (Level 1) from ToC.
    """
    chapters = []

    # Filter ToC entries for level 1 (chapters)
    toc_chapters = [e for e in toc_entries if e.get('level') == 1]

    for i, toc_entry in enumerate(toc_chapters):
        toc_heading = toc_entry['heading']
        toc_page = toc_entry.get('page')
        toc_numbering = toc_entry.get('numbering')

        if not toc_page:
            logger.warning(f"Skipping ToC chapter without page number: {toc_heading}")
            continue

        page_start = toc_page

        # Calculate page_end from next chapter's ToC page
        if i + 1 < len(toc_chapters):
            next_toc_page = toc_chapters[i + 1].get('page')
            page_end = (next_toc_page - 1) if next_toc_page else (page_start + 50)
        else:
            page_end = page_start + 100

        # Ensure page_end >= page_start
        if page_end < page_start:
            page_end = page_start

        # Format heading with numbering if available
        if toc_numbering:
            formatted_heading = f"{toc_numbering} {toc_heading}"
        else:
            formatted_heading = toc_heading

        chapters.append({
            'level': 1,
            'heading': formatted_heading,
            'page_start': page_start,
            'page_end': page_end,
            'order_index': len(chapters) + 1,
            'header_block_id': None,
            'numbering': toc_numbering,
        })

    # Fallback: if no ToC chapters found, look for chapter patterns directly
    if not chapters:
        logger.warning("No ToC chapters found, using pattern-based detection")
        used_block_ids: Set[int] = set()
        for block in header_blocks:
            if block['id'] not in used_block_ids and is_chapter_heading(block['text_content']):
                chapters.append({
                    'level': 1,
                    'heading': block['text_content'],
                    'page_start': block['page_number'],
                    'page_end': block['page_number'] + 50,
                    'order_index': len(chapters) + 1,
                    'header_block_id': block['id'],
                    'numbering': None,
                })
                used_block_ids.add(block['id'])

    logger.info(f"Identified {len(chapters)} chapters")
    return chapters


def identify_diseases_from_toc(
    toc_entries: List[Dict[str, Any]],
    chapters: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Identify disease/topic sections (Level 2) from ToC entries.

    Matches diseases to chapters by their numbering prefix, not by page range.
    For example, "1.3 POISONING" is matched to chapter "1" regardless of page number.
    """
    diseases = []

    # Create a lookup of chapters by their numbering
    chapter_by_number: Dict[str, Dict[str, Any]] = {}
    for chapter in chapters:
        chapter_num = _get_chapter_number(chapter.get('numbering'))
        if chapter_num:
            chapter_by_number[chapter_num] = chapter

    # Filter ToC entries for level 2 (diseases)
    toc_diseases = [e for e in toc_entries if e.get('level') == 2]

    for i, toc_entry in enumerate(toc_diseases):
        toc_heading = toc_entry['heading']
        toc_page = toc_entry.get('page')
        toc_numbering = toc_entry.get('numbering')

        if not toc_page:
            logger.warning(f"Skipping ToC disease without page number: {toc_heading}")
            continue

        # Find parent chapter by numbering prefix
        chapter_num = _get_chapter_number(toc_numbering)
        parent_chapter = chapter_by_number.get(chapter_num) if chapter_num else None

        if not parent_chapter:
            logger.warning(f"Could not find parent chapter for disease: {toc_numbering} {toc_heading}")
            continue

        page_start = toc_page

        # Calculate page_end from next disease's ToC page
        if i + 1 < len(toc_diseases):
            next_toc_page = toc_diseases[i + 1].get('page')
            page_end = (next_toc_page - 1) if next_toc_page else (page_start + 10)
        else:
            page_end = parent_chapter['page_end']

        # Ensure page_end >= page_start
        if page_end < page_start:
            page_end = page_start

        # Format heading with numbering
        if toc_numbering:
            formatted_heading = f"{toc_numbering} {toc_heading}"
        else:
            formatted_heading = toc_heading

        diseases.append({
            'level': 2,
            'heading': formatted_heading,
            'page_start': page_start,
            'page_end': page_end,
            'order_index': len(diseases) + 1,
            'header_block_id': None,
            'parent_chapter': parent_chapter,
            'numbering': toc_numbering,
        })

    logger.info(f"Identified {len(diseases)} diseases from ToC")
    return diseases


def identify_subsections_from_toc_and_headers(
    header_blocks: List[Dict[str, Any]],
    toc_entries: List[Dict[str, Any]],
    diseases: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Identify subsections (Level 3+) from ToC and header blocks.

    Matches subsections to diseases by their numbering prefix.
    Also identifies standard clinical subsections (Causes, Management, etc.)
    """
    subsections = []

    # Create lookup of diseases by their numbering prefix
    disease_by_prefix: Dict[str, Dict[str, Any]] = {}
    for disease in diseases:
        prefix = _get_disease_prefix(disease.get('numbering'))
        if prefix:
            disease_by_prefix[prefix] = disease

    # First, get numbered subsections from ToC (Level 3+)
    toc_subsections = [e for e in toc_entries if e.get('level', 0) >= 3]

    for i, toc_entry in enumerate(toc_subsections):
        toc_heading = toc_entry['heading']
        toc_page = toc_entry.get('page')
        toc_numbering = toc_entry.get('numbering')
        toc_level = toc_entry.get('level', 3)

        if not toc_page:
            continue

        # Find parent disease by numbering prefix
        disease_prefix = _get_disease_prefix(toc_numbering)
        parent_disease = disease_by_prefix.get(disease_prefix) if disease_prefix else None

        # Validate: if the page doesn't fall within the disease's chapter range,
        # the numbering might be wrong in the ToC (e.g., "1.1.1" on page 614)
        if parent_disease:
            parent_chapter = parent_disease.get('parent_chapter', {})
            if parent_chapter:
                chapter_start = parent_chapter.get('page_start', 0)
                chapter_end = parent_chapter.get('page_end', 9999)
                if not (chapter_start <= toc_page <= chapter_end):
                    # Numbering doesn't match page location - use page-based lookup instead
                    logger.debug(f"ToC numbering mismatch: {toc_numbering} {toc_heading} (page {toc_page}) doesn't match chapter range {chapter_start}-{chapter_end}")
                    parent_disease = None

        if not parent_disease:
            # Try to find by page range as fallback
            for disease in diseases:
                if disease['page_start'] <= toc_page <= disease['page_end']:
                    parent_disease = disease
                    break

        if not parent_disease:
            continue

        page_start = toc_page

        # Calculate page_end
        if i + 1 < len(toc_subsections):
            next_page = toc_subsections[i + 1].get('page')
            page_end = (next_page - 1) if next_page else page_start
        else:
            page_end = parent_disease['page_end']

        # Ensure page_end >= page_start
        if page_end < page_start:
            page_end = page_start

        # Format heading
        if toc_numbering:
            formatted_heading = f"{toc_numbering} {toc_heading}"
        else:
            formatted_heading = toc_heading

        subsections.append({
            'level': toc_level,
            'heading': formatted_heading,
            'page_start': page_start,
            'page_end': page_end,
            'order_index': len(subsections) + 1,
            'header_block_id': None,
            'parent_disease': parent_disease,
            'numbering': toc_numbering,
        })

    # Track pages already covered by ToC subsections
    toc_covered_pages: Set[Tuple[int, str]] = set()
    for sub in subsections:
        for page in range(sub['page_start'], sub['page_end'] + 1):
            toc_covered_pages.add((page, sub['heading']))

    # Now find standard clinical subsections from headers (Causes, Management, etc.)
    for disease in diseases:
        disease_headers = [
            h for h in header_blocks
            if disease['page_start'] <= h['page_number'] <= disease['page_end']
        ]

        for block in disease_headers:
            text = block['text_content']

            # Check for standard subsection
            is_standard, subsection_type = is_standard_subsection(text)
            if is_standard:
                # Check if this isn't already covered by a ToC subsection
                page = block['page_number']

                subsections.append({
                    'level': 3,
                    'heading': text,
                    'page_start': page,
                    'page_end': page,  # Will adjust later
                    'order_index': len(subsections) + 1,
                    'header_block_id': block['id'],
                    'parent_disease': disease,
                    'subsection_type': subsection_type,
                })

    # Sort subsections by page and adjust page_end
    subsections.sort(key=lambda s: (s['page_start'], s.get('level', 3)))

    for i, subsection in enumerate(subsections):
        if i + 1 < len(subsections):
            next_sub = subsections[i + 1]
            # Only adjust if same parent disease
            if subsection.get('parent_disease') == next_sub.get('parent_disease'):
                new_end = next_sub['page_start'] - 1
                if new_end >= subsection['page_start']:
                    subsection['page_end'] = new_end

        # Ensure page_end >= page_start
        if subsection['page_end'] < subsection['page_start']:
            subsection['page_end'] = subsection['page_start']

    logger.info(f"Identified {len(subsections)} subsections")
    return subsections


def build_heading_path(section: Dict[str, Any]) -> str:
    """
    Construct full heading path for a section.

    Builds path like: "Chapter > Disease > Subsection"
    """
    # Level 1 (Chapter) - no parent
    if section['level'] == 1:
        return section['heading']

    # Level 2 (Disease) - has chapter parent
    if section['level'] == 2:
        chapter = section.get('parent_chapter', {})
        if chapter:
            return f"{chapter['heading']} > {section['heading']}"
        return section['heading']

    # Level 3+ (Subsection) - has disease and chapter parents
    disease = section.get('parent_disease', {})
    if disease:
        chapter = disease.get('parent_chapter', {})
        if chapter:
            return f"{chapter['heading']} > {disease['heading']} > {section['heading']}"
        return f"{disease['heading']} > {section['heading']}"

    return section['heading']


def assign_blocks_to_sections(
    all_blocks: List[Dict[str, Any]],
    sections: List[Dict[str, Any]]
) -> Dict[int, List[int]]:
    """
    Map all content blocks to their parent sections.

    Assigns blocks based on page number and order. Excludes page_header
    and page_footer blocks.
    """
    mapping: Dict[int, List[int]] = {}

    # Sort sections by page_start and level (higher level = more specific)
    sorted_sections = sorted(sections, key=lambda s: (s['page_start'], -s['level']))

    # Build page-to-section mapping
    # For each page, store sections that cover it, preferring more specific (higher level)
    page_sections: Dict[int, List[Dict[str, Any]]] = {}
    for section in sorted_sections:
        for page in range(section['page_start'], section['page_end'] + 1):
            if page not in page_sections:
                page_sections[page] = []
            page_sections[page].append(section)

    orphaned_blocks = 0

    for block in all_blocks:
        # Skip page headers/footers
        if block.get('block_type') in ['page_header', 'page_footer']:
            continue

        page = block['page_number']

        # Find most specific section for this page
        assigned_section = None
        if page in page_sections:
            # Get the most specific (highest level) section for this page
            candidates = page_sections[page]
            if candidates:
                # Sort by level descending, then by page_start ascending
                candidates.sort(key=lambda s: (-s['level'], s['page_start']))
                assigned_section = candidates[0]

        if assigned_section:
            section_id = id(assigned_section)
            if section_id not in mapping:
                mapping[section_id] = []
            mapping[section_id].append(block['id'])
        else:
            orphaned_blocks += 1
            logger.debug(f"Orphaned block on page {page}: {block.get('block_type')}")

    logger.info(f"Assigned {sum(len(ids) for ids in mapping.values())} blocks to {len(mapping)} sections")
    if orphaned_blocks > 0:
        logger.warning(f"{orphaned_blocks} blocks could not be assigned to any section")

    return mapping


def build_complete_hierarchy(
    header_blocks: List[Dict[str, Any]],
    toc_entries: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Build complete section hierarchy from headers and ToC.

    Uses ToC entries as the primary source for chapters and diseases,
    matching by numbering prefix rather than page ranges.
    """
    all_sections = []
    global_order = 1

    # Step 1: Identify chapters from ToC
    chapters = identify_chapters(header_blocks, toc_entries)

    # Add chapters to all_sections
    for chapter in chapters:
        chapter['order_index'] = global_order
        chapter['heading_path'] = build_heading_path(chapter)
        all_sections.append(chapter)
        global_order += 1

    # Step 2: Identify diseases from ToC (matched by numbering, not page range)
    diseases = identify_diseases_from_toc(toc_entries, chapters)

    # Group diseases by parent chapter
    diseases_by_chapter: Dict[int, List[Dict[str, Any]]] = {}
    for disease in diseases:
        chapter_id = id(disease.get('parent_chapter'))
        if chapter_id not in diseases_by_chapter:
            diseases_by_chapter[chapter_id] = []
        diseases_by_chapter[chapter_id].append(disease)

    # Step 3: Identify subsections from ToC and headers
    subsections = identify_subsections_from_toc_and_headers(header_blocks, toc_entries, diseases)

    # Group subsections by parent disease
    subsections_by_disease: Dict[int, List[Dict[str, Any]]] = {}
    for subsection in subsections:
        disease_id = id(subsection.get('parent_disease'))
        if disease_id not in subsections_by_disease:
            subsections_by_disease[disease_id] = []
        subsections_by_disease[disease_id].append(subsection)

    # Build final ordered list: chapter -> its diseases -> each disease's subsections
    all_sections = []
    global_order = 1

    for chapter in chapters:
        chapter['order_index'] = global_order
        chapter['heading_path'] = build_heading_path(chapter)
        all_sections.append(chapter)
        global_order += 1

        # Add this chapter's diseases
        chapter_diseases = diseases_by_chapter.get(id(chapter), [])
        chapter_diseases.sort(key=lambda d: (d['page_start'], d.get('numbering', '')))

        for disease in chapter_diseases:
            disease['order_index'] = global_order
            disease['heading_path'] = build_heading_path(disease)
            all_sections.append(disease)
            global_order += 1

            # Add this disease's subsections
            disease_subsections = subsections_by_disease.get(id(disease), [])
            disease_subsections.sort(key=lambda s: (s['page_start'], s.get('level', 3)))

            for subsection in disease_subsections:
                subsection['order_index'] = global_order
                subsection['heading_path'] = build_heading_path(subsection)
                all_sections.append(subsection)
                global_order += 1

    logger.info(f"Built complete hierarchy: {len(all_sections)} total sections")
    logger.info(f"  Level 1 (Chapters): {len([s for s in all_sections if s['level'] == 1])}")
    logger.info(f"  Level 2 (Diseases): {len([s for s in all_sections if s['level'] == 2])}")
    logger.info(f"  Level 3+ (Subsections): {len([s for s in all_sections if s['level'] >= 3])}")

    return all_sections


__all__ = [
    'identify_chapters',
    'identify_diseases_from_toc',
    'identify_subsections_from_toc_and_headers',
    'build_heading_path',
    'assign_blocks_to_sections',
    'build_complete_hierarchy',
]
