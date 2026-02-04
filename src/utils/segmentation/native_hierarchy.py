"""
Native Hierarchy Extractor for Docling

Uses Docling's native layout analysis to extract section hierarchy directly
from parsed elements. This approach is document-agnostic and works across
different document types.

Key Features:
- Trusts Docling's native 'level' field from section_header elements
- Falls back to numbering inference when native level unavailable
- No ToC parsing or document-specific patterns needed
- Works across different document formats and types

Replaces: toc_parser.py, hierarchy_builder.py (ToC-based approach)
"""

from typing import List, Dict, Any, Optional
from src.utils.logging_config import logger


def _extract_page_number(element: Dict[str, Any]) -> Optional[int]:
    """
    Extract page number from Docling element's provenance data.

    Args:
        element: Docling element dict

    Returns:
        Page number (1-indexed) or None if not found
    """
    provenance = element.get('prov', [])
    if provenance and isinstance(provenance, list) and len(provenance) > 0:
        first_prov = provenance[0]
        if isinstance(first_prov, dict):
            # Docling 2.0 uses 'page_no'
            if 'page_no' in first_prov:
                return first_prov['page_no']
            # Older versions use 'page'
            if 'page' in first_prov:
                return first_prov['page']

    # Fallback to direct page_no field
    if 'page_no' in element:
        return element['page_no']

    return None


def _get_section_headers_from_json(doc_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract all section_header elements from Docling JSON.

    Args:
        doc_json: Full Docling JSON output

    Returns:
        List of section header elements with native level, text, and page info
    """
    headers = []

    # Docling 2.0: Check element arrays directly
    if 'texts' in doc_json:
        logger.debug("Detected Docling 2.0 structure, extracting from 'texts' array")

        texts = doc_json.get('texts', [])
        for element in texts:
            element_type = element.get('type') or element.get('label')

            # Only process section_header elements
            if element_type == 'section_header':
                headers.append(element)

        logger.info(f"Found {len(headers)} section headers in 'texts' array")

    # Fallback: Legacy Docling structure
    elif 'elements' in doc_json:
        logger.debug("Detected legacy Docling structure, extracting from 'elements' array")

        elements = doc_json.get('elements', [])
        for element in elements:
            element_type = element.get('type') or element.get('label')

            if element_type == 'section_header':
                headers.append(element)

        logger.info(f"Found {len(headers)} section headers in 'elements' array")

    else:
        logger.warning("Unknown Docling JSON structure, cannot extract headers")
        logger.debug(f"JSON keys: {list(doc_json.keys())}")

    return headers


def extract_native_hierarchy(doc_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract section hierarchy directly from Docling's native layout analysis.

    Uses section_header elements with native 'level' field from Docling's
    layout analysis. This eliminates ToC parsing and is more robust across
    different document formats.

    Args:
        doc_json: Full Docling JSON output from DoclingDocument.export_to_dict()

    Returns:
        List of section dicts with:
            - level: Hierarchy level (1=chapter, 2=disease, 3+=subsection)
            - heading: Section heading text
            - heading_path: Full path string
            - page_start: Starting page number
            - page_end: Ending page number (calculated)
            - order_index: Sequential order in document
            - metadata: Additional info (native level, is_standard_subsection, etc.)

    Example:
        >>> sections = extract_native_hierarchy(doc_json)
        >>> for section in sections[:3]:
        ...     print(f"{section['level']}: {section['heading']} (pages {section['page_start']}-{section['page_end']})")
    """
    logger.info("Extracting native hierarchy from Docling JSON...")

    # 1. Get all section_header elements
    header_elements = _get_section_headers_from_json(doc_json)

    if not header_elements:
        logger.error("No section headers found in Docling JSON")
        return []

    logger.success(f"✓ Found {len(header_elements)} section headers")

    # Get document page count from Docling JSON
    doc_page_count = 0
    if 'pages' in doc_json:
        pages_data = doc_json['pages']
        if isinstance(pages_data, list):
            # Pages as array
            doc_page_count = len(pages_data)
        elif isinstance(pages_data, dict):
            # Pages as dict with numeric keys (Docling 2.0)
            doc_page_count = len(pages_data)
    elif 'page_count' in doc_json:
        doc_page_count = doc_json['page_count']
    elif 'num_pages' in doc_json:
        doc_page_count = doc_json['num_pages']

    if doc_page_count > 0:
        logger.info(f"Document has {doc_page_count} pages")
    else:
        logger.warning("Could not determine document page count from Docling JSON")

    # 2. Build section tree from headers
    sections = build_section_tree(header_elements)

    # 3. Assign page ranges (pass actual doc page count)
    sections = assign_page_ranges(sections, doc_page_count)

    # 4. Build heading paths
    sections = build_heading_paths(sections)

    # 5. Validate hierarchy
    validate_hierarchy(sections)

    logger.success(f"✓ Extracted {len(sections)} sections from native hierarchy")

    return sections


def _is_end_matter(heading: str) -> bool:
    """
    Check if heading is end matter (appendices, references, annexes).

    End matter should always be level 1, regardless of numbering.

    Args:
        heading: Heading text

    Returns:
        True if this is end matter
    """
    import re
    heading_lower = heading.lower()

    # Check for common end matter patterns
    # Use word boundaries to avoid false matches (e.g., "Terms of Reference" should NOT match)
    end_matter_patterns = [
        r'\btool\s+kit\b',
        r'^annex\b',  # Start of heading
        r'^appendix\b',
        r'^references?\b',  # "Reference" or "References" at start
        r'^bibliography\b',
        r'^glossary\b',
        r'^index\b',
        r'^acknowledgements?\b',
        r'\babout\s+the\s+author\b',
    ]

    return any(re.search(pattern, heading_lower) for pattern in end_matter_patterns)


def _is_front_matter(heading: str) -> bool:
    """
    Check if heading is front matter (ToC, foreword, acronyms, etc.).

    Front matter should be level 1.

    Args:
        heading: Heading text

    Returns:
        True if this is front matter
    """
    heading_lower = heading.lower()

    # Common front matter patterns
    front_matter_patterns = [
        'table of contents',
        'contents',
        'foreword',
        'preface',
        'acknowledgement',
        'acronym',
        'abbreviation',
        'executive summary',
    ]

    return any(pattern in heading_lower for pattern in front_matter_patterns)


def _is_likely_subsection(heading: str) -> bool:
    """
    Check if heading looks like a subsection (Step N, letter-based, etc.).

    These should NOT be level 1 unless they're in front/end matter.

    Args:
        heading: Heading text

    Returns:
        True if this looks like a subsection pattern
    """
    import re

    heading_lower = heading.lower()

    # Patterns that indicate subsections
    subsection_patterns = [
        r'^step\s+\d+[:\.]',          # "Step 1:", "Step 2:"
        r'^[a-z]\)',                   # "a)", "b)", "c)"
        r'^[ivx]+\)',                  # "i)", "ii)", "iii)" (Roman numerals)
        r'^\([a-z]\)',                 # "(a)", "(b)"
        r'^[a-z]\.(?!\d)',             # "a.", "b." (not followed by digit)
    ]

    return any(re.match(pattern, heading_lower) for pattern in subsection_patterns)


def _infer_level_from_numbering(heading: str) -> Optional[int]:
    """
    Infer hierarchy level from heading numbering pattern.

    Examples:
        "1 INTRODUCTION" -> 1
        "1.1 Context" -> 2
        "1.1.1 Background" -> 3
        "23.2.4 Disease Name" -> 3
        "Step 1: ..." -> None (context-dependent, let caller handle)
        "a) Development ..." -> None (context-dependent)
        "Tool Kit" -> 1 (end matter)
        "Annex 1: ..." -> 1 (end matter)

    Args:
        heading: Heading text

    Returns:
        Inferred level (1-5) or None if no numbering found
    """
    import re

    # Check for end matter first - always level 1
    if _is_end_matter(heading):
        return 1

    # Match numeric patterns at start: "1", "1.1", "1.1.1", etc.
    match = re.match(r'^(\d+(?:\.\d+)*)', heading)
    if match:
        numbering = match.group(1)
        # Count dots to determine level
        # "1" -> 0 dots -> level 1
        # "1.1" -> 1 dot -> level 2
        # "1.1.1" -> 2 dots -> level 3
        level = numbering.count('.') + 1
        return min(level, 5)  # Cap at level 5

    return None


def build_section_tree(header_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Construct section tree from Docling section_header elements.

    Strategy (document-agnostic):
    1. Primarily trust Docling's native 'level' field from layout analysis
    2. Fall back to numbering inference if native level unavailable
    3. Track last seen level for consistency

    This approach works across different document types without needing
    document-specific patterns or subsection lists.

    Args:
        header_elements: List of section_header elements from Docling

    Returns:
        List of section dicts with level, heading, page_start, order_index
    """
    logger.info("Building section tree from headers...")

    sections = []
    last_seen_level = 1  # Track last seen level for fallback

    for i, element in enumerate(header_elements):
        # Extract basic info
        heading_text = element.get('text', '').strip()
        if not heading_text:
            heading_text = element.get('orig', '').strip()

        if not heading_text:
            logger.debug(f"Skipping header {i} with no text")
            continue

        # Get native level from Docling's layout analysis
        native_level = element.get('level')

        # Get page number
        page_num = _extract_page_number(element)

        if not page_num:
            logger.warning(f"Header missing page number: {heading_text[:50]}")
            page_num = 0  # Will be handled later

        # Determine level (prioritize numbering inference over native level)
        # VLM sometimes assigns all headings to level 1, so trust numbering first
        inferred_level = _infer_level_from_numbering(heading_text)

        if inferred_level:
            # Use numbering-based level (most reliable for numbered sections)
            level = inferred_level
            last_seen_level = level
        elif _is_front_matter(heading_text):
            # Front matter is always level 1
            level = 1
            last_seen_level = 1
        elif _is_likely_subsection(heading_text):
            # Subsection patterns (Step N, a), b), etc.) should increment from context
            # These are NOT level 1, even if VLM says so
            level = min(last_seen_level + 1, 5)
        elif native_level is not None and native_level > 0:
            # Use native level, but be suspicious if it's 1 and we're deep in content
            if native_level == 1 and last_seen_level >= 2:
                # VLM says level 1, but we're in chapter content - probably wrong
                # Increment from last seen level instead
                level = min(last_seen_level + 1, 5)
            else:
                level = native_level
                last_seen_level = level
        else:
            # No numbering and no native level: assume one level deeper than previous
            level = min(last_seen_level + 1, 5)  # Cap at level 5

        # Create section dict
        section = {
            'heading': heading_text,
            'level': level,
            'page_start': page_num,
            'page_end': page_num,  # Will be calculated later
            'order_index': i,
            'heading_path': '',  # Will be built later
            'metadata': {
                'native_docling_level': native_level,
                'inferred_from_numbering': _infer_level_from_numbering(heading_text) is not None,
                'element_id': element.get('id'),
            }
        }

        sections.append(section)

    logger.success(f"✓ Built tree with {len(sections)} sections")

    # Log level distribution
    level_counts = {}
    for section in sections:
        level = section['level']
        level_counts[level] = level_counts.get(level, 0) + 1

    logger.info("Level distribution:")
    for level in sorted(level_counts.keys()):
        logger.info(f"  - Level {level}: {level_counts[level]} sections")

    return sections


def assign_page_ranges(sections: List[Dict[str, Any]], doc_page_count: int = 0) -> List[Dict[str, Any]]:
    """
    Calculate page_end for each section based on hierarchy and document order.

    Strategy:
    - Chapters (level 1): Span until next chapter
    - Other sections: Span until next section at same or higher level

    This ensures chapters contain all their subsections, even if subsections
    span multiple pages.

    Args:
        sections: List of sections with page_start already set
        doc_page_count: Actual page count from Docling (0 if unknown)

    Returns:
        Sections with page_end calculated
    """
    logger.info("Assigning page ranges...")

    # Sort by page_start to ensure correct ordering
    sections_sorted = sorted(sections, key=lambda s: (s['page_start'], s['order_index']))

    # Determine last page: use doc_page_count if available, else estimate from sections
    if doc_page_count > 0:
        last_page = doc_page_count
        logger.debug(f"Using document page count: {last_page}")
    else:
        last_page = max(s['page_start'] for s in sections_sorted) + 20
        logger.debug(f"Document page count unknown, estimating: {last_page}")

    for i, section in enumerate(sections_sorted):
        current_level = section['level']

        # Find the next section at same or higher level (smaller or equal level number)
        next_section = None
        for j in range(i + 1, len(sections_sorted)):
            if sections_sorted[j]['level'] <= current_level:
                next_section = sections_sorted[j]
                break

        if next_section:
            # Page range ends just before next peer/parent section starts
            section['page_end'] = max(section['page_start'], next_section['page_start'] - 1)
        else:
            # Last section at this level: span to end of document
            section['page_end'] = last_page

    logger.success("✓ Page ranges assigned")

    return sections_sorted


def build_heading_paths(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Construct full heading_path strings for each section.

    Heading path shows the full hierarchy:
    - Level 1: "Chapter 1: Emergencies"
    - Level 2: "Chapter 1: Emergencies > 1.1 Anaphylactic Shock"
    - Level 3: "Chapter 1: Emergencies > 1.1 Anaphylactic Shock > Definition"

    Args:
        sections: Sections with level and heading

    Returns:
        Sections with heading_path built
    """
    logger.info("Building heading paths...")

    # Track parent sections at each level
    parent_stack = {}  # Maps level -> section

    for section in sections:
        level = section['level']
        heading = section['heading']

        # Build path by concatenating ancestors
        path_parts = []

        # Add all ancestor headings (levels < current level)
        for ancestor_level in sorted([l for l in parent_stack.keys() if l < level]):
            path_parts.append(parent_stack[ancestor_level]['heading'])

        # Add current heading
        path_parts.append(heading)

        # Join with " > "
        section['heading_path'] = ' > '.join(path_parts)

        # Update parent stack for this level
        parent_stack[level] = section

        # Clear deeper levels (we've moved to a new branch)
        parent_stack = {l: s for l, s in parent_stack.items() if l <= level}

    logger.success("✓ Heading paths built")

    return sections


def validate_hierarchy(sections: List[Dict[str, Any]]) -> bool:
    """
    Validate extracted hierarchy for common issues.

    Checks:
    - All sections have page numbers
    - No sections with page_start > page_end
    - Reasonable page ranges (not too large)
    - Level distribution looks correct (at least some level 1 and 2)

    Args:
        sections: Extracted sections

    Returns:
        True if validation passes, False otherwise

    Side Effects:
        Logs warnings for any issues found
    """
    logger.info("Validating hierarchy...")

    issues = []

    # Check 1: All sections have page numbers
    missing_pages = [s for s in sections if s['page_start'] == 0 or s['page_end'] == 0]
    if missing_pages:
        issues.append(f"{len(missing_pages)} sections missing page numbers")

    # Check 2: No inverted page ranges
    inverted = [s for s in sections if s['page_start'] > s['page_end']]
    if inverted:
        issues.append(f"{len(inverted)} sections have page_start > page_end")
        for section in inverted[:3]:  # Show first 3
            logger.warning(
                f"  Inverted range: {section['heading']} "
                f"(pages {section['page_start']}-{section['page_end']})"
            )

    # Check 3: Unreasonably large page ranges (>200 pages for non-chapters)
    large_ranges = [
        s for s in sections
        if s['level'] > 1 and (s['page_end'] - s['page_start']) > 200
    ]
    if large_ranges:
        issues.append(f"{len(large_ranges)} sections have suspiciously large page ranges (>200 pages)")
        for section in large_ranges[:3]:  # Show first 3
            logger.warning(
                f"  Large range: {section['heading']} "
                f"(pages {section['page_start']}-{section['page_end']}, level {section['level']})"
            )

    # Check 4: Level distribution
    level_counts = {}
    for section in sections:
        level = section['level']
        level_counts[level] = level_counts.get(level, 0) + 1

    if level_counts.get(1, 0) == 0:
        issues.append("No level 1 (chapter) sections found")

    if level_counts.get(2, 0) == 0:
        issues.append("No level 2 (disease/topic) sections found")

    # Report results
    if issues:
        logger.warning(f"⚠ Hierarchy validation found {len(issues)} issues:")
        for issue in issues:
            logger.warning(f"  - {issue}")
        return False
    else:
        logger.success("✓ Hierarchy validation passed")
        return True


def get_hierarchy_summary(sections: List[Dict[str, Any]]) -> str:
    """
    Generate human-readable summary of extracted hierarchy.

    Args:
        sections: Extracted sections

    Returns:
        Multi-line string with hierarchy statistics
    """
    level_counts = {}
    for section in sections:
        level = section['level']
        level_counts[level] = level_counts.get(level, 0) + 1

    lines = [
        f"Total Sections: {len(sections)}",
        "",
        "Level Distribution:",
    ]

    for level in sorted(level_counts.keys()):
        count = level_counts[level]
        if level == 1:
            label = "Chapters"
        elif level == 2:
            label = "Diseases/Topics"
        else:
            label = "Subsections"

        lines.append(f"  - Level {level} ({label}): {count}")

    # Show page range
    if sections:
        first_page = min(s['page_start'] for s in sections if s['page_start'] > 0)
        last_page = max(s['page_end'] for s in sections)
        lines.append(f"\nPage Range: {first_page} to {last_page}")

    return '\n'.join(lines)


__all__ = [
    'extract_native_hierarchy',
    'build_section_tree',
    'assign_page_ranges',
    'build_heading_paths',
    'validate_hierarchy',
    'get_hierarchy_summary',
]
