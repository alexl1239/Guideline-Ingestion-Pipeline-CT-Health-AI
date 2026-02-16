"""
Segmentation Utilities (Step 2)

Utilities for structural segmentation and hierarchy building.

This module uses Docling's native hierarchy detection for robust, document-agnostic
section extraction. Works across different document types without requiring
document-specific patterns or subsection lists.
"""

# Native hierarchy extraction (primary approach - document-agnostic)
from src.utils.segmentation.native_hierarchy import (
    extract_native_hierarchy,
    build_section_tree,
    assign_page_ranges,
    build_heading_paths,
    validate_hierarchy,
    get_hierarchy_summary,
)

# Block assignment utility
from src.utils.segmentation.hierarchy_builder import (
    assign_blocks_to_sections,
)

__all__ = [
    # native_hierarchy (primary hierarchy extraction)
    'extract_native_hierarchy',
    'build_section_tree',
    'assign_page_ranges',
    'build_heading_paths',
    'validate_hierarchy',
    'get_hierarchy_summary',
    # hierarchy_builder (block assignment only)
    'assign_blocks_to_sections',
]
