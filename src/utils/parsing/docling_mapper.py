"""
Docling Element Mapping Utilities

Functions to extract and map data from Docling parser output to database schema.
Handles various Docling JSON structures and formats element data for insertion
into the raw_blocks table.

Docling produces structured JSON with elements that have different fields depending
on their type (text, table, figure, etc.). These utilities normalize that data
into a consistent schema for storage.
"""

import json
import re
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple

from src.utils.logging_config import logger


def extract_page_number(element: Dict[str, Any]) -> Optional[int]:
    """
    Extract page number from Docling element's provenance data.

    Docling stores page information in the 'prov' (provenance) field,
    which can be a list of page references. We take the first page.

    Args:
        element: Docling element dict

    Returns:
        Page number (1-indexed) or None if not found

    Example:
        >>> element = {'prov': [{'page': 5, 'bbox': {...}}]}
        >>> extract_page_number(element)
        5
    """
    # Try provenance list first (Docling 2.0 uses 'page_no')
    provenance = element.get('prov', [])
    if provenance and isinstance(provenance, list) and len(provenance) > 0:
        first_prov = provenance[0]
        if isinstance(first_prov, dict):
            # Docling 2.0 uses 'page_no'
            if 'page_no' in first_prov:
                return first_prov['page_no']
            # Older versions use 'page'
            if 'page' in first_prov:
                return first_prov['page']

    # Fallback to direct page_no field
    if 'page_no' in element:
        return element['page_no']

    return None


def extract_page_range(element: Dict[str, Any]) -> Optional[str]:
    """
    Extract page range for multi-page elements (especially tables).

    For elements that span multiple pages, Docling includes multiple
    provenance entries. We extract the range as "start-end".

    Args:
        element: Docling element dict

    Returns:
        Page range string (e.g., "12-14") or None for single-page elements

    Example:
        >>> element = {'prov': [{'page': 12}, {'page': 13}, {'page': 14}]}
        >>> extract_page_range(element)
        "12-14"
    """
    provenance = element.get('prov', [])

    if not provenance or not isinstance(provenance, list) or len(provenance) <= 1:
        return None

    # Extract all unique page numbers (Docling 2.0 uses 'page_no')
    pages = []
    for prov in provenance:
        if isinstance(prov, dict):
            page_num = prov.get('page_no') or prov.get('page')
            if page_num is not None:
                pages.append(page_num)

    pages = sorted(set(pages))

    # Only return range if spans multiple pages
    if len(pages) > 1:
        return f"{pages[0]}-{pages[-1]}"

    return None


def extract_docling_level(element: Dict[str, Any]) -> Optional[int]:
    """
    Extract hierarchy level from section header elements.

    Docling assigns hierarchy levels to headings (e.g., H1, H2, H3).
    This is stored in the 'level' field for section_header elements.

    Args:
        element: Docling element dict

    Returns:
        Hierarchy level (1, 2, 3, etc.) or None if not a heading

    Example:
        >>> element = {'type': 'section_header', 'level': 2, 'text': '1.1 Introduction'}
        >>> extract_docling_level(element)
        2
    """
    block_type = element.get('type') or element.get('label')

    # Only extract level for heading elements
    if block_type in ('section_header', 'heading', 'title'):
        return element.get('level')

    return None


def extract_bbox(element: Dict[str, Any]) -> Optional[str]:
    """
    Extract bounding box coordinates and format as JSON string.

    Docling provides bounding boxes for precise element positioning.
    Format: {"l": left, "t": top, "r": right, "b": bottom, "page": page_num}

    Args:
        element: Docling element dict

    Returns:
        JSON string with bbox coordinates or None if not available

    Example:
        >>> element = {'bbox': {'l': 100, 't': 200, 'r': 400, 'b': 250}}
        >>> extract_bbox(element)
        '{"l": 100, "t": 200, "r": 400, "b": 250}'
    """
    if 'bbox' in element and element['bbox']:
        try:
            return json.dumps(element['bbox'])
        except (TypeError, ValueError) as e:
            logger.debug(f"Failed to serialize bbox: {e}")
            return None

    return None


def extract_text_content(element: Dict[str, Any]) -> Optional[str]:
    """
    Extract plain text content from Docling element.

    Handles different content types:
    - Text elements: 'text' or 'orig' field
    - Tables: Skipped (use markdown_content instead)
    - Other elements: Fall back to 'text' field

    Note: Tables are skipped here because they use formatted markdown instead.
    The markdown provides proper spacing and alignment.

    Args:
        element: Docling element dict

    Returns:
        Plain text string or None if empty

    Example:
        >>> element = {'text': 'This is the content.'}
        >>> extract_text_content(element)
        'This is the content.'
    """
    # Try direct text field first
    text = element.get('text', '').strip()
    if text:
        return text

    # Try 'orig' field (Docling 2.0 sometimes uses this)
    orig = element.get('orig', '').strip()
    if orig:
        return orig

    return None


def extract_markdown_content(element: Dict[str, Any]) -> Optional[str]:
    """
    Extract markdown-formatted content from Docling element.

    For tables, uses Docling's export_to_markdown() output (added during parsing).
    This provides properly formatted tables with correct spacing and alignment.

    Args:
        element: Docling element dict

    Returns:
        Markdown string or None if empty

    Example:
        >>> element = {'markdown': '| Col1 | Col2 |\n|------|------|\n| A | B |'}
        >>> extract_markdown_content(element)
        '| Col1 | Col2 |\n|------|------|\n| A | B |'
    """
    # Check for markdown field (includes table markdown added during parsing)
    markdown = element.get('markdown', '').strip()
    if markdown:
        return markdown

    # Tables without a markdown export fall back to text_content (set by
    # extract_text_content). Log at WARNING so missing table markdown is visible
    # during step1 runs rather than being silently swallowed.
    block_type = element.get('label') or element.get('type', '')
    if 'table' in block_type.lower():
        logger.warning(
            "Table element has no markdown export — falling back to text_content. "
            "Check that the Docling parser calls export_to_markdown() for all tables."
        )

    return None


def extract_element_id(element: Dict[str, Any]) -> Optional[str]:
    """
    Extract Docling's internal element identifier.

    Docling assigns unique IDs to elements for internal tracking.
    Useful for debugging and cross-referencing.

    Args:
        element: Docling element dict

    Returns:
        Element ID string or None if not available

    Example:
        >>> element = {'id': 'elem_42', 'element_id': 'doc_5_para_10'}
        >>> extract_element_id(element)
        'elem_42'
    """
    return element.get('id') or element.get('element_id')


def extract_block_type(element: Dict[str, Any]) -> str:
    """
    Extract and normalize Docling's block type label.

    Docling uses various field names for element types ('type', 'label').
    This function normalizes across different Docling versions.

    Common block types:
    - section_header: Headings with hierarchy
    - text, paragraph: Body text
    - table: Structured tables
    - figure: Images and diagrams
    - list, list_item: List structures
    - caption: Figure/table captions
    - page_header, page_footer: Running headers (filtered in Step 4)

    Args:
        element: Docling element dict

    Returns:
        Block type string (defaults to 'unknown' if not found)

    Example:
        >>> element = {'type': 'section_header', 'text': 'Introduction'}
        >>> extract_block_type(element)
        'section_header'
    """
    return element.get('type') or element.get('label') or 'unknown'


def extract_metadata(element: Dict[str, Any]) -> str:
    """
    Extract additional metadata from Docling element.

    Captures extra fields that don't map directly to database columns
    but might be useful for debugging or future processing.

    Args:
        element: Docling element dict

    Returns:
        JSON string with metadata

    Example:
        >>> element = {'type': 'text', 'name': 'paragraph_5', 'marker': 'bold'}
        >>> extract_metadata(element)
        '{"docling_type": "text", "name": "paragraph_5", "marker": "bold"}'
    """
    metadata = {
        'docling_type': element.get('type'),
        'docling_label': element.get('label'),
    }

    # Add optional fields if present
    for key in ['name', 'marker', 'enumeration', 'style']:
        if key in element:
            metadata[key] = element[key]

    return json.dumps(metadata, ensure_ascii=False)


def _is_picture_child(element: Dict[str, Any]) -> bool:
    """
    Check if an element is a child of a picture/figure element.

    Docling 2.0 stores a 'parent' reference on each element. Text fragments
    extracted from inside diagrams and flowcharts have a parent pointing to
    a picture element (e.g. {"$ref": "#/pictures/5"}). These fragments are
    typically single words or box labels that are meaningless outside the
    visual context of the figure.

    Args:
        element: Docling element dict

    Returns:
        True if the element's parent is a picture element
    """
    parent = element.get('parent')
    if isinstance(parent, dict):
        ref = parent.get('$ref', '')
        if ref.startswith('#/pictures/'):
            return True
    return False


def extract_block_data(element: Dict[str, Any], document_id: str) -> Optional[Dict[str, Any]]:
    """
    Extract complete block data from Docling element for database insertion.

    This is the main mapping function that combines all extraction functions
    to produce a complete record ready for insertion into raw_blocks table.

    Args:
        element: Docling element dict
        document_id: UUID of the document

    Returns:
        Dict with all raw_blocks fields, or None if element should be skipped
        (e.g., if it has no content or is a figure-internal text fragment)

    Example:
        >>> element = {
        ...     'type': 'text',
        ...     'text': 'This is content.',
        ...     'prov': [{'page': 5}]
        ... }
        >>> block = extract_block_data(element, 'doc-uuid-123')
        >>> block['block_type']
        'text'
        >>> block['page_number']
        5
    """
    # Skip text fragments extracted from inside figures/diagrams.
    # These are box labels, step numbers, and arrow text that are meaningless
    # outside the visual context of the figure.
    if _is_picture_child(element):
        return None

    # Extract basic content
    text_content = extract_text_content(element)
    markdown_content = extract_markdown_content(element)

    # Must have at least one content field
    if not text_content and not markdown_content:
        return None

    # Extract all fields
    block_type = extract_block_type(element)
    page_number = extract_page_number(element)
    page_range = extract_page_range(element)
    docling_level = extract_docling_level(element)
    bbox = extract_bbox(element)
    element_id = extract_element_id(element)
    is_continuation = element.get('is_continuation', False)
    metadata = extract_metadata(element)

    # Default page number to 0 if missing (required field).
    # Log at WARNING — a missing page number means this block will likely be
    # mis-assigned during step2 segmentation and is a sign of malformed Docling output.
    if page_number is None:
        page_number = 0
        logger.warning(f"Element missing page number, defaulting to 0: {block_type}")

    return {
        'document_id': document_id,
        'block_type': block_type,
        'text_content': text_content,
        'markdown_content': markdown_content,
        'page_number': page_number,
        'page_range': page_range,
        'docling_level': docling_level,
        'bbox': bbox,
        'is_continuation': is_continuation,
        'element_id': element_id,
        'metadata': metadata,
    }


def _normalize_for_dedup(text: str) -> str:
    """Lowercase and collapse whitespace for repeated-content matching."""
    if not text:
        return ''
    return ' '.join(text.lower().split())


# Replace runs of digits with a placeholder so per-page numbers (page numbers,
# dates, revision counters) collapse into a single template that can be matched
# across pages. Keeps the surrounding text intact so two unrelated paragraphs
# that both happen to mention numbers don't false-match — they only collide if
# everything else around the digits is identical.
_DIGIT_RUN_RE = re.compile(r'\d+')


def _digit_template(text: str) -> str:
    return _DIGIT_RUN_RE.sub('N', text)


def mark_repeated_content_as_page_headers(
    blocks: List[Dict[str, Any]],
    min_repetitions: int = 3,
    min_text_length: int = 5,
) -> List[Dict[str, Any]]:
    """
    Re-tag text blocks that are page-level boilerplate as `page_header`.

    Some PDFs have running headers, page numbers, and legal disclaimers that
    Docling fails to identify as page-level boilerplate (they come through as
    plain `text` blocks). Step 4's noise filter only excludes `page_header` /
    `page_footer` blocks, so without this re-tag the boilerplate ends up
    duplicated in every parent chunk.

    Two passes — both document-agnostic:

    1. **Exact match**: identical normalized text appears on ≥ N distinct
       pages. Catches static disclaimers, running titles, copyright lines.
    2. **Digit-template match**: text matches a template after replacing
       digit runs with `N` (so `Page 1 of 16` and `Page 2 of 16` both
       collapse to `Page N of N`). Catches per-page footers and bare dates.
       The non-numeric text must still match exactly, so a list of
       paragraphs containing different numbers in different sentences won't
       collide.

    Operates only on `text` blocks — section headers, list items, and tables
    are left alone.

    Args:
        blocks: List of block dicts (mutated in place)
        min_repetitions: Minimum number of distinct pages for a text to count as
            repeated boilerplate
        min_text_length: Skip very short text to avoid false positives on
            single-character noise

    Returns:
        The same blocks list with repeated content re-tagged.
    """
    # bucket key = (kind, normalized_form). Two passes share one structure so
    # a block tagged by either rule is only retagged once.
    page_buckets: Dict[Tuple[str, str], set] = defaultdict(set)
    block_buckets: Dict[Tuple[str, str], list] = defaultdict(list)

    for idx, block in enumerate(blocks):
        if block['block_type'] != 'text':
            continue
        text = block.get('text_content') or ''
        if len(text) < min_text_length:
            continue
        page = block.get('page_number') or 0

        norm = _normalize_for_dedup(text)
        page_buckets[('exact', norm)].add(page)
        block_buckets[('exact', norm)].append(idx)

        template = _normalize_for_dedup(_digit_template(text))
        if template != norm:
            page_buckets[('template', template)].add(page)
            block_buckets[('template', template)].append(idx)

    retagged: set = set()
    for key, pages in page_buckets.items():
        if len(pages) < min_repetitions:
            continue
        for block_idx in block_buckets[key]:
            if block_idx in retagged:
                continue
            blocks[block_idx]['block_type'] = 'page_header'
            retagged.add(block_idx)

    if retagged:
        logger.info(
            f"Re-tagged {len(retagged)} text blocks as page_header "
            f"(content / numeric template repeated on ≥{min_repetitions} distinct pages)"
        )
    return blocks


def _count_table_columns(markdown: str) -> int:
    """Count columns in a markdown table by inspecting the first pipe-delimited row."""
    if not markdown:
        return 0
    for line in markdown.split('\n'):
        line = line.strip()
        if line.startswith('|') and line.endswith('|') and line.count('|') >= 2:
            # `|a|b|c|` has 4 pipes and 3 columns
            return line.count('|') - 1
    return 0


def merge_consecutive_table_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge table blocks on consecutive pages with matching column structure.

    Docling sometimes fails to reconstruct tables that span multiple pages
    (especially when the continuation page does not repeat the header row).
    This pass walks the table blocks in document order and concatenates any
    run of tables on consecutive pages whose column counts match — producing
    one logical block with combined `markdown_content` and a `page_range`
    spanning the run. Continuation blocks are dropped from the returned list.

    Same-page tables are kept separate (different tables); only adjacent-page
    runs with consistent structure are stitched together.

    Args:
        blocks: List of block dicts (originals are mutated; some are dropped)

    Returns:
        New list with continuation table blocks removed and the survivor
        carrying the combined content.
    """
    if not blocks:
        return blocks

    table_indices = [i for i, b in enumerate(blocks) if b.get('block_type') == 'table']
    if len(table_indices) < 2:
        return blocks

    # Order by page so consecutive-page runs are detected even if the JSON
    # listed tables out of page order.
    table_indices.sort(key=lambda i: (blocks[i].get('page_number') or 0, i))

    runs: List[List[int]] = []
    current_run: List[int] = [table_indices[0]]

    for next_idx in table_indices[1:]:
        prev_idx = current_run[-1]
        prev_block = blocks[prev_idx]
        next_block = blocks[next_idx]

        prev_page = prev_block.get('page_number') or 0
        next_page = next_block.get('page_number') or 0

        prev_cols = _count_table_columns(prev_block.get('markdown_content') or '')
        next_cols = _count_table_columns(next_block.get('markdown_content') or '')

        consecutive = next_page == prev_page + 1
        same_shape = prev_cols > 0 and prev_cols == next_cols

        if consecutive and same_shape:
            current_run.append(next_idx)
        else:
            if len(current_run) > 1:
                runs.append(current_run)
            current_run = [next_idx]

    if len(current_run) > 1:
        runs.append(current_run)

    if not runs:
        return blocks

    drop_indices: set = set()
    for run in runs:
        head = blocks[run[0]]
        tail = blocks[run[-1]]

        combined_md = head.get('markdown_content') or ''
        combined_text_parts = [head.get('text_content') or '']

        for idx in run[1:]:
            block = blocks[idx]
            md = block.get('markdown_content') or ''
            txt = block.get('text_content') or ''
            if md:
                combined_md = (combined_md + '\n' + md) if combined_md else md
            if txt:
                combined_text_parts.append(txt)
            drop_indices.add(idx)

        head['markdown_content'] = combined_md
        combined_text = '\n'.join(p for p in combined_text_parts if p)
        head['text_content'] = combined_text or None

        first_page = head.get('page_number')
        last_page = tail.get('page_number')
        if first_page is not None and last_page is not None and first_page != last_page:
            head['page_range'] = f"{first_page}-{last_page}"

    merged_blocks = [b for i, b in enumerate(blocks) if i not in drop_indices]
    logger.info(
        f"Merged {sum(len(r) for r in runs)} table blocks into "
        f"{len(runs)} multi-page tables (dropped {len(drop_indices)} continuation fragments)"
    )
    return merged_blocks


def _resolve_ref(ref_str: str, doc_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Resolve a Docling JSON ref like ``#/texts/5`` to the underlying element dict."""
    if not isinstance(ref_str, str) or not ref_str.startswith('#/'):
        return None
    parts = ref_str[2:].split('/')
    if len(parts) != 2:
        return None
    array_name, idx_str = parts
    try:
        idx = int(idx_str)
    except ValueError:
        return None
    array = doc_json.get(array_name)
    if not isinstance(array, list) or idx < 0 or idx >= len(array):
        return None
    return array[idx]


def _walk_body_children(doc_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Walk ``body.children`` in document order, recursing into groups.

    Docling 2.0 stores elements in separate type-keyed arrays (``texts``,
    ``tables``, ``pictures``, ``groups``); the linear reading order is encoded
    by the refs in ``body.children``. Iterating those arrays independently
    puts every table after every text regardless of position, which destroys
    the document-order signal that step2 segmentation relies on (block IDs are
    assigned in list order, and section boundary walks assume block_id grows
    monotonically with document position).

    Groups are containers (lists, inline groups, captions) holding ordered
    refs to their own children — recursed into so nested elements appear at
    the right spot relative to surrounding paragraphs.
    """
    body = doc_json.get('body')
    if not isinstance(body, dict):
        return []
    children = body.get('children')
    if not isinstance(children, list):
        return []

    ordered: List[Dict[str, Any]] = []
    visited_groups: set = set()

    def visit(ref_str: str) -> None:
        element = _resolve_ref(ref_str, doc_json)
        if element is None:
            return
        if ref_str.startswith('#/groups/'):
            # Guard against malformed self-references.
            if ref_str in visited_groups:
                return
            visited_groups.add(ref_str)
            group_children = element.get('children')
            if isinstance(group_children, list):
                for child in group_children:
                    if isinstance(child, dict):
                        nested_ref = child.get('$ref')
                        if nested_ref:
                            visit(nested_ref)
        else:
            ordered.append(element)

    for child in children:
        if isinstance(child, dict):
            ref = child.get('$ref')
            if ref:
                visit(ref)

    return ordered


def extract_blocks_from_json(doc_json: Dict[str, Any], document_id: str) -> List[Dict[str, Any]]:
    """
    Extract all blocks from Docling JSON output.

    Docling 2.0 uses a reference-based structure where:
    - body.children contains references like {"$ref": "#/texts/0"}
    - Actual elements are in separate arrays: texts, tables, pictures, groups

    This function handles both Docling 2.0 and older structures.

    Args:
        doc_json: Full Docling JSON output (from DoclingDocument.export_to_dict())
        document_id: UUID of the document

    Returns:
        List of block dicts ready for database insertion

    Example:
        >>> doc_json = {'texts': [{...}, ...], 'tables': [{...}, ...]}
        >>> blocks = extract_blocks_from_json(doc_json, 'doc-uuid-123')
        >>> len(blocks)
        20000
    """
    blocks = []
    elements: List[Dict[str, Any]] = []

    # Preferred path: walk body.children to get true document order. Block IDs
    # are auto-assigned by SQLite in the order the rows are inserted, so the
    # order produced here directly determines whether step2's boundary walk
    # works at all.
    ordered_elements = _walk_body_children(doc_json)
    if ordered_elements:
        elements = ordered_elements
        logger.info(
            f"Walked body.children → {len(elements)} elements in document order"
        )

    # Docling 2.0: Iterate through element arrays directly
    elif 'texts' in doc_json or 'tables' in doc_json:
        logger.warning(
            "body.children unavailable — falling back to array concatenation. "
            "Block IDs will NOT reflect document order; section assignment quality will degrade."
        )

        # Collect from all element arrays
        for array_name in ['texts', 'tables', 'pictures', 'groups', 'key_value_items', 'form_items']:
            if array_name in doc_json:
                array_elements = doc_json[array_name]
                if isinstance(array_elements, list):
                    elements.extend(array_elements)
                    logger.info(f"  Found {len(array_elements)} elements in '{array_name}' array")

        logger.info(f"Total elements collected: {len(elements)}")

    # Option 1: Direct 'elements' list (older Docling)
    elif 'elements' in doc_json:
        elements = doc_json['elements']
        logger.info(f"Found {len(elements)} elements in 'elements' key")

    # Option 2: 'body' with nested structure (older Docling)
    elif 'body' in doc_json:
        body = doc_json['body']
        if isinstance(body, list):
            elements = body
        elif isinstance(body, dict) and 'elements' in body:
            elements = body['elements']
        logger.info(f"Found {len(elements)} elements in 'body' key")

    # Option 3: 'pages' with elements per page (older Docling)
    elif 'pages' in doc_json:
        for page in doc_json['pages']:
            if isinstance(page, dict) and 'elements' in page:
                elements.extend(page['elements'])
        logger.info(f"Found {len(elements)} elements across pages")

    # Option 4: Direct list at root (older Docling)
    elif isinstance(doc_json, list):
        elements = doc_json
        logger.info(f"Found {len(elements)} elements at root level")

    if not elements:
        logger.warning("No elements found in Docling JSON output")
        logger.debug(f"JSON keys: {list(doc_json.keys()) if isinstance(doc_json, dict) else 'root is list'}")
        return blocks

    # Extract block data from each element
    logger.info(f"Extracting block data from {len(elements)} elements...")
    skipped = 0
    picture_children_skipped = 0

    for i, element in enumerate(elements):
        try:
            if _is_picture_child(element):
                picture_children_skipped += 1
                skipped += 1
                continue
            block_data = extract_block_data(element, document_id)
            if block_data:
                blocks.append(block_data)
            else:
                skipped += 1
        except Exception as e:
            logger.warning(f"Failed to extract block {i}: {e}")
            skipped += 1
            continue

    if picture_children_skipped > 0:
        logger.info(
            f"Skipped {picture_children_skipped} text fragments from inside "
            f"figures/diagrams (picture children)"
        )

    logger.success(
        f"✓ Extracted {len(blocks)} blocks from {len(elements)} elements "
        f"({skipped} skipped)"
    )

    # Post-processing: catch boilerplate Docling missed and stitch multi-page tables.
    # Order matters — run header detection first so the table merger can ignore
    # repeated boilerplate when reasoning about adjacent pages.
    blocks = mark_repeated_content_as_page_headers(blocks)
    blocks = merge_consecutive_table_blocks(blocks)

    return blocks


__all__ = [
    "extract_page_number",
    "extract_page_range",
    "extract_docling_level",
    "extract_bbox",
    "extract_text_content",
    "extract_markdown_content",
    "extract_element_id",
    "extract_block_type",
    "extract_metadata",
    "extract_block_data",
    "extract_blocks_from_json",
    "mark_repeated_content_as_page_headers",
    "merge_consecutive_table_blocks",
    "_is_picture_child",
    "_walk_body_children",
    "_resolve_ref",
]
