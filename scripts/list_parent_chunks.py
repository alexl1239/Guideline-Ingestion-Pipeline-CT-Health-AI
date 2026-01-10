#!/usr/bin/env python3
"""
Parent Chunks Listing Script

Lists and exports parent chunks in a human-readable format.

Usage:
    # Print outline of all sections -> parent chunks
    python scripts/list_parent_chunks.py outline

    # Dump a specific parent chunk by ID
    python scripts/list_parent_chunks.py dump 42

    # Export all parent chunks to markdown
    python scripts/list_parent_chunks.py export exports/parent_chunks_all.md

    # Show statistics
    python scripts/list_parent_chunks.py stats

Examples:
    python scripts/list_parent_chunks.py outline --limit 50
    python scripts/list_parent_chunks.py dump 123 --format json
    python scripts/list_parent_chunks.py export data/exports/parent_chunks_all.md
"""

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional


def get_db_path() -> Path:
    """Get database path from project structure."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    return project_root / "data" / "ucg23_rag.db"


def connect_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Connect to database with row factory."""
    db_path = db_path or get_db_path()
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def cmd_outline(args):
    """Print outline: section heading_path -> list of parent chunk ids + token counts."""
    conn = connect_db(args.db)
    cursor = conn.cursor()

    # Get all level-2 sections with their parent chunks
    cursor.execute("""
        SELECT
            s.id as section_id,
            s.level,
            s.heading,
            s.heading_path,
            s.page_start,
            s.page_end,
            COUNT(pc.id) as chunk_count,
            SUM(pc.token_count) as total_tokens,
            AVG(pc.token_count) as avg_tokens
        FROM sections s
        LEFT JOIN parent_chunks pc ON pc.section_id = s.id
        WHERE s.level = 2
        GROUP BY s.id
        ORDER BY s.order_index
        LIMIT ?
    """, (args.limit or 10000,))

    sections = cursor.fetchall()

    if not sections:
        print("No level-2 sections found.")
        conn.close()
        return

    print("=" * 80)
    print("PARENT CHUNKS OUTLINE")
    print("=" * 80)
    print(f"Total level-2 sections: {len(sections)}")
    print()

    for section in sections:
        heading_path = section['heading_path']
        chunk_count = section['chunk_count'] or 0
        total_tokens = section['total_tokens'] or 0
        avg_tokens = section['avg_tokens'] or 0

        print(f"Section {section['section_id']}: {heading_path[:70]}")
        print(f"  Pages: {section['page_start']}-{section['page_end']}")
        print(f"  Parent chunks: {chunk_count} (total tokens: {total_tokens:,}, avg: {avg_tokens:.0f})")

        if chunk_count > 0 and args.show_chunks:
            # Get chunks for this section
            cursor.execute("""
                SELECT id, token_count, page_start, page_end
                FROM parent_chunks
                WHERE section_id = ?
                ORDER BY id
            """, (section['section_id'],))

            chunks = cursor.fetchall()
            for chunk in chunks:
                print(f"    - Chunk {chunk['id']}: {chunk['token_count']} tokens "
                      f"(pages {chunk['page_start'] or '?'}-{chunk['page_end'] or '?'})")

        print()

    conn.close()


def cmd_dump(args):
    """Dump a specific parent chunk by ID."""
    conn = connect_db(args.db)
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
            pc.created_at,
            s.heading,
            s.heading_path,
            s.level
        FROM parent_chunks pc
        JOIN sections s ON pc.section_id = s.id
        WHERE pc.id = ?
    """, (args.chunk_id,))

    chunk = cursor.fetchone()

    if not chunk:
        print(f"Error: Parent chunk {args.chunk_id} not found", file=sys.stderr)
        conn.close()
        sys.exit(1)

    if args.format == 'json':
        output = {
            'id': chunk['id'],
            'section_id': chunk['section_id'],
            'heading': chunk['heading'],
            'heading_path': chunk['heading_path'],
            'level': chunk['level'],
            'token_count': chunk['token_count'],
            'page_start': chunk['page_start'],
            'page_end': chunk['page_end'],
            'metadata': json.loads(chunk['metadata']) if chunk['metadata'] else {},
            'created_at': chunk['created_at'],
            'content': chunk['content'],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        # Markdown format
        print(f"# Parent Chunk {chunk['id']}")
        print()
        print(f"- **chunk_id:** {chunk['id']}")
        print(f"- **section_id:** {chunk['section_id']}")
        print(f"- **heading:** {chunk['heading']}")
        print(f"- **heading_path:** {chunk['heading_path']}")
        print(f"- **level:** {chunk['level']}")
        print(f"- **token_count:** {chunk['token_count']}")
        print(f"- **pages:** {chunk['page_start'] or '?'}-{chunk['page_end'] or '?'}")
        print(f"- **created_at:** {chunk['created_at']}")
        print()
        print("## Content")
        print()
        print(chunk['content'])

    conn.close()


def cmd_export(args):
    """Export all parent chunks to markdown file."""
    conn = connect_db(args.db)
    cursor = conn.cursor()

    # Get all parent chunks ordered by section
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
        ORDER BY s.order_index, pc.id
    """)

    chunks = cursor.fetchall()

    if not chunks:
        print("No parent chunks found to export.")
        conn.close()
        return

    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Parent Chunks Export\n\n")
        f.write(f"**Total Chunks:** {len(chunks)}\n")
        f.write(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")

        for chunk in chunks:
            metadata = json.loads(chunk['metadata']) if chunk['metadata'] else {}

            f.write(f"## Chunk {chunk['id']}\n\n")
            f.write(f"- **chunk_id:** {chunk['id']}\n")
            f.write(f"- **section_id:** {chunk['section_id']}\n")
            f.write(f"- **heading_path:** {chunk['heading_path']}\n")
            f.write(f"- **token_count:** {chunk['token_count']}\n")
            f.write(f"- **pages:** {chunk['page_start'] or '?'}-{chunk['page_end'] or '?'}\n")
            if metadata.get('order_index') is not None:
                f.write(f"- **order_index:** {metadata['order_index']}\n")
            f.write("\n### Content\n\n")
            f.write(chunk['content'])
            f.write("\n\n---\n\n")

    print(f"Exported {len(chunks)} parent chunks to {output_path}")
    conn.close()


def cmd_stats(args):
    """Show parent chunk statistics."""
    conn = connect_db(args.db)
    cursor = conn.cursor()

    # Overall stats
    cursor.execute("""
        SELECT
            COUNT(*) as count,
            MIN(token_count) as min_tokens,
            MAX(token_count) as max_tokens,
            AVG(token_count) as avg_tokens,
            SUM(token_count) as total_tokens
        FROM parent_chunks
    """)
    stats = cursor.fetchone()

    print("=" * 60)
    print("PARENT CHUNK STATISTICS")
    print("=" * 60)
    print(f"Total parent chunks:  {stats['count']:,}")
    print(f"Total tokens:         {stats['total_tokens'] or 0:,}")
    print(f"Min tokens per chunk: {stats['min_tokens'] or 0}")
    print(f"Max tokens per chunk: {stats['max_tokens'] or 0}")
    print(f"Avg tokens per chunk: {stats['avg_tokens'] or 0:.1f}")
    print()

    # Token distribution
    cursor.execute("""
        SELECT
            CASE
                WHEN token_count < 500 THEN '< 500'
                WHEN token_count < 1000 THEN '500-999'
                WHEN token_count < 1500 THEN '1000-1499'
                WHEN token_count < 2000 THEN '1500-1999'
                ELSE '>= 2000'
            END as bucket,
            COUNT(*) as count
        FROM parent_chunks
        GROUP BY bucket
        ORDER BY
            CASE bucket
                WHEN '< 500' THEN 1
                WHEN '500-999' THEN 2
                WHEN '1000-1499' THEN 3
                WHEN '1500-1999' THEN 4
                ELSE 5
            END
    """)

    print("Token Distribution:")
    print("-" * 40)
    for row in cursor.fetchall():
        print(f"  {row['bucket']:15s}: {row['count']:5d}")
    print()

    # Coverage per level-2 section
    cursor.execute("""
        SELECT
            COUNT(DISTINCT s.id) as sections_total,
            COUNT(DISTINCT pc.section_id) as sections_with_chunks
        FROM sections s
        LEFT JOIN parent_chunks pc ON pc.section_id = s.id
        WHERE s.level = 2
    """)
    coverage = cursor.fetchone()

    sections_without = coverage['sections_total'] - coverage['sections_with_chunks']
    print(f"Level-2 section coverage:")
    print(f"  Total sections:    {coverage['sections_total']}")
    print(f"  With chunks:       {coverage['sections_with_chunks']}")
    print(f"  Without chunks:    {sections_without}")
    print()

    # Chunks over 2000 tokens (violations)
    cursor.execute("SELECT COUNT(*) as count FROM parent_chunks WHERE token_count > 2000")
    violations = cursor.fetchone()['count']
    if violations > 0:
        print(f"WARNING: {violations} chunks exceed 2000 token limit!")
    else:
        print("All chunks within 2000 token limit.")

    print("=" * 60)
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Parent Chunks Listing and Export Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
    outline     Print outline of sections with their parent chunks
    dump        Dump a specific parent chunk by ID
    export      Export all parent chunks to markdown file
    stats       Show parent chunk statistics

Examples:
    python scripts/list_parent_chunks.py outline
    python scripts/list_parent_chunks.py outline --show-chunks
    python scripts/list_parent_chunks.py dump 42
    python scripts/list_parent_chunks.py dump 42 --format json
    python scripts/list_parent_chunks.py export data/exports/parent_chunks_all.md
    python scripts/list_parent_chunks.py stats
        """
    )

    parser.add_argument(
        '--db',
        type=Path,
        help="Path to database (defaults to data/ucg23_rag.db)"
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # outline command
    outline_parser = subparsers.add_parser('outline', help='Print section outline with chunks')
    outline_parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help="Limit number of sections to show"
    )
    outline_parser.add_argument(
        '--show-chunks',
        action='store_true',
        help="Show individual chunk IDs under each section"
    )

    # dump command
    dump_parser = subparsers.add_parser('dump', help='Dump a parent chunk by ID')
    dump_parser.add_argument('chunk_id', type=int, help='Parent chunk ID')
    dump_parser.add_argument(
        '--format',
        choices=['markdown', 'json'],
        default='markdown',
        help="Output format (default: markdown)"
    )

    # export command
    export_parser = subparsers.add_parser('export', help='Export all chunks to markdown')
    export_parser.add_argument(
        'output',
        type=str,
        help="Output file path"
    )

    # stats command
    subparsers.add_parser('stats', help='Show statistics')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == 'outline':
        cmd_outline(args)
    elif args.command == 'dump':
        cmd_dump(args)
    elif args.command == 'export':
        cmd_export(args)
    elif args.command == 'stats':
        cmd_stats(args)


if __name__ == "__main__":
    main()
