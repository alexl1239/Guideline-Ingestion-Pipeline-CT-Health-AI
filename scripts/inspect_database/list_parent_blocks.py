#!/usr/bin/env python3
"""
Parent Blocks Inspection Script

Lists and exports parent_chunks from the UCG-23 RAG database for manual review.
All outputs are written to scripts/inspect_database/output/ (no terminal output).

This script helps verify Step 5 (Cleanup and Parent Chunk Formation) is correct:
- Parent chunks cover full clinical content without gaps or duplications
- No parent chunk exceeds 2,000 token hard limit
- Clinical content is preserved and readable

Usage:
    # Outline mode (default) - writes outline + stats + index to output/
    python scripts/inspect_database/list_parent_blocks.py --db data/ucg23_rag.db

    # Dump a specific chunk
    python scripts/inspect_database/list_parent_blocks.py --db data/ucg23_rag.db --dump 123

    # Export all chunks to single markdown file
    python scripts/inspect_database/list_parent_blocks.py --db data/ucg23_rag.db --export

    # Generate all artifacts (recommended for full verification)
    python scripts/inspect_database/list_parent_blocks.py --db data/ucg23_rag.db --all
"""

import argparse
import hashlib
import json
import sqlite3
import statistics
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


# Output directory relative to this script
SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "output"


def get_default_db_path() -> Path:
    """Get default database path relative to project root."""
    project_root = SCRIPT_DIR.parent.parent
    return project_root / "data" / "ucg23_rag.db"


def ensure_output_dir():
    """Create output directory if it doesn't exist."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def detect_column_name(cursor: sqlite3.Cursor, table: str, candidates: List[str]) -> Optional[str]:
    """
    Auto-detect column name from a list of candidates.
    Uses PRAGMA table_info to inspect actual columns.
    """
    cursor.execute(f"PRAGMA table_info({table})")
    actual_columns = {row[1].lower() for row in cursor.fetchall()}

    for candidate in candidates:
        if candidate.lower() in actual_columns:
            return candidate

    return None


def get_parent_chunks_schema(cursor: sqlite3.Cursor) -> Dict[str, str]:
    """Detect the actual column names in parent_chunks table."""
    content_candidates = ['content', 'content_markdown', 'chunk_markdown', 'markdown_content', 'text_content']
    content_col = detect_column_name(cursor, 'parent_chunks', content_candidates)

    token_candidates = ['token_count', 'tokens', 'num_tokens', 'token_cnt']
    token_col = detect_column_name(cursor, 'parent_chunks', token_candidates)

    return {
        'content_col': content_col or 'content',
        'token_col': token_col or 'token_count',
    }


def get_sections_schema(cursor: sqlite3.Cursor) -> Dict[str, str]:
    """Detect the actual column names in sections table."""
    level_candidates = ['level', 'section_level', 'depth', 'hierarchy_level']
    level_col = detect_column_name(cursor, 'sections', level_candidates)

    path_candidates = ['heading_path', 'path', 'full_path', 'section_path']
    path_col = detect_column_name(cursor, 'sections', path_candidates)

    order_candidates = ['order_index', 'sort_key', 'sort_order', 'ordering', 'idx']
    order_col = detect_column_name(cursor, 'sections', order_candidates)

    return {
        'level_col': level_col or 'level',
        'heading_path_col': path_col or 'heading_path',
        'order_col': order_col or 'order_index',
    }


def get_level2_sections(cursor: sqlite3.Cursor, sections_schema: Dict[str, str]) -> List[Dict[str, Any]]:
    """Get all level-2 sections (disease/topic) ordered correctly."""
    level_col = sections_schema['level_col']
    path_col = sections_schema['heading_path_col']
    order_col = sections_schema['order_col']

    query = f"""
        SELECT id, {level_col} as level, heading, {path_col} as heading_path,
               page_start, page_end, {order_col} as order_index
        FROM sections
        WHERE {level_col} = 2
        ORDER BY {order_col}
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    return [
        {
            'id': row[0],
            'level': row[1],
            'heading': row[2],
            'heading_path': row[3],
            'page_start': row[4],
            'page_end': row[5],
            'order_index': row[6],
        }
        for row in rows
    ]


def get_parent_chunks_for_section(
    cursor: sqlite3.Cursor,
    section_id: int,
    chunks_schema: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Get all parent chunks for a given section, ordered by order_index."""
    content_col = chunks_schema['content_col']
    token_col = chunks_schema['token_col']

    cursor.execute("PRAGMA table_info(parent_chunks)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'order_index' in columns:
        order_expr = 'order_index'
    elif 'metadata' in columns:
        order_expr = "json_extract(metadata, '$.order_index')"
    else:
        order_expr = 'id'

    query = f"""
        SELECT id, section_id, {content_col} as content, {token_col} as token_count,
               page_start, page_end, metadata, {order_expr} as order_index
        FROM parent_chunks
        WHERE section_id = ?
        ORDER BY {order_expr}, id
    """

    cursor.execute(query, (section_id,))
    rows = cursor.fetchall()

    return [
        {
            'id': row[0],
            'section_id': row[1],
            'content': row[2],
            'token_count': row[3],
            'page_start': row[4],
            'page_end': row[5],
            'metadata': row[6],
            'order_index': row[7],
        }
        for row in rows
    ]


def get_all_parent_chunks(
    cursor: sqlite3.Cursor,
    chunks_schema: Dict[str, str],
    sections_schema: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Get all parent chunks ordered by section order, then chunk order."""
    content_col = chunks_schema['content_col']
    token_col = chunks_schema['token_col']
    path_col = sections_schema['heading_path_col']
    section_order_col = sections_schema['order_col']

    cursor.execute("PRAGMA table_info(parent_chunks)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'order_index' in columns:
        chunk_order_expr = 'pc.order_index'
    elif 'metadata' in columns:
        chunk_order_expr = "json_extract(pc.metadata, '$.order_index')"
    else:
        chunk_order_expr = 'pc.id'

    query = f"""
        SELECT pc.id, pc.section_id, pc.{content_col} as content,
               pc.{token_col} as token_count, pc.page_start, pc.page_end,
               pc.metadata, s.{path_col} as heading_path, s.{section_order_col} as section_order,
               {chunk_order_expr} as chunk_order
        FROM parent_chunks pc
        JOIN sections s ON pc.section_id = s.id
        ORDER BY s.{section_order_col}, {chunk_order_expr}, pc.id
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    return [
        {
            'id': row[0],
            'section_id': row[1],
            'content': row[2],
            'token_count': row[3],
            'page_start': row[4],
            'page_end': row[5],
            'metadata': row[6],
            'heading_path': row[7],
            'section_order': row[8],
            'order_index': row[9],
        }
        for row in rows
    ]


def get_chunk_by_id(
    cursor: sqlite3.Cursor,
    chunk_id: int,
    chunks_schema: Dict[str, str],
    sections_schema: Dict[str, str]
) -> Optional[Dict[str, Any]]:
    """Get a specific parent chunk by ID with section info."""
    content_col = chunks_schema['content_col']
    token_col = chunks_schema['token_col']
    path_col = sections_schema['heading_path_col']

    cursor.execute("PRAGMA table_info(parent_chunks)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'order_index' in columns:
        order_expr = 'pc.order_index'
    elif 'metadata' in columns:
        order_expr = "json_extract(pc.metadata, '$.order_index')"
    else:
        order_expr = 'NULL'

    query = f"""
        SELECT pc.id, pc.section_id, pc.{content_col} as content,
               pc.{token_col} as token_count, pc.page_start, pc.page_end,
               pc.metadata, s.{path_col} as heading_path, s.document_id,
               {order_expr} as order_index
        FROM parent_chunks pc
        JOIN sections s ON pc.section_id = s.id
        WHERE pc.id = ?
    """

    cursor.execute(query, (chunk_id,))
    row = cursor.fetchone()

    if not row:
        return None

    return {
        'id': row[0],
        'section_id': row[1],
        'content': row[2],
        'token_count': row[3],
        'page_start': row[4],
        'page_end': row[5],
        'metadata': row[6],
        'heading_path': row[7],
        'doc_id': row[8],
        'order_index': row[9],
    }


def compute_stats(chunks: List[Dict[str, Any]], level2_sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute summary statistics for parent chunks."""
    token_counts = [c['token_count'] for c in chunks if c['token_count'] is not None]

    over_limit = [c for c in chunks if c['token_count'] and c['token_count'] > 2000]
    empty_content = [c for c in chunks if not c['content'] or len(c['content'].strip()) == 0]
    null_tokens = [c for c in chunks if c['token_count'] is None]

    # Find sections with zero chunks
    section_ids_with_chunks = {c['section_id'] for c in chunks}
    sections_with_zero = [s for s in level2_sections if s['id'] not in section_ids_with_chunks]

    # Compute content hashes for duplicate detection
    content_hashes = {}
    for c in chunks:
        if c['content']:
            h = hashlib.md5(c['content'].encode()).hexdigest()
            if h not in content_hashes:
                content_hashes[h] = []
            content_hashes[h].append(c['id'])

    duplicate_hashes = {h: ids for h, ids in content_hashes.items() if len(ids) > 1}

    # Near-empty chunks (< 50 chars)
    near_empty = [c for c in chunks if c['content'] and len(c['content'].strip()) < 50]

    stats = {
        'total_level2_sections': len(level2_sections),
        'sections_with_zero_chunks': {
            'count': len(sections_with_zero),
            'section_ids': [s['id'] for s in sections_with_zero],
            'headings': [s['heading'] for s in sections_with_zero],
        },
        'total_parent_chunks': len(chunks),
        'token_count_min': min(token_counts) if token_counts else 0,
        'token_count_max': max(token_counts) if token_counts else 0,
        'token_count_median': statistics.median(token_counts) if token_counts else 0,
        'token_count_mean': statistics.mean(token_counts) if token_counts else 0,
        'token_count_p95': sorted(token_counts)[int(len(token_counts) * 0.95)] if len(token_counts) >= 20 else (max(token_counts) if token_counts else 0),
        'chunks_over_2000_tokens': {
            'count': len(over_limit),
            'chunk_ids': [c['id'] for c in over_limit],
        },
        'duplicate_chunk_hashes': {
            'count': len(duplicate_hashes),
            'details': duplicate_hashes,
        },
        'empty_content_chunks': {
            'count': len(empty_content),
            'chunk_ids': [c['id'] for c in empty_content],
        },
        'near_empty_chunks': {
            'count': len(near_empty),
            'chunk_ids': [c['id'] for c in near_empty],
        },
        'null_token_count_chunks': {
            'count': len(null_tokens),
            'chunk_ids': [c['id'] for c in null_tokens],
        },
    }

    return stats


def write_outline(
    cursor: sqlite3.Cursor,
    chunks_schema: Dict[str, str],
    sections_schema: Dict[str, str]
) -> Tuple[int, int]:
    """Write outline of parent chunks grouped by level-2 section."""
    level2_sections = get_level2_sections(cursor, sections_schema)

    lines = []
    lines.append("# Parent Chunks Outline")
    lines.append("")
    lines.append("Grouped by level-2 sections (diseases/topics)")
    lines.append("")
    lines.append("---")
    lines.append("")

    total_chunks = 0

    for section in level2_sections:
        chunks = get_parent_chunks_for_section(cursor, section['id'], chunks_schema)

        if not chunks:
            lines.append(f"## {section['heading_path']}")
            lines.append(f"*Section ID: {section['id']} | Pages: {section['page_start']}-{section['page_end']}*")
            lines.append("")
            lines.append("**(no parent chunks)** - POTENTIAL GAP")
            lines.append("")
            continue

        lines.append(f"## {section['heading_path']}")
        lines.append(f"*Section ID: {section['id']} | Pages: {section['page_start']}-{section['page_end']} | Chunks: {len(chunks)}*")
        lines.append("")

        for chunk in chunks:
            token_count = chunk['token_count'] or 0
            content_len = len(chunk['content']) if chunk['content'] else 0
            order_idx = chunk['order_index'] if chunk['order_index'] is not None else '?'

            flag = " **[OVER LIMIT]**" if token_count > 2000 else ""

            lines.append(f"- parent_chunk_id={chunk['id']} order_index={order_idx} tokens={token_count} chars={content_len}{flag}")

        lines.append("")
        total_chunks += len(chunks)

    output_path = OUTPUT_DIR / "parent_blocks_outline.md"
    output_path.write_text('\n'.join(lines), encoding='utf-8')

    return len(level2_sections), total_chunks


def write_index(
    cursor: sqlite3.Cursor,
    chunks_schema: Dict[str, str],
    sections_schema: Dict[str, str]
) -> int:
    """Write section-level index for anti-gap checking."""
    level2_sections = get_level2_sections(cursor, sections_schema)

    lines = []
    lines.append("# Parent Chunks Index")
    lines.append("")
    lines.append("Section-level index for verifying coverage (anti-gap check)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("| Section ID | Heading Path | Chunks | Total Tokens | Pages | Chunk IDs |")
    lines.append("|------------|--------------|--------|--------------|-------|-----------|")

    for section in level2_sections:
        chunks = get_parent_chunks_for_section(cursor, section['id'], chunks_schema)

        chunk_count = len(chunks)
        total_tokens = sum(c['token_count'] or 0 for c in chunks)
        page_range = f"{section['page_start']}-{section['page_end']}"
        chunk_ids = ', '.join(str(c['id']) for c in chunks) if chunks else "(none)"

        heading_short = section['heading_path'][:60] + "..." if len(section['heading_path']) > 60 else section['heading_path']

        flag = " **GAP**" if chunk_count == 0 else ""

        lines.append(f"| {section['id']} | {heading_short}{flag} | {chunk_count} | {total_tokens} | {page_range} | {chunk_ids} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Summary")
    lines.append("")

    sections_with_chunks = sum(1 for s in level2_sections if get_parent_chunks_for_section(cursor, s['id'], chunks_schema))
    sections_without = len(level2_sections) - sections_with_chunks

    lines.append(f"- Total level-2 sections: {len(level2_sections)}")
    lines.append(f"- Sections with chunks: {sections_with_chunks}")
    lines.append(f"- Sections without chunks (GAPS): {sections_without}")

    output_path = OUTPUT_DIR / "parent_chunks_index.md"
    output_path.write_text('\n'.join(lines), encoding='utf-8')

    return len(level2_sections)


def write_dump(
    cursor: sqlite3.Cursor,
    chunk_id: int,
    chunks_schema: Dict[str, str],
    sections_schema: Dict[str, str]
) -> bool:
    """Write a single parent chunk to a file with metadata header."""
    chunk = get_chunk_by_id(cursor, chunk_id, chunks_schema, sections_schema)

    if not chunk:
        return False

    lines = []
    lines.append("---")
    lines.append(f"parent_chunk_id: {chunk['id']}")
    lines.append(f"doc_id: {chunk['doc_id']}")
    lines.append(f"section_id: {chunk['section_id']}")
    lines.append(f"heading_path: {chunk['heading_path']}")
    lines.append(f"order_index: {chunk['order_index']}")
    lines.append(f"token_count: {chunk['token_count']}")
    lines.append(f"pages: {chunk['page_start']}-{chunk['page_end']}")
    lines.append("---")
    lines.append("")
    lines.append(chunk['content'] or "(empty content)")

    output_path = OUTPUT_DIR / f"parent_chunk_{chunk_id}.md"
    output_path.write_text('\n'.join(lines), encoding='utf-8')

    return True


def write_export_all(
    cursor: sqlite3.Cursor,
    chunks_schema: Dict[str, str],
    sections_schema: Dict[str, str]
) -> int:
    """Export all parent chunks to a single markdown file."""
    chunks = get_all_parent_chunks(cursor, chunks_schema, sections_schema)

    doc_id = None
    if chunks:
        cursor.execute("SELECT document_id FROM sections WHERE id = ?", (chunks[0]['section_id'],))
        row = cursor.fetchone()
        if row:
            doc_id = row[0]

    lines = []
    lines.append("# Parent Chunks Export")
    lines.append("")
    lines.append(f"**Total Chunks:** {len(chunks)}")
    lines.append(f"**Document ID:** {doc_id}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for chunk in chunks:
        lines.append("---")
        lines.append(f"parent_chunk_id: {chunk['id']}")
        lines.append(f"doc_id: {doc_id}")
        lines.append(f"section_id: {chunk['section_id']}")
        lines.append(f"heading_path: {chunk['heading_path']}")
        lines.append(f"order_index: {chunk['order_index']}")
        lines.append(f"token_count: {chunk['token_count']}")
        lines.append(f"pages: {chunk['page_start']}-{chunk['page_end']}")
        lines.append("---")
        lines.append("")
        lines.append(chunk['content'] or "(empty content)")
        lines.append("")
        lines.append("")

    output_path = OUTPUT_DIR / "parent_chunks_all.md"
    output_path.write_text('\n'.join(lines), encoding='utf-8')

    return len(chunks)


def write_validation(
    cursor: sqlite3.Cursor,
    chunks_schema: Dict[str, str],
    sections_schema: Dict[str, str]
) -> Dict[str, Any]:
    """Write validation summary JSON."""
    level2_sections = get_level2_sections(cursor, sections_schema)
    chunks = get_all_parent_chunks(cursor, chunks_schema, sections_schema)

    stats = compute_stats(chunks, level2_sections)

    output_path = OUTPUT_DIR / "parent_chunks_validation.json"
    output_path.write_text(json.dumps(stats, indent=2), encoding='utf-8')

    return stats


def write_stats(
    cursor: sqlite3.Cursor,
    chunks_schema: Dict[str, str],
    sections_schema: Dict[str, str]
) -> Dict[str, Any]:
    """Write summary statistics to JSON file (legacy compatibility)."""
    level2_sections = get_level2_sections(cursor, sections_schema)
    chunks = get_all_parent_chunks(cursor, chunks_schema, sections_schema)

    stats = compute_stats(chunks, level2_sections)

    output_path = OUTPUT_DIR / "parent_blocks_stats.json"
    output_path.write_text(json.dumps(stats, indent=2), encoding='utf-8')

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Inspect parent_chunks table - outputs to scripts/inspect_database/output/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate outline + stats + index (default)
    python scripts/inspect_database/list_parent_blocks.py --db data/ucg23_rag.db

    # Dump a specific chunk
    python scripts/inspect_database/list_parent_blocks.py --db data/ucg23_rag.db --dump 123

    # Export all chunks to single file
    python scripts/inspect_database/list_parent_blocks.py --db data/ucg23_rag.db --export

    # Generate ALL artifacts (recommended for full verification)
    python scripts/inspect_database/list_parent_blocks.py --db data/ucg23_rag.db --all

All outputs are written to: scripts/inspect_database/output/
        """
    )

    parser.add_argument(
        '--db',
        type=Path,
        default=None,
        help="Path to SQLite database (default: data/ucg23_rag.db)"
    )
    parser.add_argument(
        '--dump',
        type=int,
        metavar='ID',
        help="Dump a specific parent chunk by ID"
    )
    parser.add_argument(
        '--export',
        action='store_true',
        help="Export all parent chunks to single markdown file"
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help="Generate all artifacts (outline, export, index, validation)"
    )

    args = parser.parse_args()

    db_path = args.db or get_default_db_path()

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    ensure_output_dir()

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = conn.cursor()

    try:
        chunks_schema = get_parent_chunks_schema(cursor)
        sections_schema = get_sections_schema(cursor)

        outputs_written = []

        if args.dump:
            success = write_dump(cursor, args.dump, chunks_schema, sections_schema)
            if success:
                outputs_written.append(f"parent_chunk_{args.dump}.md")
            else:
                print(f"Error: Parent chunk {args.dump} not found")
                return 1

        elif args.all:
            # Generate ALL artifacts
            section_count, chunk_count = write_outline(cursor, chunks_schema, sections_schema)
            outputs_written.append(f"parent_blocks_outline.md ({section_count} sections, {chunk_count} chunks)")

            export_count = write_export_all(cursor, chunks_schema, sections_schema)
            outputs_written.append(f"parent_chunks_all.md ({export_count} chunks)")

            index_count = write_index(cursor, chunks_schema, sections_schema)
            outputs_written.append(f"parent_chunks_index.md ({index_count} sections)")

            stats = write_validation(cursor, chunks_schema, sections_schema)
            outputs_written.append("parent_chunks_validation.json")

            write_stats(cursor, chunks_schema, sections_schema)
            outputs_written.append("parent_blocks_stats.json")

        elif args.export:
            count = write_export_all(cursor, chunks_schema, sections_schema)
            outputs_written.append(f"parent_chunks_all.md ({count} chunks)")

        else:
            # Default: outline + index + stats
            section_count, chunk_count = write_outline(cursor, chunks_schema, sections_schema)
            outputs_written.append(f"parent_blocks_outline.md ({section_count} sections, {chunk_count} chunks)")

            index_count = write_index(cursor, chunks_schema, sections_schema)
            outputs_written.append(f"parent_chunks_index.md ({index_count} sections)")

        # Always write stats and validation
        stats = write_stats(cursor, chunks_schema, sections_schema)
        if "parent_blocks_stats.json" not in [o.split()[0] for o in outputs_written]:
            outputs_written.append("parent_blocks_stats.json")

        write_validation(cursor, chunks_schema, sections_schema)
        if "parent_chunks_validation.json" not in [o.split()[0] for o in outputs_written]:
            outputs_written.append("parent_chunks_validation.json")

        print(f"Wrote outputs to {OUTPUT_DIR}/")

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    exit(main())
