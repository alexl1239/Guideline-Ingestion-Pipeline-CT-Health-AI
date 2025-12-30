"""
Table of Contents (ToC) Parser for Docling JSON

Extracts and parses Table of Contents entries from Docling's JSON output.
Falls back to section header extraction if no explicit ToC is found.

Key Functions:
- extract_toc_from_docling: Main entry point for ToC extraction
- parse_toc_entry: Parse individual ToC line for heading and page number
- infer_toc_level: Determine hierarchy level from ToC entry
"""

import re
from typing import List, Dict, Optional, Any
from src.utils.logging_config import logger


# Common ToC heading patterns
TOC_HEADING_PATTERNS = [
    r'^table\s+of\s+contents',
    r'^contents',
    r'^index',
]

# Pattern to extract page numbers from ToC entries
# Matches patterns like: "1.2.3 Heading Name ......... 45" or "Heading Name    123"
TOC_PAGE_PATTERN = re.compile(
    r'^(.+?)\s*[.\s]{2,}\s*(\d+)\s*$|'  # Dotted leaders
    r'^(.+?)\s{3,}(\d+)\s*$'             # Multiple spaces
)

# Pattern for numbered ToC entries
TOC_NUMBERED_PATTERN = re.compile(r'^(\d+(?:\.\d+)*)\s+(.+)$')


def extract_toc_from_docling(docling_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract Table of Contents entries from Docling JSON.

    Attempts to find and parse an explicit ToC section. If none found,
    falls back to extracting section headers from the document.

    Args:
        docling_json: Full Docling JSON output

    Returns:
        List of ToC entries, each with:
            - heading: Section heading text
            - page: Page number (if available)
            - level: Inferred hierarchy level
            - numbering: Numbering prefix (e.g., "1.2.3") if present

    Example:
        >>> toc = extract_toc_from_docling(docling_json)
        >>> for entry in toc[:3]:
        ...     print(f"{entry['heading']} (page {entry['page']}, level {entry['level']})")
    """
    logger.debug("Attempting to extract ToC from Docling JSON")

    # Try to find explicit ToC section
    toc_entries = _find_explicit_toc(docling_json)

    if toc_entries:
        logger.info(f"Found explicit ToC with {len(toc_entries)} entries")
        return toc_entries

    # Fallback: extract section headers as pseudo-ToC
    logger.warning("No explicit ToC found, falling back to section header extraction")
    toc_entries = _extract_section_headers_as_toc(docling_json)
    logger.info(f"Extracted {len(toc_entries)} section headers as ToC entries")

    return toc_entries


def _find_explicit_toc(docling_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Find and parse an explicit Table of Contents section.

    Looks for ToC markers in the first 20 pages, then parses entries.
    Also recognizes document_index labels from Docling.

    Args:
        docling_json: Full Docling JSON output

    Returns:
        List of parsed ToC entries, or empty list if no ToC found
    """
    texts = docling_json.get('texts', [])
    if not texts:
        return []

    # Strategy 1: Look for document_index labels (Docling's ToC marker)
    toc_entries_from_index = []
    for text_elem in texts:
        label = text_elem.get('label', '')
        if label == 'document_index':
            text_content = text_elem.get('text', '').strip()
            prov = text_elem.get('prov', [])
            page = prov[0].get('page_no') if prov else None

            # Each document_index block may contain multiple lines
            lines = text_content.split('\n')
            for line in lines:
                line = line.strip()
                if not line or len(line) < 5:  # Skip empty/very short lines
                    continue

                # Parse ToC entry from each line
                entry = parse_toc_entry(line)
                if entry:
                    # Use page from provenance if not in text
                    if not entry['page'] and page:
                        entry['page'] = page
                    toc_entries_from_index.append(entry)

    # If we found document_index entries, use them
    if len(toc_entries_from_index) >= 5:
        logger.debug(f"Found {len(toc_entries_from_index)} ToC entries from document_index labels")
        return toc_entries_from_index

    # Strategy 2: Find ToC start marker (look in first 20 pages)
    toc_start_idx = None
    for i, text in enumerate(texts[:100]):  # Check first 100 text elements
        text_content = text.get('text', '').strip().lower()
        prov = text.get('prov', [])
        page = prov[0].get('page_no', 999) if prov else 999

        if page > 20:  # ToC unlikely after page 20
            break

        for pattern in TOC_HEADING_PATTERNS:
            if re.match(pattern, text_content, re.IGNORECASE):
                toc_start_idx = i
                logger.debug(f"Found ToC marker at index {i}: '{text_content}'")
                break

        if toc_start_idx is not None:
            break

    if toc_start_idx is None:
        return []

    # Parse ToC entries (following the ToC marker)
    toc_entries = []
    toc_end_markers = ['introduction', 'chapter 1', 'preface', 'foreword']

    for i in range(toc_start_idx + 1, min(toc_start_idx + 200, len(texts))):
        text_elem = texts[i]
        text_content = text_elem.get('text', '').strip()

        if not text_content:
            continue

        # Check for ToC end markers
        text_lower = text_content.lower()
        if any(marker in text_lower for marker in toc_end_markers):
            if len(toc_entries) > 5:  # Must have found substantial ToC
                break

        # Try to parse as ToC entry
        entry = parse_toc_entry(text_content)
        if entry:
            toc_entries.append(entry)

    return toc_entries if len(toc_entries) > 5 else []


def _extract_section_headers_as_toc(docling_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract section headers from document as pseudo-ToC.

    Used as fallback when no explicit ToC is found. Extracts all elements
    with label='section_header'.

    Args:
        docling_json: Full Docling JSON output

    Returns:
        List of section headers formatted as ToC entries
    """
    texts = docling_json.get('texts', [])
    toc_entries = []

    for text_elem in texts:
        label = text_elem.get('label', '')
        text_content = text_elem.get('text', '').strip()

        if label == 'section_header' and text_content:
            # Get page number from provenance
            prov = text_elem.get('prov', [])
            page = prov[0].get('page_no') if prov else None

            # Try to parse numbering
            match = TOC_NUMBERED_PATTERN.match(text_content)
            numbering = None
            heading = text_content

            if match:
                numbering = match.group(1)
                heading = match.group(2).strip()

            # Infer level from numbering or fallback to default
            level = infer_toc_level(numbering) if numbering else 2

            toc_entries.append({
                'heading': heading,
                'page': page,
                'level': level,
                'numbering': numbering,
            })

    return toc_entries


def parse_toc_entry(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single ToC entry line.

    Extracts heading, page number, and numbering from ToC lines like:
    - "1.2.3 Anaphylactic Shock ......... 45"
    - "Introduction    12"
    - "Chapter 2: Infectious Diseases ... 100"

    Args:
        text: ToC entry text

    Returns:
        Dict with heading, page, level, numbering, or None if not a valid entry

    Example:
        >>> parse_toc_entry("1.2.3 Anaphylactic Shock ......... 45")
        {'heading': 'Anaphylactic Shock', 'page': 45, 'level': 3, 'numbering': '1.2.3'}
    """
    if not text or len(text) < 3:
        return None

    # Try to match page number pattern
    match = TOC_PAGE_PATTERN.match(text)

    if match:
        # Extract heading and page
        heading = (match.group(1) or match.group(3) or '').strip()
        page_str = match.group(2) or match.group(4)
        page = int(page_str) if page_str else None

        if not heading:
            return None

        # Try to extract numbering prefix
        num_match = TOC_NUMBERED_PATTERN.match(heading)
        numbering = None

        if num_match:
            numbering = num_match.group(1)
            heading = num_match.group(2).strip()

        # Infer level
        level = infer_toc_level(numbering) if numbering else 1

        return {
            'heading': heading,
            'page': page,
            'level': level,
            'numbering': numbering,
        }

    # No page number found - might still be a heading
    # Only accept if it has numbering
    num_match = TOC_NUMBERED_PATTERN.match(text)
    if num_match:
        numbering = num_match.group(1)
        heading = num_match.group(2).strip()
        level = infer_toc_level(numbering)

        return {
            'heading': heading,
            'page': None,
            'level': level,
            'numbering': numbering,
        }

    return None


def infer_toc_level(numbering: Optional[str]) -> int:
    """
    Infer hierarchy level from ToC numbering.

    Rules:
    - "1" or "2" → Level 1 (Chapter)
    - "1.1" or "2.3" → Level 2 (Disease/Topic)
    - "1.1.1" or "2.3.4" → Level 3 (Subsection)
    - No numbering → Level 1 (default)

    Args:
        numbering: Numeric prefix (e.g., "1.2.3")

    Returns:
        Hierarchy level (1-4)

    Example:
        >>> infer_toc_level("1")
        1
        >>> infer_toc_level("1.2.3")
        3
    """
    if not numbering:
        return 1

    # Count dots to determine depth
    depth = numbering.count('.') + 1

    # Clamp to reasonable range
    return min(depth, 4)


def validate_toc_entries(toc_entries: List[Dict[str, Any]]) -> bool:
    """
    Validate that extracted ToC entries are reasonable.

    Checks:
    - At least 3 entries
    - Contains level 1 entries (chapters)
    - Page numbers are sequential (if present)

    Args:
        toc_entries: List of ToC entries to validate

    Returns:
        True if ToC entries appear valid

    Example:
        >>> entries = [{'heading': 'Ch 1', 'page': 10, 'level': 1}]
        >>> validate_toc_entries(entries)
        False  # Too few entries
    """
    if len(toc_entries) < 3:
        logger.warning("ToC validation failed: too few entries")
        return False

    # Check for level 1 entries
    has_level_1 = any(entry.get('level') == 1 for entry in toc_entries)
    if not has_level_1:
        logger.warning("ToC validation failed: no level 1 entries found")
        return False

    # Check page number sequence (if present)
    pages_with_numbers = [e for e in toc_entries if e.get('page') is not None]
    if len(pages_with_numbers) > 1:
        pages = [e['page'] for e in pages_with_numbers]
        # Should be generally increasing (allow some backwards for subsections)
        if pages[-1] < pages[0]:
            logger.warning("ToC validation failed: page numbers not increasing")
            return False

    logger.debug("ToC entries validated successfully")
    return True


def get_toc_summary(toc_entries: List[Dict[str, Any]]) -> str:
    """
    Generate human-readable summary of ToC entries.

    Args:
        toc_entries: List of ToC entries

    Returns:
        Formatted summary string

    Example:
        >>> summary = get_toc_summary(toc_entries)
        >>> print(summary)
        ToC Summary: 25 entries
          Level 1: 5 entries
          Level 2: 15 entries
          Level 3: 5 entries
    """
    if not toc_entries:
        return "ToC Summary: No entries found"

    # Count by level
    level_counts = {}
    for entry in toc_entries:
        level = entry.get('level', 0)
        level_counts[level] = level_counts.get(level, 0) + 1

    summary_lines = [f"ToC Summary: {len(toc_entries)} entries"]
    for level in sorted(level_counts.keys()):
        summary_lines.append(f"  Level {level}: {level_counts[level]} entries")

    return "\n".join(summary_lines)


__all__ = [
    'extract_toc_from_docling',
    'parse_toc_entry',
    'infer_toc_level',
    'validate_toc_entries',
    'get_toc_summary',
]
