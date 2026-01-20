"""
Text Normalization for Cleanup (Step 3)

Functions for cleaning and normalizing markdown content from raw blocks.
Preserves clinical accuracy while standardizing formatting.
"""

import re
from typing import Dict, Any, Optional

from src.utils.logging_config import logger


# Block types to filter out (noise)
NOISE_BLOCK_TYPES = {'page_header', 'page_footer'}

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


def wrap_table_content(text: str) -> str:
    """
    Wrap table markdown with clear fences for later processing.

    Tables are marked for special handling in downstream steps (Step 4).

    Args:
        text: Table markdown content

    Returns:
        Wrapped table content

    Example:
        >>> wrap_table_content("| Col1 | Col2 |")
        "\\n\\n[TABLE]\\n| Col1 | Col2 |\\n[/TABLE]\\n\\n"
    """
    return f"\n\n[TABLE]\n{text.strip()}\n[/TABLE]\n\n"


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
        logger.debug(f"Wrapping table block (length: {len(content)})")
        return wrap_table_content(content)

    if block_type in ('figure', 'picture'):
        # Try to extract caption from content or metadata
        caption = content.strip() if len(content.strip()) < 200 else None
        logger.debug(f"Creating figure placeholder (caption: {bool(caption)})")
        return create_figure_placeholder(caption)

    if block_type == 'caption':
        # Keep captions as-is but normalize
        return normalize_markdown(content)

    # Default: normalize markdown for text blocks
    return normalize_markdown(content)
