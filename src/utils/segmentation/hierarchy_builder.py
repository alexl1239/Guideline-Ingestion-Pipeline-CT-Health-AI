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

from typing import List, Dict, Any, Optional, Set
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

    Also detects missing chapters by looking for orphan level 2 entries
    and attempting to find/infer the missing chapter from header blocks.
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

    # Detect missing chapters from orphan level 2 entries
    chapters = _infer_missing_chapters(chapters, toc_entries, header_blocks)

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

    # Sort by numbering to ensure correct order
    chapters.sort(key=lambda c: (int(c['numbering']) if c.get('numbering') and c['numbering'].isdigit() else 999, c['page_start']))

    # Reassign order_index after sorting
    for i, chapter in enumerate(chapters):
        chapter['order_index'] = i + 1

    logger.info(f"Identified {len(chapters)} chapters")
    return chapters


def _infer_missing_chapters(
    chapters: List[Dict[str, Any]],
    toc_entries: List[Dict[str, Any]],
    header_blocks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Detect and infer missing chapters from orphan level 2 ToC entries.

    If we have entries like "9.1 Neurological Disorders" but no "9" chapter,
    we look for the chapter header in header_blocks and create it.
    """
    import re

    # Get existing chapter numbers
    existing_chapter_nums = {c.get('numbering') for c in chapters if c.get('numbering')}

    # Find orphan level 2 entries (their chapter number doesn't exist)
    toc_level2 = [e for e in toc_entries if e.get('level') == 2]

    orphan_chapter_nums: Dict[str, List[Dict[str, Any]]] = {}
    for entry in toc_level2:
        chapter_num = _get_chapter_number(entry.get('numbering'))
        if chapter_num and chapter_num not in existing_chapter_nums:
            if chapter_num not in orphan_chapter_nums:
                orphan_chapter_nums[chapter_num] = []
            orphan_chapter_nums[chapter_num].append(entry)

    if not orphan_chapter_nums:
        return chapters

    logger.warning(f"Found orphan entries for missing chapters: {list(orphan_chapter_nums.keys())}")

    # Try to find each missing chapter in header blocks
    for chapter_num, orphan_entries in orphan_chapter_nums.items():
        # Patterns to match chapter header:
        # 1. "9 MENTAL..." or "9. MENTAL..." (number at start)
        # 2. "Mental, Neurological... 9" (number at end)
        pattern_start = re.compile(rf'^{chapter_num}\.?\s+[A-Z]', re.IGNORECASE)
        pattern_end = re.compile(rf'\s+{chapter_num}\s*$', re.IGNORECASE)

        # Get the first orphan's page to estimate where the chapter starts
        first_orphan_page = min(e.get('page', 9999) for e in orphan_entries)

        # Look for chapter header in blocks slightly before the first orphan
        found_chapter = None
        for block in header_blocks:
            text = block['text_content'].strip()
            page = block['page_number']

            # Only look near the expected location (within 5 pages before first orphan)
            if page > first_orphan_page:
                continue
            if page < first_orphan_page - 5:
                continue

            if pattern_start.match(text) or pattern_end.search(text):
                # Clean up the heading (remove page numbers like ".488" and trailing chapter number)
                cleaned_heading = re.sub(r'\s*\.\d+\s*$', '', text)
                cleaned_heading = re.sub(rf'\s+{chapter_num}\s*$', '', cleaned_heading)
                cleaned_heading = f"{chapter_num} {cleaned_heading.strip()}"
                found_chapter = {
                    'level': 1,
                    'heading': cleaned_heading,
                    'page_start': page,
                    'page_end': page + 50,  # Will be adjusted later
                    'order_index': 0,
                    'header_block_id': block['id'],
                    'numbering': chapter_num,
                }
                logger.info(f"Inferred missing Chapter {chapter_num}: {cleaned_heading} (page {page})")
                break

        if not found_chapter:
            # Create a placeholder chapter from the orphan entries
            found_chapter = {
                'level': 1,
                'heading': f"{chapter_num} (Inferred Chapter)",
                'page_start': first_orphan_page,
                'page_end': first_orphan_page + 50,
                'order_index': 0,
                'header_block_id': None,
                'numbering': chapter_num,
            }
            logger.warning(f"Could not find header for Chapter {chapter_num}, using placeholder")

        chapters.append(found_chapter)

    # Adjust page_end values for newly added chapters
    all_chapters = sorted(chapters, key=lambda c: c['page_start'])
    for i, chapter in enumerate(all_chapters):
        if i + 1 < len(all_chapters):
            chapter['page_end'] = all_chapters[i + 1]['page_start'] - 1
        if chapter['page_end'] < chapter['page_start']:
            chapter['page_end'] = chapter['page_start'] + 50

    return chapters


def identify_diseases_from_toc(
    toc_entries: List[Dict[str, Any]],
    chapters: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Identify disease/topic sections (Level 2) from ToC entries.

    Matches diseases to chapters by their numbering prefix, not by page range.
    For example, "1.3 POISONING" is matched to chapter "1" regardless of page number.

    Also infers missing Level 2 entries when ToC skips directly to Level 3
    (e.g., chapters 4, 8, 14 which have "4.1.1" but no "4.1").
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

    # Infer missing Level 2 entries from orphan Level 3 entries
    diseases = _infer_missing_diseases(diseases, toc_entries, chapters, chapter_by_number)

    # Deduplicate by numbering (keep first occurrence)
    seen_numberings: Set[str] = set()
    unique_diseases = []
    for disease in diseases:
        numbering = disease.get('numbering')
        if numbering and numbering in seen_numberings:
            continue
        if numbering:
            seen_numberings.add(numbering)
        unique_diseases.append(disease)

    logger.info(f"Identified {len(unique_diseases)} diseases from ToC (deduped from {len(diseases)})")
    return unique_diseases


def _infer_missing_diseases(
    diseases: List[Dict[str, Any]],
    toc_entries: List[Dict[str, Any]],
    _chapters: List[Dict[str, Any]],  # Unused but kept for API consistency
    chapter_by_number: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Infer missing Level 2 (disease) entries from orphan Level 3 ToC entries.

    Some chapters (e.g., 4, 8, 14) skip Level 2 in the ToC and go directly to Level 3.
    For example: ToC has "4.1.1", "4.1.2" but no "4.1".

    This function:
    1. Finds Level 3+ entries whose Level 2 parent doesn't exist
    2. Groups them by their Level 2 prefix (e.g., "4.1")
    3. Creates synthetic Level 2 entries spanning those groups
    """
    # Get existing disease prefixes
    existing_prefixes = {d.get('numbering') for d in diseases if d.get('numbering')}

    # Find Level 3+ ToC entries
    toc_level3_plus = [e for e in toc_entries if e.get('level', 0) >= 3]

    # Group orphan Level 3+ entries by their Level 2 prefix
    orphan_groups: Dict[str, List[Dict[str, Any]]] = {}

    for entry in toc_level3_plus:
        numbering = entry.get('numbering')
        if not numbering:
            continue

        # Get Level 2 prefix (e.g., "4.1" from "4.1.1" or "4.1.2.1")
        disease_prefix = _get_disease_prefix(numbering)
        if not disease_prefix:
            continue

        # Check if this prefix already exists as a disease
        if disease_prefix in existing_prefixes:
            continue

        if disease_prefix not in orphan_groups:
            orphan_groups[disease_prefix] = []
        orphan_groups[disease_prefix].append(entry)

    if not orphan_groups:
        return diseases

    logger.warning(f"Found orphan Level 3+ entries for missing diseases: {list(orphan_groups.keys())}")

    # Create synthetic Level 2 entries for each group
    for prefix, entries in orphan_groups.items():
        # Get chapter number from prefix
        chapter_num = _get_chapter_number(prefix)
        parent_chapter = chapter_by_number.get(chapter_num) if chapter_num else None

        if not parent_chapter:
            logger.warning(f"Could not find parent chapter for inferred disease: {prefix}")
            continue

        # Get page range from the group of entries
        pages = [e.get('page') for e in entries if e.get('page')]
        if not pages:
            continue

        page_start = min(pages)
        page_end = max(pages)

        # Ensure page_end doesn't exceed chapter end
        if page_end > parent_chapter['page_end']:
            page_end = parent_chapter['page_end']

        # Create a heading - use generic since we don't have a ToC entry for this level
        inferred_heading = f"{prefix} (Inferred Section)"

        diseases.append({
            'level': 2,
            'heading': inferred_heading,
            'page_start': page_start,
            'page_end': page_end,
            'order_index': len(diseases) + 1,
            'header_block_id': None,
            'parent_chapter': parent_chapter,
            'numbering': prefix,
            'is_inferred': True,
        })

        logger.info(f"Inferred missing disease: {prefix} (pages {page_start}-{page_end}) under chapter {chapter_num}")

    return diseases


def identify_numbered_subsections_from_toc(
    toc_entries: List[Dict[str, Any]],
    diseases: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Identify numbered subsections (Level 3+) from ToC entries.

    These are sections like "1.1.1 Anaphylactic Shock" or "1.1.2.1 Dehydration in Children".
    """
    subsections = []

    # Create lookup of diseases by their numbering prefix
    disease_by_prefix: Dict[str, Dict[str, Any]] = {}
    for disease in diseases:
        prefix = _get_disease_prefix(disease.get('numbering'))
        if prefix:
            disease_by_prefix[prefix] = disease

    # Get numbered subsections from ToC (Level 3+)
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

        # Calculate page_end from next subsection
        if i + 1 < len(toc_subsections):
            next_page = toc_subsections[i + 1].get('page')
            page_end = (next_page - 1) if next_page else page_start
        else:
            page_end = parent_disease['page_end']

        # Always cap at parent disease's page_end to avoid overlapping with sibling diseases
        # (e.g., 1.3.13 should not overlap with 1.4)
        page_end = min(page_end, parent_disease['page_end'])

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
            'parent_numbered_section': None,  # Will be set for nested numbered sections
            'numbering': toc_numbering,
            'is_numbered': True,
        })

    # Deduplicate by numbering (keep first occurrence)
    seen_numberings: Set[str] = set()
    unique_subsections = []
    for subsection in subsections:
        numbering = subsection.get('numbering')
        if numbering and numbering in seen_numberings:
            continue
        if numbering:
            seen_numberings.add(numbering)
        unique_subsections.append(subsection)

    logger.info(f"Identified {len(unique_subsections)} numbered subsections from ToC (deduped from {len(subsections)})")
    return unique_subsections


def identify_standard_subsections_from_headers(
    header_blocks: List[Dict[str, Any]],
    diseases: List[Dict[str, Any]],
    numbered_subsections: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Identify standard clinical subsections (Causes, Management, etc.) from headers.

    These are assigned as children of their containing numbered section (not siblings).
    Level is set to parent_level + 1.
    """
    standard_subsections = []

    # Build a list of all numbered sections (diseases + numbered subsections)
    # sorted by page range for efficient lookup
    all_numbered = []

    for disease in diseases:
        all_numbered.append({
            'section': disease,
            'page_start': disease['page_start'],
            'page_end': disease['page_end'],
            'level': disease['level'],
        })

    for sub in numbered_subsections:
        all_numbered.append({
            'section': sub,
            'page_start': sub['page_start'],
            'page_end': sub['page_end'],
            'level': sub['level'],
        })

    # Sort by page_start descending, level descending (to find most specific first)
    all_numbered.sort(key=lambda x: (-x['page_start'], -x['level']))

    def find_parent_numbered_section(page: int) -> Optional[Dict[str, Any]]:
        """Find the most specific numbered section that contains this page."""
        best_match = None
        best_level = 0

        for item in all_numbered:
            if item['page_start'] <= page <= item['page_end']:
                # Prefer higher level (more specific) and later start page
                if item['level'] > best_level or (item['level'] == best_level and
                    (best_match is None or item['page_start'] > best_match['page_start'])):
                    best_match = item['section']
                    best_level = item['level']

        return best_match

    # Find standard subsections from headers
    processed_headers: Set[int] = set()

    # Track which subsection types have been added for each parent to avoid duplicates
    # Key: (parent_id, normalized_heading) -> first occurrence page
    added_subsections: Dict[tuple, int] = {}

    for block in header_blocks:
        if block['id'] in processed_headers:
            continue

        text = block['text_content']
        page = block['page_number']

        # Check for standard subsection
        is_standard, subsection_type = is_standard_subsection(text)
        if not is_standard:
            continue

        # Find the parent numbered section
        parent = find_parent_numbered_section(page)
        if not parent:
            continue

        # Check for duplicate: same subsection type under same parent
        parent_id = id(parent)
        normalized_heading = text.upper().strip()
        dedup_key = (parent_id, normalized_heading)

        if dedup_key in added_subsections:
            # Skip duplicate - already have this subsection type under this parent
            processed_headers.add(block['id'])
            continue

        # Set level to parent_level + 1
        parent_level = parent['level']
        new_level = parent_level + 1

        # Determine the ultimate disease parent for heading path
        if parent['level'] == 2:
            # Parent is a disease
            parent_disease = parent
            parent_numbered_section = None
        else:
            # Parent is a numbered subsection
            parent_disease = parent.get('parent_disease')
            parent_numbered_section = parent

        standard_subsections.append({
            'level': new_level,
            'heading': text,
            'page_start': page,
            'page_end': page,  # Will be adjusted later
            'order_index': len(standard_subsections) + 1,
            'header_block_id': block['id'],
            'parent_disease': parent_disease,
            'parent_numbered_section': parent_numbered_section,
            'subsection_type': subsection_type,
            'is_numbered': False,
        })

        added_subsections[dedup_key] = page
        processed_headers.add(block['id'])

    logger.info(f"Identified {len(standard_subsections)} standard subsections from headers")
    return standard_subsections


def adjust_subsection_page_ends(
    subsections: List[Dict[str, Any]]
) -> None:
    """
    Adjust page_end for subsections based on the next subsection's page_start.
    """
    # Sort by page_start
    subsections.sort(key=lambda s: (s['page_start'], -s['level']))

    for i, subsection in enumerate(subsections):
        if i + 1 < len(subsections):
            next_sub = subsections[i + 1]
            # If next subsection starts on a later page, extend this one
            if next_sub['page_start'] > subsection['page_start']:
                new_end = next_sub['page_start'] - 1
                if new_end > subsection['page_end']:
                    subsection['page_end'] = new_end

        # Ensure page_end >= page_start
        if subsection['page_end'] < subsection['page_start']:
            subsection['page_end'] = subsection['page_start']


def build_heading_path(section: Dict[str, Any]) -> str:
    """
    Construct full heading path for a section.

    Builds path like: "Chapter > Disease > Numbered Subsection > Standard Subsection"
    """
    # Level 1 (Chapter) - no parent
    if section['level'] == 1:
        return section['heading']

    # Level 2 (Disease Category) - has chapter parent
    if section['level'] == 2:
        chapter = section.get('parent_chapter', {})
        if chapter:
            return f"{chapter['heading']} > {section['heading']}"
        return section['heading']

    # Level 3+ - could be numbered subsection or standard subsection
    parent_numbered = section.get('parent_numbered_section')
    parent_disease = section.get('parent_disease', {})

    if parent_numbered:
        # Standard subsection under a numbered subsection
        chapter = parent_disease.get('parent_chapter', {}) if parent_disease else {}
        if chapter and parent_disease:
            return f"{chapter['heading']} > {parent_disease['heading']} > {parent_numbered['heading']} > {section['heading']}"
        elif parent_disease:
            return f"{parent_disease['heading']} > {parent_numbered['heading']} > {section['heading']}"
        return f"{parent_numbered['heading']} > {section['heading']}"
    elif parent_disease:
        # Numbered subsection or standard subsection directly under disease
        chapter = parent_disease.get('parent_chapter', {})
        if chapter:
            return f"{chapter['heading']} > {parent_disease['heading']} > {section['heading']}"
        return f"{parent_disease['heading']} > {section['heading']}"

    return section['heading']


def _normalize_heading(text: str) -> str:
    """Normalize heading text for matching."""
    import re
    # Remove extra whitespace, lowercase, strip
    normalized = re.sub(r'\s+', ' ', text.strip().lower())
    # Remove common prefixes like numbering for matching
    return normalized


def _find_header_block_for_section(
    section: Dict[str, Any],
    header_blocks: List[Dict[str, Any]]
) -> Optional[int]:
    """
    Find the header block ID that matches this section's heading.

    Returns the block ID or None if not found.
    """
    section_heading = section.get('heading', '')
    section_page_start = section.get('page_start', 0)

    # Normalize section heading for matching
    normalized_section = _normalize_heading(section_heading)

    # Look for matching header blocks near the section's page_start
    for block in header_blocks:
        if block['page_number'] < section_page_start - 1:
            continue
        if block['page_number'] > section_page_start + 1:
            continue

        block_text = block.get('text_content', '')
        normalized_block = _normalize_heading(block_text)

        # Check for match (either exact or section heading contains block text)
        if normalized_block == normalized_section:
            return block['id']
        if normalized_block in normalized_section or normalized_section in normalized_block:
            return block['id']

    return None


def assign_blocks_to_sections(
    all_blocks: List[Dict[str, Any]],
    sections: List[Dict[str, Any]]
) -> Dict[int, List[int]]:
    """
    Map all content blocks to their parent sections.

    Uses block ordering within pages to correctly assign blocks to sections.
    When multiple sections exist on the same page, uses section header blocks
    to determine boundaries.

    Excludes page_header and page_footer blocks.
    """
    mapping: Dict[int, List[int]] = {}

    if not sections or not all_blocks:
        return mapping

    # Get header blocks for matching
    header_blocks = [b for b in all_blocks if b.get('block_type') == 'section_header']

    # Sort sections by order_index (document order)
    sorted_sections = sorted(sections, key=lambda s: s.get('order_index', 0))

    # Find header block IDs for each section
    section_header_ids: Dict[int, Optional[int]] = {}
    for section in sorted_sections:
        # First check if section already has header_block_id
        header_id = section.get('header_block_id')
        if not header_id:
            # Try to find matching header block
            header_id = _find_header_block_for_section(section, header_blocks)
        section_header_ids[id(section)] = header_id

    # Build list of (header_block_id, section) tuples for sections with headers
    section_boundaries = []
    for section in sorted_sections:
        header_id = section_header_ids[id(section)]
        if header_id is not None:
            section_boundaries.append((header_id, section))

    # Sort by header_block_id (document order)
    section_boundaries.sort(key=lambda x: x[0])

    # Also build page-based fallback for sections without header matches
    page_sections: Dict[int, List[Dict[str, Any]]] = {}
    for section in sorted_sections:
        for page in range(section['page_start'], section['page_end'] + 1):
            if page not in page_sections:
                page_sections[page] = []
            page_sections[page].append(section)

    orphaned_blocks = 0

    # Sort blocks by ID (document order)
    sorted_blocks = sorted(all_blocks, key=lambda b: b['id'])

    # Track current section based on header boundaries
    current_boundary_idx = 0

    for block in sorted_blocks:
        # Skip page headers/footers
        if block.get('block_type') in ['page_header', 'page_footer']:
            continue

        block_id = block['id']
        page = block['page_number']

        # Advance section boundary if we've passed the next header
        while (current_boundary_idx < len(section_boundaries) - 1 and
               block_id >= section_boundaries[current_boundary_idx + 1][0]):
            current_boundary_idx += 1

        assigned_section = None

        # If we have section boundaries and current block is at or after first boundary
        if section_boundaries and block_id >= section_boundaries[0][0]:
            # Use the current boundary's section
            assigned_section = section_boundaries[current_boundary_idx][1]

            # Verify this section actually covers this page (sanity check)
            if not (assigned_section['page_start'] <= page <= assigned_section['page_end']):
                # Fall back to page-based assignment
                assigned_section = None

        # Fallback: page-based assignment for blocks before any header
        # or when header matching fails
        if assigned_section is None and page in page_sections:
            candidates = page_sections[page]
            if candidates:
                # For fallback, prefer highest level (most specific) section
                # that starts on or before this page
                valid_candidates = [
                    s for s in candidates
                    if s['page_start'] <= page
                ]
                if valid_candidates:
                    valid_candidates.sort(key=lambda s: (-s['level'], -s['page_start']))
                    assigned_section = valid_candidates[0]

        if assigned_section:
            section_id = id(assigned_section)
            if section_id not in mapping:
                mapping[section_id] = []
            mapping[section_id].append(block_id)
        else:
            orphaned_blocks += 1
            logger.debug(f"Orphaned block {block_id} on page {page}: {block.get('block_type')}")

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

    Structure:
    - Level 1: Chapters
    - Level 2: Disease categories (e.g., "1.1 Common Emergencies")
    - Level 3: Numbered diseases (e.g., "1.1.1 Anaphylactic Shock")
               OR standard subsections under Level 2
    - Level 4: Numbered sub-diseases (e.g., "1.1.2.1 Dehydration in Children")
               OR standard subsections under Level 3
    - Level 5: Standard subsections under Level 4
    """
    # Step 1: Identify chapters from ToC
    chapters = identify_chapters(header_blocks, toc_entries)

    # Step 2: Identify diseases from ToC (matched by numbering)
    diseases = identify_diseases_from_toc(toc_entries, chapters)

    # Step 3: Identify numbered subsections from ToC (Level 3+)
    numbered_subsections = identify_numbered_subsections_from_toc(toc_entries, diseases)

    # Step 4: Identify standard subsections from headers (Causes, Management, etc.)
    # These are children of their containing numbered section
    standard_subsections = identify_standard_subsections_from_headers(
        header_blocks, diseases, numbered_subsections
    )

    # Combine all subsections and adjust page_end values
    all_subsections = numbered_subsections + standard_subsections
    adjust_subsection_page_ends(all_subsections)

    # Group diseases by parent chapter
    diseases_by_chapter: Dict[int, List[Dict[str, Any]]] = {}
    for disease in diseases:
        chapter_id = id(disease.get('parent_chapter'))
        if chapter_id not in diseases_by_chapter:
            diseases_by_chapter[chapter_id] = []
        diseases_by_chapter[chapter_id].append(disease)

    # Group subsections by parent disease
    subsections_by_disease: Dict[int, List[Dict[str, Any]]] = {}
    for subsection in all_subsections:
        disease_id = id(subsection.get('parent_disease'))
        if disease_id not in subsections_by_disease:
            subsections_by_disease[disease_id] = []
        subsections_by_disease[disease_id].append(subsection)

    # Build final ordered list
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

            # Add this disease's subsections (sorted by page, then level)
            disease_subsections = subsections_by_disease.get(id(disease), [])
            disease_subsections.sort(key=lambda s: (s['page_start'], s['level']))

            for subsection in disease_subsections:
                subsection['order_index'] = global_order
                subsection['heading_path'] = build_heading_path(subsection)
                all_sections.append(subsection)
                global_order += 1

    # Log level distribution
    level_counts = {}
    for s in all_sections:
        level = s['level']
        level_counts[level] = level_counts.get(level, 0) + 1

    logger.info(f"Built complete hierarchy: {len(all_sections)} total sections")
    for level in sorted(level_counts.keys()):
        logger.info(f"  Level {level}: {level_counts[level]}")

    return all_sections


__all__ = [
    'identify_chapters',
    'identify_diseases_from_toc',
    'identify_numbered_subsections_from_toc',
    'identify_standard_subsections_from_headers',
    'build_heading_path',
    'assign_blocks_to_sections',
    'build_complete_hierarchy',
]
