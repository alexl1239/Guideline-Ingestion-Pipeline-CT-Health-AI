"""
Parent Chunk Construction for Cleanup (Step 3)

Functions for building and splitting content units into parent chunks.
Target: 1000-1500 tokens per parent chunk, hard max 2000 tokens.
"""

import re
from typing import Dict, List, Any, Tuple
import tiktoken

from src.config import (
    PARENT_TOKEN_TARGET,
    PARENT_TOKEN_MIN,
    PARENT_TOKEN_HARD_MAX,
)
from src.utils.cleanup.text_normalizer import clean_block
from src.utils.cleanup.database import (
    get_section_with_descendants,
    get_raw_blocks_for_sections,
    get_subsections_for_section,
)
from src.utils.tokenization import count_tokens
from src.utils.logging_config import logger


def build_section_content(
    section: Dict[str, Any],
    tokenizer: tiktoken.Encoding
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Build the complete cleaned content for a level-2 section.

    Concatenates the section's own blocks plus all descendant subsection blocks
    in order, with subsection headings inserted as markdown headers.

    Args:
        section: Level-2 section dict (id, heading, heading_path, etc.)
        tokenizer: Tiktoken tokenizer for token counting

    Returns:
        Tuple of (full_content_string, list_of_subsection_units)
        Each unit is {'heading': str, 'heading_path': str, 'content': str,
                      'tokens': int, 'section_id': int}

    Example:
        >>> section = {'id': 42, 'heading': 'Malaria', 'heading_path': '...'}
        >>> full_content, units = build_section_content(section, tokenizer)
        >>> len(units)  # Definition, Management, etc.
        5
    """
    section_id = section['id']
    heading_path = section['heading_path']

    logger.debug(f"Building content for section {section_id}: {section['heading']}")

    # Get all descendant section IDs
    all_section_ids = get_section_with_descendants(section_id)

    # Get all raw blocks
    blocks = get_raw_blocks_for_sections(all_section_ids)
    logger.debug(f"Processing {len(blocks)} blocks for section {section_id}")

    # Get subsections for splitting
    subsections = get_subsections_for_section(section_id)

    # Build content by subsection units for smart splitting
    units = []

    # First, get blocks that belong directly to the level-2 section (not subsections)
    subsection_ids = {s['id'] for s in subsections}
    main_blocks = [b for b in blocks if b['section_id'] == section_id]

    # Clean main section blocks
    main_content_parts = []
    blocks_cleaned = 0
    blocks_skipped = 0

    for block in main_blocks:
        cleaned = clean_block(block)
        if cleaned:
            main_content_parts.append(cleaned)
            blocks_cleaned += 1
        else:
            blocks_skipped += 1

    if main_content_parts:
        main_content = '\n\n'.join(main_content_parts)
        main_tokens = count_tokens(main_content, tokenizer)
        units.append({
            'heading': section['heading'],
            'heading_path': heading_path,
            'content': main_content,
            'tokens': main_tokens,
            'section_id': section_id,
        })
        logger.debug(f"Main section content: {blocks_cleaned} blocks, {main_tokens} tokens")

    if blocks_skipped > 0:
        logger.debug(f"Skipped {blocks_skipped} noise/empty blocks in main section")

    # Process each subsection
    for subsection in subsections:
        sub_id = subsection['id']
        sub_blocks = [b for b in blocks if b['section_id'] == sub_id]

        if not sub_blocks:
            logger.debug(f"Skipping empty subsection: {subsection['heading']}")
            continue

        # Build subsection heading
        sub_heading = subsection['heading']
        level = subsection['level']
        markdown_heading = '#' * min(level, 6) + ' ' + sub_heading

        # Clean subsection blocks
        sub_content_parts = [markdown_heading]
        sub_cleaned = 0
        sub_skipped = 0

        for block in sub_blocks:
            cleaned = clean_block(block)
            if cleaned:
                sub_content_parts.append(cleaned)
                sub_cleaned += 1
            else:
                sub_skipped += 1

        sub_content = '\n\n'.join(sub_content_parts)
        sub_tokens = count_tokens(sub_content, tokenizer)

        units.append({
            'heading': sub_heading,
            'heading_path': subsection['heading_path'],
            'content': sub_content,
            'tokens': sub_tokens,
            'section_id': sub_id,
        })

        logger.debug(
            f"Subsection '{sub_heading}': {sub_cleaned} blocks, {sub_tokens} tokens "
            f"({sub_skipped} skipped)"
        )

    # Build full content
    full_content = '\n\n'.join(u['content'] for u in units)
    total_tokens = sum(u['tokens'] for u in units)

    logger.debug(
        f"Section {section_id} complete: {len(units)} units, "
        f"{total_tokens} total tokens"
    )

    return full_content, units


def split_large_unit(
    unit: Dict[str, Any],
    tokenizer: tiktoken.Encoding,
    max_tokens: int = PARENT_TOKEN_HARD_MAX
) -> List[Dict[str, Any]]:
    """
    Split a single unit that exceeds max_tokens at paragraph boundaries.

    Attempts to split at paragraph boundaries (double newline) first.
    If a single paragraph exceeds max_tokens, splits at line boundaries.

    Args:
        unit: Unit dict with 'content', 'tokens', 'heading', 'heading_path', 'section_id'
        tokenizer: Tiktoken tokenizer
        max_tokens: Maximum tokens per chunk (default: PARENT_TOKEN_HARD_MAX)

    Returns:
        List of smaller unit dicts

    Example:
        >>> large_unit = {'content': '...' * 5000, 'tokens': 3000, ...}
        >>> small_units = split_large_unit(large_unit, tokenizer, 2000)
        >>> all(u['tokens'] <= 2000 for u in small_units)
        True
    """
    content = unit['content']
    heading = unit['heading']
    heading_path = unit['heading_path']
    section_id = unit['section_id']

    logger.warning(
        f"Splitting large unit '{heading}' ({unit['tokens']} tokens > {max_tokens})"
    )

    # Split by paragraphs (double newline)
    paragraphs = re.split(r'\n\n+', content)

    result_units = []
    current_parts = []
    current_tokens = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_tokens = count_tokens(para, tokenizer)

        # If single paragraph exceeds max, split by lines
        if para_tokens > max_tokens:
            logger.warning(
                f"Single paragraph in '{heading}' exceeds {max_tokens} tokens "
                f"({para_tokens}), splitting by lines"
            )

            # Flush current parts first
            if current_parts:
                result_units.append({
                    'heading': heading,
                    'heading_path': heading_path,
                    'content': '\n\n'.join(current_parts),
                    'tokens': current_tokens,
                    'section_id': section_id,
                })
                current_parts = []
                current_tokens = 0

            # Split large paragraph by lines
            lines = para.split('\n')
            line_parts = []
            line_tokens = 0

            for line in lines:
                line_tok = count_tokens(line + '\n', tokenizer)
                if line_tokens + line_tok > max_tokens and line_parts:
                    result_units.append({
                        'heading': heading,
                        'heading_path': heading_path,
                        'content': '\n'.join(line_parts),
                        'tokens': line_tokens,
                        'section_id': section_id,
                    })
                    line_parts = []
                    line_tokens = 0

                line_parts.append(line)
                line_tokens += line_tok

            if line_parts:
                result_units.append({
                    'heading': heading,
                    'heading_path': heading_path,
                    'content': '\n'.join(line_parts),
                    'tokens': line_tokens,
                    'section_id': section_id,
                })
        else:
            # Normal paragraph
            if current_tokens + para_tokens > max_tokens and current_parts:
                result_units.append({
                    'heading': heading,
                    'heading_path': heading_path,
                    'content': '\n\n'.join(current_parts),
                    'tokens': current_tokens,
                    'section_id': section_id,
                })
                current_parts = []
                current_tokens = 0

            current_parts.append(para)
            current_tokens += para_tokens

    # Flush remaining
    if current_parts:
        result_units.append({
            'heading': heading,
            'heading_path': heading_path,
            'content': '\n\n'.join(current_parts),
            'tokens': current_tokens,
            'section_id': section_id,
        })

    logger.info(f"Split '{heading}' into {len(result_units)} smaller units")
    return result_units


def create_parent_chunks(
    section: Dict[str, Any],
    units: List[Dict[str, Any]],
    tokenizer: tiktoken.Encoding,
    target_min: int = PARENT_TOKEN_MIN,
    target_max: int = PARENT_TOKEN_TARGET,
    hard_max: int = PARENT_TOKEN_HARD_MAX,
) -> List[Dict[str, Any]]:
    """
    Create parent chunks by greedily packing units.

    Target range: 1000-1500 tokens; hard cap 2000 tokens.
    Prefers splitting at subsection boundaries.

    Algorithm:
    1. Split any units exceeding hard_max
    2. Greedily pack units into chunks targeting target_max tokens
    3. Merge small trailing chunks if possible

    Args:
        section: Level-2 section dict (id, heading, heading_path, page_start, page_end)
        units: List of content units (subsections)
        tokenizer: Tiktoken tokenizer
        target_min: Minimum target tokens (default: 1000)
        target_max: Maximum target tokens, soft limit (default: 1500)
        hard_max: Hard maximum tokens, never exceed (default: 2000)

    Returns:
        List of parent chunk dicts with section_id, heading_path, content,
        token_count, page_start, page_end, order_index

    Example:
        >>> chunks = create_parent_chunks(section, units, tokenizer)
        >>> all(c['token_count'] <= 2000 for c in chunks)
        True
        >>> statistics.median([c['token_count'] for c in chunks])
        1522
    """
    if not units:
        logger.debug(f"No units for section {section['id']}, returning empty chunks")
        return []

    # First, split any units that exceed hard_max
    split_units = []
    units_split = 0
    for unit in units:
        if unit['tokens'] > hard_max:
            split_result = split_large_unit(unit, tokenizer, hard_max)
            split_units.extend(split_result)
            units_split += 1
        else:
            split_units.append(unit)

    if units_split > 0:
        logger.info(
            f"Split {units_split} large units in section {section['id']} "
            f"(now {len(split_units)} units)"
        )

    # Greedy packing
    chunks = []
    current_units = []
    current_tokens = 0

    for unit in split_units:
        unit_tokens = unit['tokens']

        # If adding this unit would exceed hard_max, finalize current chunk
        if current_tokens + unit_tokens > hard_max and current_units:
            chunks.append({
                'section_id': section['id'],
                'heading_path': section['heading_path'],
                'content': '\n\n'.join(u['content'] for u in current_units),
                'token_count': current_tokens,
                'units': current_units,
            })
            current_units = []
            current_tokens = 0

        # Add unit to current chunk
        current_units.append(unit)
        current_tokens += unit_tokens

        # If we've reached target range, finalize (but allow more if under hard_max)
        if current_tokens >= target_max:
            chunks.append({
                'section_id': section['id'],
                'heading_path': section['heading_path'],
                'content': '\n\n'.join(u['content'] for u in current_units),
                'token_count': current_tokens,
                'units': current_units,
            })
            current_units = []
            current_tokens = 0

    # Finalize remaining
    if current_units:
        # Try to merge with previous chunk if both are small
        if chunks and current_tokens < target_min and chunks[-1]['token_count'] < target_min:
            last_chunk = chunks[-1]
            merged_tokens = last_chunk['token_count'] + current_tokens

            if merged_tokens <= hard_max:
                logger.debug(
                    f"Merging small chunks: {last_chunk['token_count']} + {current_tokens} "
                    f"= {merged_tokens} tokens"
                )
                last_chunk['content'] = (
                    last_chunk['content'] + '\n\n' +
                    '\n\n'.join(u['content'] for u in current_units)
                )
                last_chunk['token_count'] = merged_tokens
                last_chunk['units'].extend(current_units)
            else:
                logger.debug(
                    f"Cannot merge small chunks (would exceed hard_max: {merged_tokens})"
                )
                chunks.append({
                    'section_id': section['id'],
                    'heading_path': section['heading_path'],
                    'content': '\n\n'.join(u['content'] for u in current_units),
                    'token_count': current_tokens,
                    'units': current_units,
                })
        else:
            chunks.append({
                'section_id': section['id'],
                'heading_path': section['heading_path'],
                'content': '\n\n'.join(u['content'] for u in current_units),
                'token_count': current_tokens,
                'units': current_units,
            })

    # Assign order indices and compute page ranges
    for idx, chunk in enumerate(chunks):
        chunk['order_index'] = idx

        # Use section's page range (would need block-level page tracking for precision)
        chunk['page_start'] = section.get('page_start')
        chunk['page_end'] = section.get('page_end')

        # Clean up internal tracking
        del chunk['units']

    logger.debug(
        f"Created {len(chunks)} parent chunks for section {section['id']} "
        f"(tokens: {[c['token_count'] for c in chunks]})"
    )

    return chunks
