"""
Hierarchy Builder for Structural Segmentation

Constructs the section hierarchy (chapters → diseases → subsections) from
heading candidates and Table of Contents entries.

Key Functions:
- identify_chapters: Find chapter-level sections
- identify_diseases: Find disease/topic sections within chapters
- identify_subsections: Find subsections within diseases
- build_heading_path: Construct full heading path strings
- assign_blocks_to_sections: Map blocks to sections by page/order
"""

from typing import List, Dict, Any, Optional, Set
from src.utils.logging_config import logger
from src.utils.segmentation.heading_patterns import (
    extract_numbered_heading,
    infer_level_from_numbering,
    is_chapter_heading,
    is_standard_subsection,
    score_heading_candidate,
)


def identify_chapters(
    header_blocks: List[Dict[str, Any]],
    toc_entries: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Identify chapter-level sections (Level 1).

    Uses ToC entries and heading patterns to find chapters. Matches ToC
    entries with header blocks using page proximity and text similarity.

    Args:
        header_blocks: List of section header blocks from raw_blocks
        toc_entries: List of ToC entries from extract_toc_from_docling

    Returns:
        List of chapter section dicts with:
            - level: 1
            - heading: Chapter heading text
            - page_start: First page of chapter
            - page_end: Last page (estimated)
            - order_index: Sequential order
            - header_block_id: ID of the header block

    Example:
        >>> chapters = identify_chapters(headers, toc)
        >>> for ch in chapters:
        ...     print(f"Chapter: {ch['heading']} (pages {ch['page_start']}-{ch['page_end']})")
    """
    chapters = []

    # Filter ToC entries for level 1 (chapters)
    toc_chapters = [e for e in toc_entries if e.get('level') == 1]

    # Track used header blocks to avoid duplicates
    used_block_ids: Set[int] = set()

    for i, toc_entry in enumerate(toc_chapters):
        toc_heading = toc_entry['heading']
        toc_page = toc_entry.get('page')

        # Find matching header block
        best_match = None
        best_score = 0

        for block in header_blocks:
            if block['id'] in used_block_ids:
                continue

            block_text = block['text_content']
            block_page = block['page_number']

            # Skip if not chapter-like
            if not is_chapter_heading(block_text):
                continue

            # Calculate match score
            score = 0

            # Page proximity (if ToC has page number)
            if toc_page and abs(block_page - toc_page) <= 2:
                score += 40

            # Text similarity (simple contains check)
            if toc_heading.lower() in block_text.lower() or block_text.lower() in toc_heading.lower():
                score += 50

            # Chapter pattern bonus
            score += 10

            if score > best_score:
                best_score = score
                best_match = block

        if best_match:
            # Estimate page_end (until next chapter or max)
            if i + 1 < len(toc_chapters):
                next_page = toc_chapters[i + 1].get('page', best_match['page_number'] + 50)
                page_end = next_page - 1
            else:
                page_end = best_match['page_number'] + 100  # Estimate

            chapters.append({
                'level': 1,
                'heading': best_match['text_content'],
                'page_start': best_match['page_number'],
                'page_end': page_end,
                'order_index': len(chapters) + 1,
                'header_block_id': best_match['id'],
            })

            used_block_ids.add(best_match['id'])

    # Fallback: if no ToC chapters found, look for chapter patterns directly
    if not chapters:
        logger.warning("No ToC chapters found, using pattern-based detection")
        for block in header_blocks:
            if block['id'] not in used_block_ids and is_chapter_heading(block['text_content']):
                chapters.append({
                    'level': 1,
                    'heading': block['text_content'],
                    'page_start': block['page_number'],
                    'page_end': block['page_number'] + 50,  # Estimate
                    'order_index': len(chapters) + 1,
                    'header_block_id': block['id'],
                })
                used_block_ids.add(block['id'])

    logger.info(f"Identified {len(chapters)} chapters")
    return chapters


def identify_diseases(
    header_blocks: List[Dict[str, Any]],
    chapter: Dict[str, Any],
    toc_entries: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Identify disease/topic sections (Level 2) within a chapter.

    Looks for numbered headings like "1.1.1 Disease Name" and matches
    with ToC entries when available.

    Args:
        header_blocks: All section header blocks
        chapter: Parent chapter section dict
        toc_entries: ToC entries for reference

    Returns:
        List of disease section dicts with level=2

    Example:
        >>> diseases = identify_diseases(headers, chapter, toc)
        >>> for d in diseases:
        ...     print(f"  {d['heading']} (page {d['page_start']})")
    """
    diseases = []

    # Filter headers within chapter page range
    chapter_headers = [
        h for h in header_blocks
        if chapter['page_start'] <= h['page_number'] <= chapter['page_end']
        and h['id'] != chapter['header_block_id']
    ]

    # Track used blocks
    used_block_ids: Set[int] = set()

    for block in chapter_headers:
        if block['id'] in used_block_ids:
            continue

        text = block['text_content']

        # Check for numbered heading (disease pattern)
        numbered = extract_numbered_heading(text)
        if numbered:
            numbering, heading_text = numbered
            level = infer_level_from_numbering(numbering)

            # Level 2 is disease/topic
            if level == 2:
                diseases.append({
                    'level': 2,
                    'heading': text,
                    'page_start': block['page_number'],
                    'page_end': block['page_number'] + 5,  # Will adjust later
                    'order_index': len(diseases) + 1,
                    'header_block_id': block['id'],
                    'parent_chapter': chapter,
                    'numbering': numbering,
                })
                used_block_ids.add(block['id'])

    # Adjust page_end for each disease (until next disease)
    for i, disease in enumerate(diseases):
        if i + 1 < len(diseases):
            disease['page_end'] = diseases[i + 1]['page_start'] - 1
        else:
            disease['page_end'] = chapter['page_end']

    logger.debug(f"Identified {len(diseases)} diseases in chapter '{chapter['heading']}'")
    return diseases


def identify_subsections(
    header_blocks: List[Dict[str, Any]],
    disease: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Identify subsections (Level 3+) within a disease.

    Looks for standard clinical subsections (Definition, Management, etc.)
    and numbered subsections (e.g., "1.1.1.1").

    Args:
        header_blocks: All section header blocks
        disease: Parent disease section dict

    Returns:
        List of subsection dicts with level=3+

    Example:
        >>> subsections = identify_subsections(headers, disease)
        >>> for s in subsections:
        ...     print(f"    {s['heading']}")
    """
    subsections = []

    # Filter headers within disease page range
    disease_headers = [
        h for h in header_blocks
        if disease['page_start'] <= h['page_number'] <= disease['page_end']
        and h['id'] != disease['header_block_id']
    ]

    for block in disease_headers:
        text = block['text_content']

        # Check for standard subsection
        is_standard, subsection_type = is_standard_subsection(text)
        if is_standard:
            subsections.append({
                'level': 3,
                'heading': text,
                'page_start': block['page_number'],
                'page_end': block['page_number'] + 1,  # Will adjust
                'order_index': len(subsections) + 1,
                'header_block_id': block['id'],
                'parent_disease': disease,
                'subsection_type': subsection_type,
            })
            continue

        # Check for numbered subsection
        numbered = extract_numbered_heading(text)
        if numbered:
            numbering, heading_text = numbered
            level = infer_level_from_numbering(numbering)

            # Level 3+ is subsection
            if level >= 3:
                subsections.append({
                    'level': level,
                    'heading': text,
                    'page_start': block['page_number'],
                    'page_end': block['page_number'] + 1,
                    'order_index': len(subsections) + 1,
                    'header_block_id': block['id'],
                    'parent_disease': disease,
                    'numbering': numbering,
                })

    # Adjust page_end for subsections
    for i, subsection in enumerate(subsections):
        if i + 1 < len(subsections):
            subsection['page_end'] = subsections[i + 1]['page_start'] - 1
        else:
            subsection['page_end'] = disease['page_end']

    logger.debug(f"Identified {len(subsections)} subsections in disease '{disease['heading']}'")
    return subsections


def build_heading_path(section: Dict[str, Any]) -> str:
    """
    Construct full heading path for a section.

    Builds path like: "Chapter > Disease > Subsection"

    Args:
        section: Section dict (must have level and heading)

    Returns:
        Full heading path string

    Example:
        >>> path = build_heading_path(subsection)
        >>> print(path)
        "Emergencies and Trauma > 1.1.1 Anaphylactic Shock > Management"
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

    Args:
        all_blocks: All raw_blocks (not just headers)
        sections: All sections (chapters, diseases, subsections)

    Returns:
        Dict mapping section_id to list of block_ids

    Example:
        >>> mapping = assign_blocks_to_sections(blocks, sections)
        >>> for section_id, block_ids in mapping.items():
        ...     print(f"Section {section_id}: {len(block_ids)} blocks")
    """
    mapping: Dict[int, List[int]] = {}

    # Sort sections by page_start for efficient lookup
    sorted_sections = sorted(sections, key=lambda s: (s['page_start'], s['level']))

    # Create a lookup dict for faster access
    # Use (page, level) as key to handle nested sections
    section_lookup: Dict[tuple, Dict[str, Any]] = {}
    for section in sorted_sections:
        for page in range(section['page_start'], section['page_end'] + 1):
            key = (page, section['level'])
            # Keep the most specific (highest level) section for each page
            if key not in section_lookup or section['level'] > section_lookup[key]['level']:
                section_lookup[key] = section

    orphaned_blocks = 0

    for block in all_blocks:
        # Skip page headers/footers (they shouldn't have section_id)
        if block.get('block_type') in ['page_header', 'page_footer']:
            continue

        page = block['page_number']

        # Find most specific section for this page
        # Try level 3+ first (subsections), then level 2 (diseases), then level 1 (chapters)
        assigned_section = None

        for level in [4, 3, 2, 1]:
            key = (page, level)
            if key in section_lookup:
                assigned_section = section_lookup[key]
                break

        if assigned_section:
            # Use a temporary ID (will be replaced with actual DB ID later)
            section_id = id(assigned_section)  # Use object ID as temporary key

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

    Orchestrates chapter, disease, and subsection identification into
    a flat list of all sections with proper heading paths.

    Args:
        header_blocks: All section header blocks from raw_blocks
        toc_entries: ToC entries from extract_toc_from_docling

    Returns:
        Flat list of all sections (chapters, diseases, subsections) with
        heading_path populated, ready for database insertion

    Example:
        >>> hierarchy = build_complete_hierarchy(headers, toc)
        >>> print(f"Total sections: {len(hierarchy)}")
        >>> for section in hierarchy[:5]:
        ...     print(f"[L{section['level']}] {section['heading_path']}")
    """
    all_sections = []
    global_order = 1

    # Step 1: Identify chapters
    chapters = identify_chapters(header_blocks, toc_entries)

    for chapter in chapters:
        chapter['order_index'] = global_order
        chapter['heading_path'] = build_heading_path(chapter)
        all_sections.append(chapter)
        global_order += 1

        # Step 2: Identify diseases within chapter
        diseases = identify_diseases(header_blocks, chapter, toc_entries)

        for disease in diseases:
            disease['order_index'] = global_order
            disease['heading_path'] = build_heading_path(disease)
            all_sections.append(disease)
            global_order += 1

            # Step 3: Identify subsections within disease
            subsections = identify_subsections(header_blocks, disease)

            for subsection in subsections:
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
    'identify_diseases',
    'identify_subsections',
    'build_heading_path',
    'assign_blocks_to_sections',
    'build_complete_hierarchy',
]
