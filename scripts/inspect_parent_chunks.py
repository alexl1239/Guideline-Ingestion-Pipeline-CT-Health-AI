#!/usr/bin/env python3
"""
Parent Chunks Inspection Script

Interactive CLI tool for inspecting and analyzing parent chunks from the Step 3
database output. Provides multiple commands with optional markdown export.

OUTPUT BEHAVIOR:
- All commands print to STDOUT (terminal) by default
- Add --export flag to additionally save output to data/exports/ as markdown
- Commands 'view' and 'section' display detailed content (terminal only)
- Commands 'stats', 'list', and 'search' support --export flag

COMMANDS:
    stats       Display token statistics, distribution, and coverage metrics
                Default: prints to terminal
                With --export: saves to data/exports/parent_chunks_stats.md
                Example: python scripts/inspect_parent_chunks.py stats --export

    list        Show all level-2 sections with chunk counts and token ranges
                Default: prints to terminal
                With --export: saves to data/exports/parent_chunks_list.md
                Example: python scripts/inspect_parent_chunks.py list --export

    view        Display full content of a specific chunk by chunk ID
                Output: Terminal only (no --export option available)
                Example: python scripts/inspect_parent_chunks.py view 459

    section     Show all chunks belonging to a specific section ID
                Output: Terminal only (no --export option available)
                Example: python scripts/inspect_parent_chunks.py section 3660

    search      Search chunk content for a keyword (case-insensitive)
                Default: prints to terminal
                With --export: saves to data/exports/parent_chunks_search.md
                Example: python scripts/inspect_parent_chunks.py search "malaria" --export

NOTE: Step 3 automatically exports parent_chunks_all.md to data/exports/ when run.
      This script provides additional ad-hoc inspection and analysis capabilities.

Usage Examples:
    python scripts/inspect_parent_chunks.py stats
    python scripts/inspect_parent_chunks.py stats --export
    python scripts/inspect_parent_chunks.py list --limit 20 --show-chunks
    python scripts/inspect_parent_chunks.py list --export
    python scripts/inspect_parent_chunks.py view 459
    python scripts/inspect_parent_chunks.py section 3660
    python scripts/inspect_parent_chunks.py search "malaria" --limit 5
    python scripts/inspect_parent_chunks.py search "malaria" --export
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Optional


def get_db_path() -> Path:
    """Get database path from project structure."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    return project_root / "data" / "ucg23_rag.db"


def get_export_dir() -> Path:
    """Get data/exports/ directory path."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    return project_root / "data" / "exports"


def write_to_markdown(content: str, filename: str) -> Path:
    """Write content to markdown file in exports directory."""
    export_dir = get_export_dir()
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = export_dir / filename

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return output_path


def connect_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Connect to database with row factory."""
    db_path = db_path or get_db_path()
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


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

    # Token distribution
    cursor.execute("""
        SELECT
            CASE
                WHEN token_count < 500 THEN '< 500'
                WHEN token_count < 1000 THEN '500-999'
                WHEN token_count < 1500 THEN '1000-1499'
                WHEN token_count < 2000 THEN '1500-1999'
                ELSE '>= 2000 (VIOLATION!)'
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
    distribution = cursor.fetchall()

    # Chunks per section
    cursor.execute("""
        SELECT
            COUNT(DISTINCT s.id) as total_sections,
            COUNT(DISTINCT pc.section_id) as sections_with_chunks,
            CAST(COUNT(pc.id) AS FLOAT) / COUNT(DISTINCT s.id) as avg_chunks_per_section
        FROM sections s
        LEFT JOIN parent_chunks pc ON pc.section_id = s.id
        WHERE s.level = 2
    """)
    coverage = cursor.fetchone()

    # Violations
    cursor.execute("SELECT COUNT(*) as count FROM parent_chunks WHERE token_count > 2000")
    violations = cursor.fetchone()['count']

    conn.close()

    # Build output
    lines = []
    lines.append("=" * 70)
    lines.append("PARENT CHUNK STATISTICS")
    lines.append("=" * 70)
    lines.append(f"Total chunks:         {stats['count']:,}")
    lines.append(f"Total tokens:         {stats['total_tokens'] or 0:,}")
    lines.append(f"Min tokens/chunk:     {stats['min_tokens'] or 0}")
    lines.append(f"Max tokens/chunk:     {stats['max_tokens'] or 0}")
    lines.append(f"Avg tokens/chunk:     {stats['avg_tokens'] or 0:.1f}")
    lines.append("")
    lines.append("Token Distribution:")
    lines.append("-" * 50)
    for row in distribution:
        bar = '█' * (row['count'] // 5)
        lines.append(f"  {row['bucket']:20s}: {row['count']:4d}  {bar}")
    lines.append("")
    lines.append(f"Level-2 Section Coverage:")
    lines.append(f"  Total sections:        {coverage['total_sections']}")
    lines.append(f"  With chunks:           {coverage['sections_with_chunks']}")
    lines.append(f"  Avg chunks/section:    {coverage['avg_chunks_per_section']:.1f}")
    lines.append("")
    if violations > 0:
        lines.append(f"⚠️  WARNING: {violations} chunks exceed 2000 token limit!")
    else:
        lines.append("✓ All chunks within 2000 token limit")
    lines.append("=" * 70)

    output = '\n'.join(lines)

    # Output or export
    if args.export:
        output_path = write_to_markdown(output, "parent_chunks_stats.md")
        print(f"✓ Exported statistics to {output_path}")
    else:
        print(output)


def cmd_list(args):
    """List all chunks with metadata."""
    conn = connect_db(args.db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            s.id as section_id,
            s.heading,
            COUNT(pc.id) as chunk_count,
            SUM(pc.token_count) as total_tokens,
            MIN(pc.token_count) as min_tokens,
            MAX(pc.token_count) as max_tokens
        FROM sections s
        LEFT JOIN parent_chunks pc ON pc.section_id = s.id
        WHERE s.level = 2
        GROUP BY s.id
        ORDER BY s.order_index
        LIMIT ?
    """, (args.limit,))

    sections = cursor.fetchall()

    # Build output
    lines = []
    lines.append("=" * 80)
    lines.append(f"PARENT CHUNKS BY SECTION (showing {len(sections)} sections)")
    lines.append("=" * 80)
    lines.append("")

    for section in sections:
        heading = section['heading'][:60]
        chunk_count = section['chunk_count'] or 0
        total_tokens = section['total_tokens'] or 0
        min_tokens = section['min_tokens'] or 0
        max_tokens = section['max_tokens'] or 0

        lines.append(f"Section {section['section_id']}: {heading}")
        lines.append(f"  Chunks: {chunk_count}  |  Total tokens: {total_tokens:,}")
        if chunk_count > 0:
            lines.append(f"  Token range: {min_tokens}-{max_tokens}")

        if args.show_chunks and chunk_count > 0:
            # Show individual chunks
            cursor.execute("""
                SELECT id, token_count
                FROM parent_chunks
                WHERE section_id = ?
                ORDER BY id
            """, (section['section_id'],))

            chunks = cursor.fetchall()
            chunk_ids = [f"{c['id']}({c['token_count']})" for c in chunks]
            lines.append(f"  Chunk IDs: {', '.join(chunk_ids)}")

        lines.append("")

    conn.close()

    output = '\n'.join(lines)

    # Output or export
    if args.export:
        output_path = write_to_markdown(output, "parent_chunks_list.md")
        print(f"✓ Exported section list to {output_path}")
    else:
        print(output)


def cmd_view(args):
    """View a specific chunk by ID."""
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
            s.heading,
            s.heading_path
        FROM parent_chunks pc
        JOIN sections s ON pc.section_id = s.id
        WHERE pc.id = ?
    """, (args.chunk_id,))

    chunk = cursor.fetchone()

    if not chunk:
        print(f"Error: Chunk {args.chunk_id} not found", file=sys.stderr)
        conn.close()
        sys.exit(1)

    print("=" * 80)
    print(f"PARENT CHUNK {chunk['id']}")
    print("=" * 80)
    print(f"Section ID:    {chunk['section_id']}")
    print(f"Heading:       {chunk['heading']}")
    print(f"Path:          {chunk['heading_path']}")
    print(f"Token count:   {chunk['token_count']}")
    print(f"Pages:         {chunk['page_start'] or '?'}-{chunk['page_end'] or '?'}")
    print()
    print("-" * 80)
    print("CONTENT:")
    print("-" * 80)
    print(chunk['content'])
    print()
    print("=" * 80)

    conn.close()


def cmd_section(args):
    """Show all chunks for a specific section."""
    conn = connect_db(args.db)
    cursor = conn.cursor()

    # Get section info
    cursor.execute("""
        SELECT id, heading, heading_path
        FROM sections
        WHERE id = ?
    """, (args.section_id,))

    section = cursor.fetchone()
    if not section:
        print(f"Error: Section {args.section_id} not found", file=sys.stderr)
        conn.close()
        sys.exit(1)

    # Get chunks for this section
    cursor.execute("""
        SELECT id, token_count, substr(content, 1, 150) as preview
        FROM parent_chunks
        WHERE section_id = ?
        ORDER BY id
    """, (args.section_id,))

    chunks = cursor.fetchall()

    print("=" * 80)
    print(f"SECTION {section['id']}: {section['heading']}")
    print("=" * 80)
    print(f"Path: {section['heading_path']}")
    print(f"Total chunks: {len(chunks)}")
    print()

    if not chunks:
        print("(No chunks found for this section)")
    else:
        for chunk in chunks:
            print(f"Chunk {chunk['id']} ({chunk['token_count']} tokens):")
            preview = chunk['preview'].replace('\n', ' ')[:120]
            print(f"  {preview}...")
            print()

    print("=" * 80)
    conn.close()


def cmd_search(args):
    """Search chunks by keyword."""
    conn = connect_db(args.db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            pc.id,
            pc.token_count,
            s.heading,
            substr(pc.content, 1, 200) as preview
        FROM parent_chunks pc
        JOIN sections s ON pc.section_id = s.id
        WHERE pc.content LIKE ?
        ORDER BY pc.id
        LIMIT ?
    """, (f'%{args.keyword}%', args.limit))

    results = cursor.fetchall()

    conn.close()

    # Build output
    lines = []
    lines.append("=" * 80)
    lines.append(f"SEARCH RESULTS: '{args.keyword}' ({len(results)} matches)")
    lines.append("=" * 80)
    lines.append("")

    if not results:
        lines.append("(No matches found)")
    else:
        for result in results:
            lines.append(f"Chunk {result['id']} - {result['heading']} ({result['token_count']} tokens)")
            preview = result['preview'].replace('\n', ' ')[:100]
            lines.append(f"  {preview}...")
            lines.append("")

    output = '\n'.join(lines)

    # Output or export
    if args.export:
        output_path = write_to_markdown(output, "parent_chunks_search.md")
        print(f"✓ Exported search results to {output_path}")
    else:
        print(output)


def main():
    parser = argparse.ArgumentParser(
        description="Inspect parent chunks in the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
    stats       Show statistics and token distribution (use --export to save)
    list        List all sections with chunk counts (use --export to save)
    view        View a specific chunk by ID
    section     Show all chunks for a specific section
    search      Search chunks by keyword (use --export to save)

Examples:
    python scripts/inspect_parent_chunks.py stats
    python scripts/inspect_parent_chunks.py stats --export
    python scripts/inspect_parent_chunks.py list --limit 20 --show-chunks
    python scripts/inspect_parent_chunks.py list --export
    python scripts/inspect_parent_chunks.py view 459
    python scripts/inspect_parent_chunks.py section 3660
    python scripts/inspect_parent_chunks.py search "malaria"
    python scripts/inspect_parent_chunks.py search "malaria" --export

NOTE: Step 3 auto-exports parent_chunks_all.md to data/exports/ for full content review.
        """
    )

    parser.add_argument('--db', type=Path, help="Path to database")

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # stats command
    stats_parser = subparsers.add_parser('stats', help='Show statistics')
    stats_parser.add_argument('--export', action='store_true', help="Export to data/exports/parent_chunks_stats.md")

    # list command
    list_parser = subparsers.add_parser('list', help='List sections with chunks')
    list_parser.add_argument('--limit', type=int, default=100, help="Max sections to show")
    list_parser.add_argument('--show-chunks', action='store_true', help="Show chunk IDs")
    list_parser.add_argument('--export', action='store_true', help="Export to data/exports/parent_chunks_list.md")

    # view command
    view_parser = subparsers.add_parser('view', help='View a specific chunk')
    view_parser.add_argument('chunk_id', type=int, help='Chunk ID to view')

    # section command
    section_parser = subparsers.add_parser('section', help='Show chunks for a section')
    section_parser.add_argument('section_id', type=int, help='Section ID')

    # search command
    search_parser = subparsers.add_parser('search', help='Search chunks')
    search_parser.add_argument('keyword', help='Keyword to search for')
    search_parser.add_argument('--limit', type=int, default=10, help="Max results")
    search_parser.add_argument('--export', action='store_true', help="Export to data/exports/parent_chunks_search.md")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == 'stats':
        cmd_stats(args)
    elif args.command == 'list':
        cmd_list(args)
    elif args.command == 'view':
        cmd_view(args)
    elif args.command == 'section':
        cmd_section(args)
    elif args.command == 'search':
        cmd_search(args)


if __name__ == "__main__":
    main()
