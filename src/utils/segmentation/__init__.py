"""
Segmentation Utilities (Step 2)

Utilities for structural segmentation and hierarchy building.
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

from src.utils.segmentation.toc_parser import (
    extract_toc_from_docling,
    parse_toc_entry,
    infer_toc_level,
    validate_toc_entries,
    get_toc_summary,
)

from src.utils.segmentation.hierarchy_builder import (
    identify_chapters,
    identify_diseases_from_toc,
    identify_subsections_from_toc_and_headers,
    build_heading_path,
    assign_blocks_to_sections,
    build_complete_hierarchy,
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
    # toc_parser
    'extract_toc_from_docling',
    'parse_toc_entry',
    'infer_toc_level',
    'validate_toc_entries',
    'get_toc_summary',
    # hierarchy_builder
    'identify_chapters',
    'identify_diseases_from_toc',
    'identify_subsections_from_toc_and_headers',
    'build_heading_path',
    'assign_blocks_to_sections',
    'build_complete_hierarchy',
]
