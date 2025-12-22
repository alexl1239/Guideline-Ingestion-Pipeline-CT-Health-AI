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
from typing import Dict, List, Any, Optional

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
    - Tables: Extract from table_cells
    - Other elements: Fall back to 'text' field

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

    # For tables, extract text from cells
    label = element.get('label', '')
    if 'table' in label or label == 'document_index':
        data = element.get('data', {})
        if 'table_cells' in data:
            cells = data['table_cells']
            cell_texts = []
            for cell in cells:
                cell_text = cell.get('text', '').strip()
                if cell_text:
                    cell_texts.append(cell_text)
            if cell_texts:
                # Join with newlines for now (better than nothing)
                return '\n'.join(cell_texts)

    return None


def extract_markdown_content(element: Dict[str, Any]) -> Optional[str]:
    """
    Extract markdown-formatted content from Docling element.

    Especially useful for tables, which Docling can export as markdown.

    Args:
        element: Docling element dict

    Returns:
        Markdown string or None if empty

    Example:
        >>> element = {'markdown': '| Col1 | Col2 |\n|------|------|\n| A | B |'}
        >>> extract_markdown_content(element)
        '| Col1 | Col2 |\n|------|------|\n| A | B |'
    """
    markdown = element.get('markdown', '').strip()
    return markdown if markdown else None


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
    - page_header, page_footer: Running headers (filtered in Step 3)

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
        (e.g., if it has no content)

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

    # Default page number to 0 if missing (required field)
    if page_number is None:
        page_number = 0
        logger.debug(f"Element missing page number, defaulting to 0: {block_type}")

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
    elements = []

    # Docling 2.0: Iterate through element arrays directly
    if 'texts' in doc_json or 'tables' in doc_json:
        logger.info("Detected Docling 2.0 structure with element arrays")

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

    for i, element in enumerate(elements):
        try:
            block_data = extract_block_data(element, document_id)
            if block_data:
                blocks.append(block_data)
            else:
                skipped += 1
        except Exception as e:
            logger.warning(f"Failed to extract block {i}: {e}")
            skipped += 1
            continue

    logger.success(
        f"✓ Extracted {len(blocks)} blocks from {len(elements)} elements "
        f"({skipped} skipped)"
    )

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
]
