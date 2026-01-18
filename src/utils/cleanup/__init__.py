"""
Cleanup Utilities (Step 3)

Modular utilities for text normalization, chunking, and database operations
used in Step 3: Cleanup and Parent Chunk Construction.
"""

# Text normalization
from src.utils.cleanup.text_normalizer import (
    NOISE_BLOCK_TYPES,
    BULLET_CHARS,
    normalize_bullets,
    normalize_whitespace,
    normalize_markdown,
    wrap_table_content,
    create_figure_placeholder,
    clean_block,
)

# Chunking logic
from src.utils.cleanup.chunker import (
    build_section_content,
    split_large_unit,
    create_parent_chunks,
)

# Database operations
from src.utils.cleanup.database import (
    get_level2_sections,
    get_section_with_descendants,
    get_raw_blocks_for_sections,
    get_subsections_for_section,
    check_existing_parent_chunks,
    delete_parent_chunks_for_document,
    insert_parent_chunks_batch,
    export_parent_chunks_to_markdown,
    get_document_id,
)


__all__ = [
    # Text normalization
    'NOISE_BLOCK_TYPES',
    'BULLET_CHARS',
    'normalize_bullets',
    'normalize_whitespace',
    'normalize_markdown',
    'wrap_table_content',
    'create_figure_placeholder',
    'clean_block',
    # Chunking
    'build_section_content',
    'split_large_unit',
    'create_parent_chunks',
    # Database
    'get_level2_sections',
    'get_section_with_descendants',
    'get_raw_blocks_for_sections',
    'get_subsections_for_section',
    'check_existing_parent_chunks',
    'delete_parent_chunks_for_document',
    'insert_parent_chunks_batch',
    'export_parent_chunks_to_markdown',
    'get_document_id',
]
