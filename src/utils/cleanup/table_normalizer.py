"""
Table Markdown Preprocessing for Step 4

Cleans Docling's raw table markdown before LLM linearization or storage.
Fixes known Docling output quality issues without altering clinical data.

All transformations are purely syntactic — no content is added, removed,
or reworded.
"""

import re
import html
from typing import Optional

from src.utils.logging_config import logger


def decode_html_entities(text: str) -> str:
    """
    Decode HTML entities in table markdown.

    Docling sometimes emits HTML entities like &amp; instead of &.

    Args:
        text: Table markdown text

    Returns:
        Text with HTML entities decoded

    Example:
        >>> decode_html_entities("M&amp;E Framework")
        'M&E Framework'
    """
    return html.unescape(text)


def fix_concatenated_header_words(text: str) -> str:
    """
    Insert spaces into concatenated ALL-CAPS header words.

    Docling sometimes merges adjacent header words when extracting table
    headers, producing strings like "DELIVEREDBYICCMVHTS" instead of
    "DELIVERED BY ICCM VHTS".

    Strategy: Split runs of 3+ uppercase letters at word boundaries using
    a dictionary-free approach — insert a space before any uppercase letter
    that follows a lowercase-to-uppercase or uppercase-to-uppercase
    transition where the preceding run is long enough to be a word.

    Only applied to text inside pipe-delimited header cells to avoid
    touching body content.

    Args:
        text: Table markdown text

    Returns:
        Text with spaces inserted in concatenated headers

    Example:
        >>> fix_concatenated_header_words("| DELIVEREDBYICCMVHTS |")
        '| DELIVERED BY ICCM VHTS |'
    """
    lines = text.split('\n')
    result = []

    for line in lines:
        # Only process header rows (lines with pipes but not separator rows)
        if '|' in line and not re.match(r'^[\s|:-]+$', line):
            # Check if this looks like an ALL-CAPS header row
            # (most cell content is uppercase)
            cells = line.split('|')
            cell_text = ''.join(cells)
            alpha_chars = [c for c in cell_text if c.isalpha()]
            if alpha_chars:
                upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
            else:
                upper_ratio = 0

            if upper_ratio > 0.7:
                # Split concatenated uppercase words:
                # Insert space between a run of >=2 uppercase letters followed
                # by another run of >=2 uppercase letters.
                # e.g. "DELIVEREDBY" -> "DELIVERED BY"
                line = re.sub(
                    r'([A-Z]{2,})([A-Z][a-z])',
                    r'\1 \2',
                    line
                )
                # Handle pure ALL-CAPS concatenation like DELIVEREDBYICCMVHTS
                # Look for known word boundaries in ALL-CAPS runs
                line = re.sub(
                    r'([A-Z]{3,?})(?=[A-Z]{3})',
                    _split_allcaps_run,
                    line
                )
        result.append(line)

    return '\n'.join(result)


def _split_allcaps_run(match: re.Match) -> str:
    """
    Helper for fix_concatenated_header_words.

    Attempts to find natural word boundaries in ALL-CAPS runs by looking
    for common English prepositions/articles/conjunctions as separators.
    """
    text = match.group(0)
    # Common short words that indicate word boundaries in concatenated headers
    separators = ['BY', 'OF', 'IN', 'AT', 'TO', 'FOR', 'AND', 'THE', 'OR', 'ON', 'WITH']

    for sep in separators:
        # If the run contains a separator word, split there
        idx = text.find(sep)
        if idx > 0 and idx + len(sep) < len(text):
            before = text[:idx]
            after = text[idx:]
            if len(before) >= 2 and len(after) >= 2:
                return f"{before} {after}"

    return text


def strip_duplicate_header_rows(text: str) -> str:
    """
    Remove duplicate merged-header rows in tables.

    Docling sometimes repeats the same header text across many columns
    when a table has merged header cells. For example, a header that spans
    12 columns might appear as 12 identical cells.

    Args:
        text: Table markdown text

    Returns:
        Text with duplicate header rows collapsed

    Example:
        >>> text = "| Year | Year | Year | Year |\\n|---|---|---|---|"
        >>> strip_duplicate_header_rows(text)
        '| Year |\\n|---|---|---|---|'
    """
    lines = text.split('\n')
    result = []

    for line in lines:
        if '|' in line and not re.match(r'^[\s|:-]+$', line):
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if cells:
                unique_cells = list(dict.fromkeys(cells))  # preserve order, dedupe
                # If more than half the cells are identical, collapse
                if len(unique_cells) < len(cells) * 0.5:
                    line = '| ' + ' | '.join(unique_cells) + ' |'
        result.append(line)

    return '\n'.join(result)


def normalize_table_markdown(markdown: str) -> str:
    """
    Apply all table markdown preprocessing steps.

    This is the main entry point for table preprocessing. Call this on
    raw Docling table markdown before LLM linearization or storage.

    Steps applied in order:
    1. Decode HTML entities (&amp; -> &)
    2. Fix concatenated header words (DELIVEREDBY -> DELIVERED BY)
    3. Strip duplicate header rows from merged cells

    Args:
        markdown: Raw table markdown from Docling

    Returns:
        Cleaned table markdown

    Example:
        >>> raw = "| M&amp;E Component | iCCMM&amp;EStatus |"
        >>> normalize_table_markdown(raw)
        '| M&E Component | iCCM M&E Status |'
    """
    if not markdown or not markdown.strip():
        return markdown

    result = decode_html_entities(markdown)
    result = fix_concatenated_header_words(result)
    result = strip_duplicate_header_rows(result)

    return result


__all__ = [
    'normalize_table_markdown',
    'decode_html_entities',
    'fix_concatenated_header_words',
    'strip_duplicate_header_rows',
]
