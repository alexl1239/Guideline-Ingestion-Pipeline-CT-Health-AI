"""
Text Normalization for Cleanup (Step 4)

Functions for cleaning and normalizing markdown content from raw blocks.
Preserves clinical accuracy while standardizing formatting.

Tables are expected to have been linearized by Step 3 first — clean_block()
reads raw_blocks.text_content for table blocks. If text_content is empty,
the raw markdown is passed through and a warning is logged.
"""

import re
from typing import Dict, Any, Optional

from src.utils.logging_config import logger


# Block types to filter out (noise)
# - page_header/page_footer: running headers/footers with no clinical content
# - document_index: TOC navigation blocks; garbled by Docling (duplicate columns,
#   dotted leaders, missing spaces) and add no clinical value to RAG chunks
# - section_header: structural markers already captured in the sections table;
#   headings are explicitly prepended from sections metadata in build_section_content(),
#   so including the raw block would duplicate them in chunk content
NOISE_BLOCK_TYPES = {'page_header', 'page_footer', 'document_index', 'section_header'}

# Bullet character normalization mapping
BULLET_CHARS = {
    '•': '-',
    '◦': '-',
    '–': '-',
    '—': '-',
    '∙': '-',
    '●': '-',
    '○': '-',
    '■': '-',
    '□': '-',
    '▪': '-',
    '▸': '-',
    '▹': '-',
    '►': '-',
    '▻': '-',
}


def normalize_bullets(text: str) -> str:
    """
    Normalize bullet characters to consistent '- ' format.

    Converts various Unicode bullet characters (•, ◦, –, etc.) to standard
    markdown bullets while preserving indentation.

    Args:
        text: Text with various bullet formats

    Returns:
        Text with normalized bullets

    Example:
        >>> normalize_bullets("  • First item\\n  ◦ Second item")
        "  - First item\\n  - Second item"
    """
    if not text:
        return text

    for char, replacement in BULLET_CHARS.items():
        # Replace bullet followed by space or at start of line
        text = re.sub(
            rf'^(\s*){re.escape(char)}(\s*)',
            rf'\1{replacement} ',
            text,
            flags=re.MULTILINE
        )

    return text


def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace: collapse 3+ newlines to max 2, trim trailing spaces.

    Ensures consistent spacing without losing paragraph boundaries.

    Args:
        text: Text with irregular whitespace

    Returns:
        Text with normalized whitespace

    Example:
        >>> normalize_whitespace("Line 1\\n\\n\\n\\nLine 2  ")
        "Line 1\\n\\nLine 2"
    """
    if not text:
        return text

    # Collapse 3+ consecutive newlines to exactly 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Trim trailing spaces on each line
    text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)

    # Ensure consistent line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    return text.strip()


def normalize_markdown(text: str) -> str:
    """
    Apply all markdown normalization rules.

    Combines bullet normalization and whitespace normalization.

    Args:
        text: Raw markdown text

    Returns:
        Normalized markdown

    Example:
        >>> normalize_markdown("  • Item\\n\\n\\n\\nNext  ")
        "  - Item\\n\\nNext"
    """
    if not text:
        return ""

    text = normalize_bullets(text)
    text = normalize_whitespace(text)

    return text


def create_figure_placeholder(caption: Optional[str] = None) -> str:
    """
    Create a placeholder for figure/image content.

    Figures are not processed in current version but marked for context.

    Args:
        caption: Optional caption text

    Returns:
        Figure placeholder string

    Example:
        >>> create_figure_placeholder("Clinical workflow diagram")
        "\\n\\n[FIGURE: Clinical workflow diagram]\\n\\n"

        >>> create_figure_placeholder()
        "\\n\\n[FIGURE]\\n\\n"
    """
    if caption and caption.strip():
        return f"\n\n[FIGURE: {caption.strip()}]\n\n"
    return "\n\n[FIGURE]\n\n"


def clean_block(block: Dict[str, Any]) -> Optional[str]:
    """
    Clean and normalize a single raw block.

    Applies appropriate cleaning based on block type. Filters out noise blocks
    (page headers/footers) and handles tables, figures, and text differently.

    Args:
        block: Raw block dict with block_type, markdown_content, text_content

    Returns:
        Cleaned markdown string, or None if block should be skipped

    Block Types:
        - page_header, page_footer: Filtered (returns None)
        - table: Wrapped with [TABLE] markers
        - figure, picture: Converted to placeholder
        - caption: Normalized but preserved
        - text, paragraph, etc.: Normalized markdown

    Example:
        >>> block = {
        ...     'block_type': 'text',
        ...     'markdown_content': '  • First item\\n\\n\\n\\n  • Second item  '
        ... }
        >>> clean_block(block)
        '  - First item\\n\\n  - Second item'
    """
    block_type = block.get('block_type', '')

    # Skip noise blocks
    if block_type in NOISE_BLOCK_TYPES:
        logger.debug(f"Filtering out noise block: {block_type}")
        return None

    # Get content (prefer markdown over text)
    content = block.get('markdown_content') or block.get('text_content') or ''
    if not content.strip():
        logger.debug(f"Skipping empty block (type: {block_type})")
        return None

    # Handle different block types
    if block_type == 'table':
        # Step 3 (table linearization) writes prose into text_content. We use
        # that when present. If it's empty, Step 3 was skipped or failed for
        # this block — fall back to the raw markdown so chunks still build,
        # but log so the operator sees it.
        linearized = block.get('text_content', '').strip() if block.get('text_content') else ''
        if linearized:
            logger.debug(f"Using linearized table content (length: {len(linearized)})")
            return normalize_markdown(linearized)
        logger.warning(
            f"Table block has no linearized text_content — "
            f"falling back to raw markdown. Did Step 3 run?"
        )
        return normalize_markdown(content)

    if block_type in ('figure', 'picture'):
        # Docling extracts captions as dedicated adjacent 'caption' blocks.
        # Any text on the figure element itself is OCR'd from inside the image
        # (step-number labels, box text, etc.) — not a true caption.
        # Discard it and let the neighbouring caption block provide context.
        logger.debug("Creating figure placeholder (caption supplied by adjacent caption block)")
        return create_figure_placeholder()

    if block_type == 'caption':
        # Keep captions as-is but normalize
        return normalize_markdown(content)

    # Default: normalize markdown for text blocks
    return normalize_markdown(content)
