"""
STEP 3 — CLEANUP AND PARENT CHUNK CONSTRUCTION

Removes noise, normalizes markdown content, and constructs parent chunks
from raw blocks for RAG retrieval.

Process:
1. Load sections and raw_blocks from database
2. Filter out page headers/footers (block_type in {page_header, page_footer})
3. Normalize markdown: bullets, whitespace, heading levels
4. Insert figure/caption placeholders for clinically important images
5. Concatenate cleaned blocks per level-2 section (disease/topic)
6. Split into parent chunks targeting 1000-1500 tokens, hard max 2000
7. Write parent chunks to database with token counts

Input: Populated raw_blocks table with section_id assignments (from Step 2)
Output: Populated parent_chunks table

Transaction Boundary: Per batch of 10 sections (as per CLAUDE.md)
"""

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import tiktoken

from src.config import (
    DATABASE_PATH,
    PARENT_TOKEN_TARGET,
    PARENT_TOKEN_MIN,
    PARENT_TOKEN_HARD_MAX,
    CLEANUP_BATCH_SIZE,
    TOKEN_ENCODING,
    EXPORTS_DIR,
)
from src.database import get_connection
from src.utils.logging_config import logger, setup_logger


class CleanupError(Exception):
    """Raised when cleanup and parent chunk formation fails."""
    pass


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


def get_tokenizer():
    """Get tiktoken tokenizer for cl100k_base encoding."""
    return tiktoken.get_encoding(TOKEN_ENCODING)


def count_tokens(text: str, tokenizer=None) -> int:
    """
    Count tokens in text using tiktoken cl100k_base encoding.

    Args:
        text: Text to count tokens in
        tokenizer: Optional pre-initialized tokenizer

    Returns:
        Token count
    """
    if tokenizer is None:
        tokenizer = get_tokenizer()
    return len(tokenizer.encode(text))


def normalize_bullets(text: str) -> str:
    """
    Normalize bullet characters to consistent '- ' format.

    Args:
        text: Text with various bullet formats

    Returns:
        Text with normalized bullets
    """
    for char, replacement in BULLET_CHARS.items():
        # Replace bullet followed by space or at start of line
        text = re.sub(rf'^(\s*){re.escape(char)}(\s*)', rf'\1{replacement} ', text, flags=re.MULTILINE)
    return text


def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace: collapse 3+ newlines to max 2, trim trailing spaces.

    Args:
        text: Text with irregular whitespace

    Returns:
        Text with normalized whitespace
    """
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

    Args:
        text: Raw markdown text

    Returns:
        Normalized markdown
    """
    if not text:
        return ""

    text = normalize_bullets(text)
    text = normalize_whitespace(text)

    return text


def wrap_table_content(text: str) -> str:
    """
    Wrap table markdown with clear fences for later processing.

    Args:
        text: Table markdown content

    Returns:
        Wrapped table content
    """
    return f"\n\n[TABLE]\n{text.strip()}\n[/TABLE]\n\n"


def create_figure_placeholder(caption: Optional[str] = None) -> str:
    """
    Create a placeholder for figure/image content.

    Args:
        caption: Optional caption text

    Returns:
        Figure placeholder string
    """
    if caption and caption.strip():
        return f"\n\n[FIGURE: {caption.strip()}]\n\n"
    return "\n\n[FIGURE]\n\n"


def clean_block(block: Dict[str, Any]) -> Optional[str]:
    """
    Clean and normalize a single raw block.

    Args:
        block: Raw block dict with block_type, markdown_content, text_content

    Returns:
        Cleaned markdown string, or None if block should be skipped
    """
    block_type = block.get('block_type', '')

    # Skip noise blocks
    if block_type in NOISE_BLOCK_TYPES:
        return None

    # Get content (prefer markdown over text)
    content = block.get('markdown_content') or block.get('text_content') or ''
    if not content.strip():
        return None

    # Handle different block types
    if block_type == 'table':
        return wrap_table_content(content)

    if block_type in ('figure', 'picture'):
        # Try to extract caption from content or metadata
        caption = content.strip() if len(content.strip()) < 200 else None
        return create_figure_placeholder(caption)

    if block_type == 'caption':
        # Keep captions as-is but normalize
        return normalize_markdown(content)

    # Default: normalize markdown
    return normalize_markdown(content)


def get_level2_sections(document_id: str) -> List[Dict[str, Any]]:
    """
    Get all level-2 sections (disease/topic) for a document.

    Args:
        document_id: Document UUID

    Returns:
        List of section dicts with id, heading, heading_path, page_start, page_end, order_index
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, heading, heading_path, page_start, page_end, order_index
            FROM sections
            WHERE document_id = ? AND level = 2
            ORDER BY order_index
        """, (document_id,))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_section_with_descendants(section_id: int) -> List[int]:
    """
    Get a section and all its descendant section IDs.

    Args:
        section_id: Parent section ID

    Returns:
        List of section IDs including parent and all descendants
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get the section's heading_path
        cursor.execute("SELECT heading_path FROM sections WHERE id = ?", (section_id,))
        result = cursor.fetchone()
        if not result:
            return [section_id]

        heading_path = result[0]

        # Get all sections that start with this heading_path
        cursor.execute("""
            SELECT id FROM sections
            WHERE heading_path LIKE ? OR heading_path = ?
            ORDER BY order_index
        """, (heading_path + ' > %', heading_path))

        return [row[0] for row in cursor.fetchall()]


def get_raw_blocks_for_sections(section_ids: List[int]) -> List[Dict[str, Any]]:
    """
    Get all raw blocks for a list of sections, ordered by page and block ID.

    Args:
        section_ids: List of section IDs

    Returns:
        List of raw block dicts
    """
    if not section_ids:
        return []

    with get_connection() as conn:
        cursor = conn.cursor()

        placeholders = ','.join('?' * len(section_ids))
        cursor.execute(f"""
            SELECT id, section_id, block_type, text_content, markdown_content,
                   page_number, page_range, docling_level, metadata
            FROM raw_blocks
            WHERE section_id IN ({placeholders})
            ORDER BY page_number, id
        """, section_ids)

        return [dict(row) for row in cursor.fetchall()]


def get_subsections_for_section(section_id: int) -> List[Dict[str, Any]]:
    """
    Get immediate subsections (level >= 3) under a level-2 section.

    Args:
        section_id: Level-2 section ID

    Returns:
        List of subsection dicts with id, heading, heading_path, order_index
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get the section's heading_path
        cursor.execute("SELECT heading_path FROM sections WHERE id = ?", (section_id,))
        result = cursor.fetchone()
        if not result:
            return []

        heading_path = result[0]

        # Get all subsections (level >= 3)
        cursor.execute("""
            SELECT id, level, heading, heading_path, page_start, page_end, order_index
            FROM sections
            WHERE heading_path LIKE ? AND level >= 3
            ORDER BY order_index
        """, (heading_path + ' > %',))

        return [dict(row) for row in cursor.fetchall()]


def build_section_content(
    section: Dict[str, Any],
    tokenizer
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Build the complete cleaned content for a level-2 section.

    Concatenates the section's own blocks plus all descendant subsection blocks
    in order, with subsection headings inserted as markdown headers.

    Args:
        section: Level-2 section dict
        tokenizer: Tiktoken tokenizer

    Returns:
        Tuple of (full_content_string, list_of_subsection_units)
        Each unit is {'heading': str, 'content': str, 'tokens': int}
    """
    section_id = section['id']
    heading_path = section['heading_path']

    # Get all descendant section IDs
    all_section_ids = get_section_with_descendants(section_id)

    # Get all raw blocks
    blocks = get_raw_blocks_for_sections(all_section_ids)

    # Get subsections for splitting
    subsections = get_subsections_for_section(section_id)

    # Build content by subsection units for smart splitting
    units = []

    # First, get blocks that belong directly to the level-2 section (not subsections)
    subsection_ids = {s['id'] for s in subsections}
    main_blocks = [b for b in blocks if b['section_id'] == section_id]

    # Clean main section blocks
    main_content_parts = []
    for block in main_blocks:
        cleaned = clean_block(block)
        if cleaned:
            main_content_parts.append(cleaned)

    if main_content_parts:
        main_content = '\n\n'.join(main_content_parts)
        units.append({
            'heading': section['heading'],
            'heading_path': heading_path,
            'content': main_content,
            'tokens': count_tokens(main_content, tokenizer),
            'section_id': section_id,
        })

    # Process each subsection
    for subsection in subsections:
        sub_id = subsection['id']
        sub_blocks = [b for b in blocks if b['section_id'] == sub_id]

        if not sub_blocks:
            continue

        # Build subsection heading
        sub_heading = subsection['heading']
        level = subsection['level']
        markdown_heading = '#' * min(level, 6) + ' ' + sub_heading

        # Clean subsection blocks
        sub_content_parts = [markdown_heading]
        for block in sub_blocks:
            cleaned = clean_block(block)
            if cleaned:
                sub_content_parts.append(cleaned)

        sub_content = '\n\n'.join(sub_content_parts)
        units.append({
            'heading': sub_heading,
            'heading_path': subsection['heading_path'],
            'content': sub_content,
            'tokens': count_tokens(sub_content, tokenizer),
            'section_id': sub_id,
        })

    # Build full content
    full_content = '\n\n'.join(u['content'] for u in units)

    return full_content, units


def split_large_unit(
    unit: Dict[str, Any],
    tokenizer,
    max_tokens: int = PARENT_TOKEN_HARD_MAX
) -> List[Dict[str, Any]]:
    """
    Split a single unit that exceeds max_tokens at paragraph boundaries.

    Args:
        unit: Unit dict with 'content', 'tokens'
        tokenizer: Tiktoken tokenizer
        max_tokens: Maximum tokens per chunk

    Returns:
        List of smaller unit dicts
    """
    content = unit['content']
    heading = unit['heading']
    heading_path = unit['heading_path']
    section_id = unit['section_id']

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

    return result_units


def create_parent_chunks(
    section: Dict[str, Any],
    units: List[Dict[str, Any]],
    tokenizer,
    target_min: int = PARENT_TOKEN_MIN,
    target_max: int = PARENT_TOKEN_TARGET,
    hard_max: int = PARENT_TOKEN_HARD_MAX,
) -> List[Dict[str, Any]]:
    """
    Create parent chunks by greedily packing units.

    Target range: 1000-1500 tokens; hard cap 2000 tokens.
    Prefer splitting at subsection boundaries.

    Args:
        section: Level-2 section dict
        units: List of content units (subsections)
        tokenizer: Tiktoken tokenizer
        target_min: Minimum target tokens
        target_max: Maximum target tokens (soft limit)
        hard_max: Hard maximum tokens (never exceed)

    Returns:
        List of parent chunk dicts
    """
    if not units:
        return []

    # First, split any units that exceed hard_max
    split_units = []
    for unit in units:
        if unit['tokens'] > hard_max:
            split_units.extend(split_large_unit(unit, tokenizer, hard_max))
        else:
            split_units.append(unit)

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
                last_chunk['content'] = last_chunk['content'] + '\n\n' + '\n\n'.join(u['content'] for u in current_units)
                last_chunk['token_count'] = merged_tokens
                last_chunk['units'].extend(current_units)
            else:
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

        # Compute page range from units
        page_starts = []
        page_ends = []
        for unit in chunk.get('units', []):
            # Would need page info from blocks - for now we use section's page range
            pass

        # Use section's page range as fallback
        chunk['page_start'] = section.get('page_start')
        chunk['page_end'] = section.get('page_end')

        # Clean up internal tracking
        del chunk['units']

    return chunks


def check_existing_parent_chunks(document_id: str) -> int:
    """
    Check if parent chunks already exist for a document.

    Args:
        document_id: Document UUID

    Returns:
        Count of existing parent chunks
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM parent_chunks pc
            JOIN sections s ON pc.section_id = s.id
            WHERE s.document_id = ?
        """, (document_id,))
        return cursor.fetchone()[0]


def delete_parent_chunks_for_document(document_id: str) -> int:
    """
    Delete all parent chunks for a document.

    Args:
        document_id: Document UUID

    Returns:
        Number of chunks deleted
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get section IDs for this document
        cursor.execute("SELECT id FROM sections WHERE document_id = ?", (document_id,))
        section_ids = [row[0] for row in cursor.fetchall()]

        if not section_ids:
            return 0

        placeholders = ','.join('?' * len(section_ids))
        cursor.execute(f"""
            DELETE FROM parent_chunks
            WHERE section_id IN ({placeholders})
        """, section_ids)

        deleted = cursor.rowcount
        conn.commit()

        logger.info(f"Deleted {deleted} existing parent chunks for document {document_id}")
        return deleted


def insert_parent_chunks_batch(chunks: List[Dict[str, Any]]) -> int:
    """
    Insert a batch of parent chunks into the database.

    Args:
        chunks: List of chunk dicts with section_id, content, token_count, etc.

    Returns:
        Number of chunks inserted
    """
    if not chunks:
        return 0

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")

        try:
            for chunk in chunks:
                cursor.execute("""
                    INSERT INTO parent_chunks (
                        section_id, content, token_count,
                        page_start, page_end, metadata
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    chunk['section_id'],
                    chunk['content'],
                    chunk['token_count'],
                    chunk.get('page_start'),
                    chunk.get('page_end'),
                    json.dumps({
                        'heading_path': chunk.get('heading_path'),
                        'order_index': chunk.get('order_index'),
                    })
                ))

            conn.commit()
            return len(chunks)

        except Exception as e:
            conn.rollback()
            raise CleanupError(f"Failed to insert parent chunks: {e}") from e


def export_parent_chunks_to_markdown(document_id: str, output_path: Path) -> int:
    """
    Export all parent chunks to a markdown file for review.

    Args:
        document_id: Document UUID
        output_path: Path to write markdown export

    Returns:
        Number of chunks exported
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                pc.id,
                pc.section_id,
                pc.content,
                pc.token_count,
                pc.page_start,
                pc.page_end,
                pc.metadata,
                s.heading_path
            FROM parent_chunks pc
            JOIN sections s ON pc.section_id = s.id
            WHERE s.document_id = ?
            ORDER BY s.order_index, pc.id
        """, (document_id,))

        chunks = cursor.fetchall()

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Parent Chunks Export\n\n")
        f.write(f"**Document ID:** {document_id}\n")
        f.write(f"**Total Chunks:** {len(chunks)}\n")
        f.write(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")

        for chunk in chunks:
            chunk_id = chunk[0]
            section_id = chunk[1]
            content = chunk[2]
            token_count = chunk[3]
            page_start = chunk[4]
            page_end = chunk[5]
            metadata = json.loads(chunk[6]) if chunk[6] else {}
            heading_path = chunk[7]

            f.write(f"## Chunk {chunk_id}\n\n")
            f.write(f"- **chunk_id:** {chunk_id}\n")
            f.write(f"- **section_id:** {section_id}\n")
            f.write(f"- **heading_path:** {heading_path}\n")
            f.write(f"- **token_count:** {token_count}\n")
            f.write(f"- **pages:** {page_start or '?'}-{page_end or '?'}\n")
            if metadata.get('order_index') is not None:
                f.write(f"- **order_index:** {metadata['order_index']}\n")
            f.write("\n### Content\n\n")
            f.write(content)
            f.write("\n\n---\n\n")

    logger.info(f"Exported {len(chunks)} parent chunks to {output_path}")
    return len(chunks)


def get_document_id(db_path: Path) -> Optional[str]:
    """
    Auto-detect document ID if only one document exists.

    Args:
        db_path: Path to database

    Returns:
        Document ID string or None if multiple/no documents
    """
    with get_connection(db_path=db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM documents")
        docs = cursor.fetchall()

        if len(docs) == 0:
            logger.error("No documents found in database")
            return None
        elif len(docs) == 1:
            doc_id = docs[0][0]
            logger.info(f"Auto-detected document: {docs[0][1]} ({doc_id})")
            return doc_id
        else:
            logger.error("Multiple documents found. Please specify --doc-id:")
            for doc in docs:
                logger.info(f"  {doc[0]}: {doc[1]}")
            return None


def run(
    db_path: Optional[Path] = None,
    doc_id: Optional[str] = None,
    export_path: Optional[Path] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Execute Step 3: Cleanup and Parent Chunk Construction.

    Args:
        db_path: Path to database (defaults to config)
        doc_id: Document ID (auto-detected if not provided)
        export_path: Path to export parent chunks markdown
        overwrite: If True, delete existing parent chunks first

    Returns:
        Dict with statistics

    Raises:
        CleanupError: If cleanup fails
    """
    db_path = db_path or DATABASE_PATH
    start_time = time.time()

    logger.info("=" * 80)
    logger.info("STEP 3: CLEANUP AND PARENT CHUNK CONSTRUCTION")
    logger.info("=" * 80)

    # Get or validate document ID
    if doc_id is None:
        doc_id = get_document_id(db_path)
        if doc_id is None:
            raise CleanupError("Could not determine document ID")

    # Check for existing parent chunks
    existing_count = check_existing_parent_chunks(doc_id)
    if existing_count > 0:
        if overwrite:
            logger.warning(f"Found {existing_count} existing parent chunks - deleting (--overwrite)")
            delete_parent_chunks_for_document(doc_id)
        else:
            logger.error(
                f"Found {existing_count} existing parent chunks for document {doc_id}. "
                f"Use --overwrite to replace them."
            )
            raise CleanupError("Parent chunks already exist. Use --overwrite to replace.")

    # Get level-2 sections
    logger.info("Loading level-2 sections (diseases/topics)...")
    sections = get_level2_sections(doc_id)

    if not sections:
        logger.error("No level-2 sections found. Please run Step 2 first.")
        raise CleanupError("No level-2 sections found")

    logger.success(f"Found {len(sections)} level-2 sections")

    # Initialize tokenizer
    tokenizer = get_tokenizer()

    # Process sections in batches
    total_chunks_created = 0
    total_blocks_processed = 0
    total_blocks_skipped = 0
    all_token_counts = []

    batch_size = CLEANUP_BATCH_SIZE

    for batch_start in range(0, len(sections), batch_size):
        batch_end = min(batch_start + batch_size, len(sections))
        batch_sections = sections[batch_start:batch_end]
        batch_num = batch_start // batch_size + 1
        total_batches = (len(sections) + batch_size - 1) // batch_size

        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch_sections)} sections)...")

        batch_chunks = []

        for section in batch_sections:
            section_id = section['id']
            heading = section['heading']

            # Build content for this section
            full_content, units = build_section_content(section, tokenizer)

            if not units:
                logger.debug(f"No content for section: {heading}")
                continue

            # Create parent chunks
            chunks = create_parent_chunks(section, units, tokenizer)

            for chunk in chunks:
                all_token_counts.append(chunk['token_count'])

            batch_chunks.extend(chunks)

            logger.debug(
                f"  Section '{heading[:50]}...': "
                f"{len(units)} units -> {len(chunks)} chunks"
            )

        # Insert batch
        if batch_chunks:
            inserted = insert_parent_chunks_batch(batch_chunks)
            total_chunks_created += inserted
            logger.success(f"  Batch {batch_num}: Inserted {inserted} parent chunks")

    # Export to markdown if requested
    if export_path:
        export_parent_chunks_to_markdown(doc_id, export_path / "parent_chunks_all.md")

    # Compute statistics
    duration = time.time() - start_time

    stats = {
        'document_id': doc_id,
        'sections_processed': len(sections),
        'parent_chunks_created': total_chunks_created,
        'token_min': min(all_token_counts) if all_token_counts else 0,
        'token_max': max(all_token_counts) if all_token_counts else 0,
        'token_median': statistics.median(all_token_counts) if all_token_counts else 0,
        'token_mean': statistics.mean(all_token_counts) if all_token_counts else 0,
        'chunks_over_limit': sum(1 for t in all_token_counts if t > PARENT_TOKEN_HARD_MAX),
        'duration_seconds': duration,
    }

    # Log summary
    logger.info("=" * 80)
    logger.info("STEP 3 COMPLETE")
    logger.info("=" * 80)
    logger.success(f"Level-2 sections processed: {stats['sections_processed']}")
    logger.success(f"Parent chunks created: {stats['parent_chunks_created']}")
    logger.info(f"Token distribution:")
    logger.info(f"  Min: {stats['token_min']}")
    logger.info(f"  Max: {stats['token_max']}")
    logger.info(f"  Median: {stats['token_median']:.0f}")
    logger.info(f"  Mean: {stats['token_mean']:.1f}")

    if stats['chunks_over_limit'] > 0:
        logger.error(f"CHUNKS OVER {PARENT_TOKEN_HARD_MAX} TOKEN LIMIT: {stats['chunks_over_limit']}")
    else:
        logger.success(f"All chunks within {PARENT_TOKEN_HARD_MAX} token limit")

    logger.info(f"Duration: {duration:.2f} seconds")
    logger.info("=" * 80)

    return stats


def main():
    """CLI entry point for Step 3."""
    parser = argparse.ArgumentParser(
        description="Step 3: Cleanup and Parent Chunk Construction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with auto-detected document ID
    python -m src.pipeline.step3_cleanup

    # Run with specific document ID
    python -m src.pipeline.step3_cleanup --doc-id 4e2ce587-fc2c-4f79-8f2f-8ac25d5252b0

    # Overwrite existing chunks and export
    python -m src.pipeline.step3_cleanup --overwrite --export data/exports/

    # Specify custom database path
    python -m src.pipeline.step3_cleanup --db data/ucg23_rag.db
        """
    )

    parser.add_argument(
        '--db',
        type=Path,
        help="Path to SQLite database (defaults to config)"
    )
    parser.add_argument(
        '--doc-id',
        type=str,
        help="Document ID (auto-detected if only one document exists)"
    )
    parser.add_argument(
        '--export',
        type=Path,
        help="Export parent chunks to this directory"
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help="Delete existing parent chunks and rebuild"
    )

    args = parser.parse_args()

    # Initialize logging
    setup_logger()

    try:
        stats = run(
            db_path=args.db,
            doc_id=args.doc_id,
            export_path=args.export,
            overwrite=args.overwrite,
        )
        logger.info("Step 3 completed successfully")
        sys.exit(0)

    except CleanupError as e:
        logger.error(f"Step 3 failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error in Step 3: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
