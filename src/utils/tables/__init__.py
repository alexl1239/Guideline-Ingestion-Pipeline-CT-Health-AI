"""
Table Utilities (Step 3)

Database operations for querying table blocks and writing linearized prose
back to raw_blocks.text_content. Step 4's clean_block() then consumes the
linearized text during parent chunk construction.
"""

from src.utils.tables.database import (
    get_table_blocks_for_document,
    update_raw_block_text_content,
    batch_update_raw_blocks_text_content,
    count_unlinearized_tables,
    get_document_id_for_tables,
)
from src.utils.tables.table_normalizer import (
    normalize_table_markdown,
    decode_html_entities,
    fix_concatenated_header_words,
    strip_duplicate_header_rows,
)
from src.utils.tables.linearizer import (
    linearize_table,
    SYSTEM_PROMPT,
)

__all__ = [
    # Database operations
    "get_table_blocks_for_document",
    "update_raw_block_text_content",
    "batch_update_raw_blocks_text_content",
    "count_unlinearized_tables",
    "get_document_id_for_tables",
    # Markdown preprocessing
    "normalize_table_markdown",
    "decode_html_entities",
    "fix_concatenated_header_words",
    "strip_duplicate_header_rows",
    # LLM linearization
    "linearize_table",
    "SYSTEM_PROMPT",
]
