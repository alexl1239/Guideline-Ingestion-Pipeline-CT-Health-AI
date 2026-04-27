#!/usr/bin/env python3
"""
Table Inspection and Comparison Script

Shows original table markdown vs linearized prose for every table block
in the database. Useful for validating Step 3 output quality and as a
showcase of the linearization transformation.

OUTPUT BEHAVIOR:
- All commands print to STDOUT by default
- Add --export to save to data/exports/

COMMANDS:
    compare     Side-by-side diff of original vs linearized (one or all tables)
                Example: python scripts/inspect_tables.py compare
                Example: python scripts/inspect_tables.py compare --block-id 42
                Example: python scripts/inspect_tables.py compare --export

    stats       Summary: total tables, how many linearized, how many pending
                Example: python scripts/inspect_tables.py stats

    view        Show full original + linearized for a single block
                Example: python scripts/inspect_tables.py view 42

    pending     List table blocks that have NOT yet been linearized
                Example: python scripts/inspect_tables.py pending

Usage:
    python scripts/inspect_tables.py stats
    python scripts/inspect_tables.py compare --export
    python scripts/inspect_tables.py compare --block-id 42
    python scripts/inspect_tables.py view 42
    python scripts/inspect_tables.py pending
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Optional


def get_db_path() -> Path:
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    # Auto-detect single .db file in data/
    data_dir = project_root / "data"
    candidates = list(data_dir.glob("*_rag.db"))
    if len(candidates) == 1:
        return candidates[0]
    # Fall back to the config-derived default
    try:
        sys.path.insert(0, str(project_root))
        from src.config import DATABASE_PATH
        return Path(DATABASE_PATH)
    except Exception:
        return data_dir / "ucg23_rag.db"


def get_export_dir() -> Path:
    script_dir = Path(__file__).parent
    return script_dir.parent / "data" / "exports"


def write_export(content: str, filename: str) -> Path:
    export_dir = get_export_dir()
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = export_dir / filename
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return output_path


def connect_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    db_path = db_path or get_db_path()
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _fence(text: str, lang: str = "") -> str:
    """Wrap text in a fenced code block."""
    return f"```{lang}\n{text}\n```"


def cmd_stats(args):
    conn = connect_db(args.db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN text_content IS NOT NULL AND TRIM(text_content) != '' THEN 1 ELSE 0 END) as linearized,
            SUM(CASE WHEN text_content IS NULL OR TRIM(text_content) = '' THEN 1 ELSE 0 END) as pending
        FROM raw_blocks
        WHERE block_type = 'table'
    """)
    row = cursor.fetchone()

    cursor.execute("""
        SELECT
            AVG(LENGTH(markdown_content)) as avg_orig_chars,
            AVG(LENGTH(text_content))     as avg_linear_chars
        FROM raw_blocks
        WHERE block_type = 'table'
          AND text_content IS NOT NULL AND TRIM(text_content) != ''
    """)
    sizes = cursor.fetchone()
    conn.close()

    total = row['total'] or 0
    linearized = row['linearized'] or 0
    pending = row['pending'] or 0
    pct = (linearized / total * 100) if total > 0 else 0

    print("=" * 60)
    print("TABLE LINEARIZATION STATS")
    print("=" * 60)
    print(f"Total table blocks:    {total}")
    print(f"Linearized (Step 3):   {linearized}  ({pct:.0f}%)")
    print(f"Pending:               {pending}")
    if linearized > 0:
        print()
        print(f"Avg original length:   {sizes['avg_orig_chars']:.0f} chars")
        print(f"Avg linearized length: {sizes['avg_linear_chars']:.0f} chars")
        ratio = (sizes['avg_linear_chars'] / sizes['avg_orig_chars']) if sizes['avg_orig_chars'] else 0
        print(f"Expansion ratio:       {ratio:.2f}x")
    if pending > 0:
        print()
        print(f"Run: python -m src.pipeline.step3_tables  (to linearize {pending} remaining)")
    print("=" * 60)


def cmd_pending(args):
    conn = connect_db(args.db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            rb.id,
            rb.page_number,
            rb.page_range,
            s.heading_path,
            LENGTH(rb.markdown_content) as md_chars
        FROM raw_blocks rb
        LEFT JOIN sections s ON rb.section_id = s.id
        WHERE rb.block_type = 'table'
          AND (rb.text_content IS NULL OR TRIM(rb.text_content) = '')
        ORDER BY rb.page_number, rb.id
    """)
    rows = cursor.fetchall()
    conn.close()

    print("=" * 70)
    print(f"PENDING TABLE BLOCKS ({len(rows)} not yet linearized)")
    print("=" * 70)
    if not rows:
        print("All tables have been linearized.")
    for row in rows:
        pages = row['page_range'] or str(row['page_number'])
        path = (row['heading_path'] or '(no section)')[:60]
        print(f"  Block {row['id']:4d}  p.{pages:<6}  {row['md_chars']:4d} chars  {path}")
    print("=" * 70)


def cmd_view(args):
    conn = connect_db(args.db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            rb.id,
            rb.page_number,
            rb.page_range,
            rb.markdown_content,
            rb.text_content,
            s.heading_path
        FROM raw_blocks rb
        LEFT JOIN sections s ON rb.section_id = s.id
        WHERE rb.id = ?
          AND rb.block_type = 'table'
    """, (args.block_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        print(f"Error: No table block with id={args.block_id}", file=sys.stderr)
        sys.exit(1)

    pages = row['page_range'] or str(row['page_number'])
    path = row['heading_path'] or '(no section)'
    orig = row['markdown_content'] or '(empty)'
    linear = row['text_content'] or '(not yet linearized — run Step 3)'

    print("=" * 80)
    print(f"TABLE BLOCK {row['id']}  —  Page {pages}")
    print("=" * 80)
    print(f"Section: {path}")
    print()
    print("─" * 40 + " ORIGINAL MARKDOWN " + "─" * 21)
    print(orig)
    print()
    print("─" * 40 + " LINEARIZED PROSE  " + "─" * 21)
    print(linear)
    print("=" * 80)


def cmd_compare(args):
    conn = connect_db(args.db)
    cursor = conn.cursor()

    if args.block_id is not None:
        cursor.execute("""
            SELECT
                rb.id,
                rb.page_number,
                rb.page_range,
                rb.markdown_content,
                rb.text_content,
                s.heading_path
            FROM raw_blocks rb
            LEFT JOIN sections s ON rb.section_id = s.id
            WHERE rb.id = ?
              AND rb.block_type = 'table'
        """, (args.block_id,))
        rows = cursor.fetchall()
        if not rows:
            print(f"Error: No table block with id={args.block_id}", file=sys.stderr)
            conn.close()
            sys.exit(1)
    else:
        where_clause = ""
        if not args.all:
            where_clause = "AND rb.text_content IS NOT NULL AND TRIM(rb.text_content) != ''"
        cursor.execute(f"""
            SELECT
                rb.id,
                rb.page_number,
                rb.page_range,
                rb.markdown_content,
                rb.text_content,
                s.heading_path
            FROM raw_blocks rb
            LEFT JOIN sections s ON rb.section_id = s.id
            WHERE rb.block_type = 'table'
              {where_clause}
            ORDER BY rb.page_number, rb.id
        """)
        rows = cursor.fetchall()

    conn.close()

    lines = []
    lines.append("# Table Linearization Comparison")
    lines.append("")
    lines.append(
        f"**{len(rows)} table{'s' if len(rows) != 1 else ''} shown** "
        f"({'all tables' if args.all else 'linearized only'})"
    )
    lines.append("")

    for i, row in enumerate(rows, start=1):
        pages = row['page_range'] or str(row['page_number'])
        path = row['heading_path'] or '*(no section)*'
        orig = (row['markdown_content'] or '*(empty)*').strip()
        linear = (row['text_content'] or '*(not yet linearized)*').strip()

        lines.append(f"---")
        lines.append("")
        lines.append(f"## Table {i} — Block ID {row['id']} (Page {pages})")
        lines.append("")
        lines.append(f"**Section:** {path}")
        lines.append("")
        lines.append("### Original Markdown")
        lines.append("")
        lines.append(_fence(orig, "markdown"))
        lines.append("")
        lines.append("### Linearized Prose")
        lines.append("")
        lines.append(linear)
        lines.append("")

    output = '\n'.join(lines)

    if args.export:
        if args.block_id is not None:
            fname = f"table_compare_block_{args.block_id}.md"
        else:
            fname = "table_compare_all.md"
        out_path = write_export(output, fname)
        print(f"Exported {len(rows)} table comparison(s) to {out_path}")
    else:
        print(output)


def main():
    parser = argparse.ArgumentParser(
        description="Inspect and compare table linearization output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/inspect_tables.py stats
    python scripts/inspect_tables.py compare --export
    python scripts/inspect_tables.py compare --block-id 42
    python scripts/inspect_tables.py compare --all --export
    python scripts/inspect_tables.py view 42
    python scripts/inspect_tables.py pending
        """
    )
    parser.add_argument('--db', type=Path, help="Path to database (auto-detected if omitted)")

    subparsers = parser.add_subparsers(dest='command')

    # stats
    subparsers.add_parser('stats', help='Summary counts and compression stats')

    # pending
    subparsers.add_parser('pending', help='List blocks not yet linearized')

    # view
    view_p = subparsers.add_parser('view', help='Full detail for one block')
    view_p.add_argument('block_id', type=int, help='raw_blocks.id to view')

    # compare
    compare_p = subparsers.add_parser('compare', help='Side-by-side original vs linearized')
    compare_p.add_argument(
        '--block-id', type=int, default=None,
        help='Compare a single block (omit to compare all linearized blocks)'
    )
    compare_p.add_argument(
        '--all', action='store_true',
        help='Include pending (unlinearized) blocks too'
    )
    compare_p.add_argument(
        '--export', action='store_true',
        help='Save output to data/exports/ instead of printing'
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == 'stats':
        cmd_stats(args)
    elif args.command == 'pending':
        cmd_pending(args)
    elif args.command == 'view':
        cmd_view(args)
    elif args.command == 'compare':
        cmd_compare(args)


if __name__ == "__main__":
    main()
