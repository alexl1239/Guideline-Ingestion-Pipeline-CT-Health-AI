"""
Segmentation Utilities (Step 2)

Utilities for structural segmentation and hierarchy building.

This module uses Docling's native hierarchy detection for robust section
extraction without fragile ToC parsing.
"""

from src.utils.segmentation.heading_patterns import (
    extract_numbered_heading,
    infer_level_from_numbering,
    is_chapter_heading,
    is_standard_subsection,
    score_heading_candidate,
    normalize_heading_text,
    get_heading_confidence_category,
    STANDARD_SUBSECTIONS,
)

# Native hierarchy extraction
from src.utils.segmentation.native_hierarchy import (
    extract_native_hierarchy,
    build_section_tree,
    assign_page_ranges,
    build_heading_paths,
    validate_hierarchy,
    get_hierarchy_summary,
)

# Block assignment utility (still needed for assigning blocks to sections)
from src.utils.segmentation.hierarchy_builder import (
    assign_blocks_to_sections,
)

__all__ = [
    # heading_patterns
    'extract_numbered_heading',
    'infer_level_from_numbering',
    'is_chapter_heading',
    'is_standard_subsection',
    'score_heading_candidate',
    'normalize_heading_text',
    'get_heading_confidence_category',
    'STANDARD_SUBSECTIONS',
    # native_hierarchy
    'extract_native_hierarchy',
    'build_section_tree',
    'assign_page_ranges',
    'build_heading_paths',
    'validate_hierarchy',
    'get_hierarchy_summary',
    # hierarchy_builder (only assign_blocks_to_sections is still used)
    'assign_blocks_to_sections',
]
