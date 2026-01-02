#!/usr/bin/env python3
"""
Export a sample section hierarchy with raw blocks to markdown.

Usage:
    python scripts/export_sample_hierarchy.py [section_id] [output_file]

Finding section IDs:
    # Browse available sections
    sqlite3 data/ucg23_rag.db "SELECT id, level, heading FROM sections LIMIT 20;"

    # Search for specific topics
    sqlite3 data/ucg23_rag.db "SELECT id, heading FROM sections WHERE heading LIKE '%Shock%';"

    # Count blocks per section
    sqlite3 data/ucg23_rag.db "SELECT section_id, COUNT(*) FROM raw_blocks GROUP BY section_id;"

Examples:
    python scripts/export_sample_hierarchy.py 21419 sample_export.md
    python scripts/export_sample_hierarchy.py 21418  # Exports to stdout
"""

import sqlite3
import sys
import json
from pathlib import Path


def get_section_hierarchy(cursor, section_id):
    """Get the full hierarchy for a section."""
    query = """
    SELECT id, level, heading, heading_path, page_start, page_end, order_index
    FROM sections
    WHERE id = ?
    """
    return cursor.execute(query, (section_id,)).fetchone()


def get_raw_blocks(cursor, section_id):
    """Get all raw blocks for a section."""
    query = """
    SELECT id, block_type, text_content, markdown_content, page_number,
           page_range, docling_level, is_continuation, element_id, metadata
    FROM raw_blocks
    WHERE section_id = ?
    ORDER BY page_number, id
    """
    return cursor.execute(query, (section_id,)).fetchall()


def get_parent_section(cursor, section):
    """Get the parent section by parsing heading_path."""
    heading_path = section[3]  # heading_path
    current_level = section[1]  # level

    if current_level == 1:
        return None  # Top level has no parent

    # Parse parent from heading_path (everything before the last ">")
    parts = heading_path.split(" > ")
    if len(parts) <= 1:
        return None

    parent_path = " > ".join(parts[:-1])

    query = """
    SELECT id, level, heading, heading_path
    FROM sections
    WHERE heading_path = ?
    """
    return cursor.execute(query, (parent_path,)).fetchone()


def get_sibling_sections(cursor, section, context_range=5):
    """Get sibling sections (same level, nearby in order)."""
    current_level = section[1]
    current_order = section[6]  # order_index
    heading_path = section[3]

    # Determine parent path for filtering siblings
    parts = heading_path.split(" > ")
    if len(parts) > 1:
        parent_path_prefix = " > ".join(parts[:-1]) + " > "
    else:
        parent_path_prefix = ""

    query = """
    SELECT id, level, heading, heading_path, order_index
    FROM sections
    WHERE level = ?
      AND heading_path LIKE ?
      AND order_index BETWEEN ? AND ?
    ORDER BY order_index
    """

    return cursor.execute(query, (
        current_level,
        parent_path_prefix + "%",
        current_order - context_range,
        current_order + context_range
    )).fetchall()


def get_child_sections(cursor, section):
    """Get immediate child sections (one level deeper)."""
    heading_path = section[3]
    current_level = section[1]

    query = """
    SELECT id, level, heading, heading_path, order_index,
           (SELECT COUNT(*) FROM raw_blocks WHERE section_id = sections.id) as block_count
    FROM sections
    WHERE level = ?
      AND heading_path LIKE ?
    ORDER BY order_index
    """

    return cursor.execute(query, (
        current_level + 1,
        heading_path + " > %"
    )).fetchall()


def format_metadata(metadata_str):
    """Format metadata JSON for display."""
    if not metadata_str or metadata_str == '{}':
        return None
    try:
        metadata = json.loads(metadata_str)
        return json.dumps(metadata, indent=2)
    except:
        return metadata_str


def export_to_markdown(section, raw_blocks, cursor, output_file=None):
    """Export section hierarchy and raw blocks to markdown."""
    lines = []

    # Header
    lines.append("# Sample Section Export: Hierarchy + Raw Blocks")
    lines.append("")
    lines.append("*Generated from Uganda Clinical Guidelines 2023 ETL Pipeline*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Section Information
    lines.append("## Section Information")
    lines.append("")
    lines.append(f"**Section ID:** {section[0]}")
    lines.append(f"**Level:** {section[1]}")
    lines.append(f"**Heading:** {section[2]}")
    lines.append(f"**Full Path:** {section[3]}")
    lines.append(f"**Pages:** {section[4]}–{section[5]}")
    lines.append(f"**Order Index:** {section[6]}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Hierarchy Context
    lines.append("## Hierarchy Context")
    lines.append("")

    # Parent section
    parent = get_parent_section(cursor, section)
    if parent:
        lines.append(f"**Parent Section:** `{parent[0]}` - {parent[2]}")
    else:
        lines.append("**Parent Section:** *(none - top level)*")
    lines.append("")

    # Sibling sections
    siblings = get_sibling_sections(cursor, section, context_range=10)
    lines.append("**Sibling Sections** (same level):")
    if siblings:
        for sib_id, sib_level, sib_heading, sib_path, sib_order in siblings:
            if sib_id == section[0]:
                lines.append(f"- `{sib_id}` - **{sib_heading}** ← **(current)**")
            else:
                lines.append(f"- `{sib_id}` - {sib_heading}")
    else:
        lines.append("*(none found)*")
    lines.append("")

    # Child sections
    children = get_child_sections(cursor, section)
    lines.append("**Child Sections** (one level deeper):")
    if children:
        for child_id, child_level, child_heading, child_path, child_order, block_count in children:
            lines.append(f"- `{child_id}` - {child_heading} ({block_count} blocks)")
    else:
        lines.append("*(none)*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Raw Blocks
    lines.append(f"## Raw Blocks ({len(raw_blocks)} total)")
    lines.append("")

    for idx, block in enumerate(raw_blocks, 1):
        block_id, block_type, text_content, markdown_content, page_number, \
        page_range, docling_level, is_continuation, element_id, metadata = block

        lines.append(f"### Block {idx} (ID: {block_id})")
        lines.append("")
        lines.append(f"**Type:** `{block_type}`")
        lines.append(f"**Page:** {page_number}")

        if page_range:
            lines.append(f"**Page Range:** {page_range}")

        if docling_level is not None:
            lines.append(f"**Docling Level:** {docling_level}")

        if is_continuation:
            lines.append(f"**Continuation:** {is_continuation}")

        if element_id:
            lines.append(f"**Element ID:** `{element_id}`")

        # Show metadata if it's not empty
        formatted_metadata = format_metadata(metadata)
        if formatted_metadata:
            lines.append(f"**Metadata:**")
            lines.append("```json")
            lines.append(formatted_metadata)
            lines.append("```")

        lines.append("")

        # Content
        if markdown_content:
            lines.append("**Markdown Content:**")
            lines.append("```markdown")
            lines.append(markdown_content.strip())
            lines.append("```")
        elif text_content:
            lines.append("**Text Content:**")
            lines.append("```")
            lines.append(text_content.strip())
            lines.append("```")

        lines.append("")
        lines.append("---")
        lines.append("")

    # Write output
    markdown_output = "\n".join(lines)

    if output_file:
        Path(output_file).write_text(markdown_output)
        print(f"✓ Exported to {output_file}")
    else:
        print(markdown_output)


def main():
    # Get script directory and project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    db_path = project_root / "data" / "ucg23_rag.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python scripts/export_sample_hierarchy.py [section_id] [output_file]")
        print("\nSuggested section IDs:")
        print("  21419 - Anaphylactic Shock > Causes (16 blocks)")
        print("  21422 - Anaphylactic Shock > Management (2 blocks)")
        print("\nOutputs to stdout if no output_file specified")
        print("If filename only (no path), saves to data/exports/")
        sys.exit(1)

    section_id = int(sys.argv[1])

    # Handle output file path
    if len(sys.argv) > 2:
        output_path = Path(sys.argv[2])
        # If just a filename (no directory), save to data/exports/
        if output_path.parent == Path('.'):
            output_file = str(project_root / "data" / "exports" / output_path.name)
        else:
            output_file = sys.argv[2]
    else:
        output_file = None

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get section info
    section = get_section_hierarchy(cursor, section_id)
    if not section:
        print(f"Error: Section {section_id} not found", file=sys.stderr)
        conn.close()
        sys.exit(1)

    # Get raw blocks
    raw_blocks = get_raw_blocks(cursor, section_id)

    if not raw_blocks:
        print(f"Warning: No raw blocks found for section {section_id}", file=sys.stderr)

    # Export
    export_to_markdown(section, raw_blocks, cursor, output_file)

    conn.close()


if __name__ == "__main__":
    main()
