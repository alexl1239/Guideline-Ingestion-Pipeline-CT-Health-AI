"""
Block Assignment Utility for Structural Segmentation

Maps raw_blocks to sections based on page numbers and document order.
This module is used by Step 2 after sections are extracted from Docling's
native hierarchy (via native_hierarchy.py).

Note: All ToC-based hierarchy building has been removed in favor of
Docling's native layout analysis, which is more robust and eliminates
OCR errors, page offset bugs, and fuzzy matching issues.
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from src.utils.logging_config import logger


def _block_page_span(block: Dict[str, Any]) -> Tuple[int, int]:
    """
    Effective (start, end) page span for a block.

    Multi-page blocks (notably merged multi-page tables, where step 1
    stitches contiguous table fragments into one logical block) carry a
    `page_range` like "3-13". Single-page blocks just have `page_number`.
    Returning a (start, end) tuple lets section assignment reason about
    block extent uniformly without the caller caring which case applies.
    """
    page = block.get('page_number') or 0
    page_range = block.get('page_range')
    if page_range and isinstance(page_range, str) and '-' in page_range:
        try:
            start_str, end_str = page_range.split('-', 1)
            return (int(start_str), int(end_str))
        except (ValueError, TypeError):
            pass
    return (page, page)


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

    # Two-pass scan: collect exact matches and containment matches separately,
    # then prefer exact. Iteration order would otherwise return whichever match
    # came first — if a containment match (e.g. chapter header "Commercial
    # Reimbursement Policy" containing "Policy") precedes the true exact match
    # for "Policy", every subsequent section shifts by one boundary and the
    # entire section→block mapping desyncs.
    exact_matches: List[Dict[str, Any]] = []
    contain_matches: List[Dict[str, Any]] = []

    for block in header_blocks:
        if block['page_number'] < section_page_start - 1:
            continue
        if block['page_number'] > section_page_start + 1:
            continue

        block_text = block.get('text_content', '')
        normalized_block = _normalize_heading(block_text)

        if not normalized_block:
            continue

        if normalized_block == normalized_section:
            exact_matches.append(block)
        elif normalized_block in normalized_section or normalized_section in normalized_block:
            contain_matches.append(block)

    # Prefer the exact match closest to the section's declared page_start.
    if exact_matches:
        exact_matches.sort(key=lambda b: abs(b['page_number'] - section_page_start))
        return exact_matches[0]['id']

    if contain_matches:
        contain_matches.sort(key=lambda b: abs(b['page_number'] - section_page_start))
        return contain_matches[0]['id']

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

    Args:
        all_blocks: List of all raw blocks with id, page_number, block_type
        sections: List of sections with page_start, page_end, order_index

    Returns:
        Dict mapping section order_index to list of block IDs
    """
    mapping: Dict[int, List[int]] = {}

    if not sections or not all_blocks:
        return mapping

    # Get header blocks for matching
    header_blocks = [b for b in all_blocks if b.get('block_type') == 'section_header']

    # Sort sections by order_index (document order)
    sorted_sections = sorted(sections, key=lambda s: s.get('order_index', 0))

    # Find header block IDs for each section, keyed by order_index (stable unique ID)
    section_header_ids: Dict[int, Optional[int]] = {}
    for section in sorted_sections:
        # First check if section already has header_block_id
        header_id = section.get('header_block_id')
        if not header_id:
            # Try to find matching header block
            header_id = _find_header_block_for_section(section, header_blocks)
        section_header_ids[section['order_index']] = header_id

    # Build list of (header_block_id, section) tuples for sections with headers
    section_boundaries = []
    for section in sorted_sections:
        header_id = section_header_ids[section['order_index']]
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
        elif section_boundaries:
            # Block sits before the first matched header (e.g. cover-page form
            # fields, document subject line). Attach to the first section so
            # this content lands somewhere with a real heading instead of
            # leaking into a downstream level-2 chunk via page-based fallback.
            # Note: section_boundaries is sorted by header_block_id ascending,
            # so [0] is the earliest header in the document — typically the
            # chapter (level 1) when one exists, but otherwise the first
            # in-document section, which is still the right home for content
            # that precedes everything else.
            assigned_section = section_boundaries[0][1]

        # Fallback: page-based assignment for blocks before any header
        # or when header matching fails. The boundary walk relies on block_id
        # reflecting document position, but Docling stores tables and texts in
        # separate arrays so table block_ids are always > all text block_ids —
        # tables therefore always land here regardless of their true position.
        if assigned_section is None and page in page_sections:
            candidates = page_sections[page]
            if candidates:
                block_start, block_end = _block_page_span(block)

                # Prefer sections whose own page range fully contains the
                # block's effective span. Critical for multi-page merged
                # tables: a 10-page table starting on page 3 should land in
                # the section that spans pages 3-13, not in a single-page
                # section that also starts on page 3.
                valid_candidates = [
                    s for s in candidates
                    if s['page_start'] <= block_start
                ]
                if valid_candidates:
                    # Sort priority — chosen so a multi-page merged table lands
                    # in the topic that owns its full page span, but a level-1
                    # chapter doesn't trivially win just because it contains
                    # everything:
                    #   1. Deepest level first. Chapters span the whole doc
                    #      and would otherwise always "contain" any block.
                    #   2. Within a level, prefer sections that contain the
                    #      full block span over those that don't.
                    #   3. Tightest fit (smallest gap between section span
                    #      and block span). Picks Policy History (3-13) over
                    #      a nearby single-page section for a 3-13 table.
                    #   4. Latest page_start as final tiebreaker.
                    block_size = block_end - block_start
                    valid_candidates.sort(key=lambda s: (
                        -s['level'],
                        0 if s['page_end'] >= block_end else 1,
                        abs((s['page_end'] - s['page_start']) - block_size),
                        -s['page_start'],
                    ))
                    assigned_section = valid_candidates[0]

        if assigned_section:
            section_key = assigned_section['order_index']
            if section_key not in mapping:
                mapping[section_key] = []
            mapping[section_key].append(block_id)
        else:
            orphaned_blocks += 1
            logger.debug(f"Orphaned block {block_id} on page {page}: {block.get('block_type')}")

    logger.info(f"Assigned {sum(len(ids) for ids in mapping.values())} blocks to {len(mapping)} sections")
    if orphaned_blocks > 0:
        logger.warning(f"{orphaned_blocks} blocks could not be assigned to any section")

    return mapping


__all__ = [
    'assign_blocks_to_sections',
]
