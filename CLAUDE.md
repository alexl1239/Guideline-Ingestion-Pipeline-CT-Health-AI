# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a production ETL pipeline that converts Uganda Clinical Guidelines 2023 (UCG-23) PDF documents into a single, portable SQLite database with vector search capabilities for offline clinical RAG applications.

**Input**: Two PDF files (split at chapter 14, as LlamaParse has 700-page limit)
- `data/ugc23_raw/Uganda_Clinical_Guidelines_2023-part-1.pdf` (55 MB)
- `data/ugc23_raw/Uganda_Clinical_Guidelines_2023-part-2.pdf` (156 MB)

**Output**: `data/ucg23_rag.db` - Single portable SQLite database with `sqlite-vec` embeddings

## Environment Setup

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Required API Keys** (configure in `.env`):
- `LLAMAPARSE_API_KEY`: For LlamaParse cloud parsing (primary parser, requires paid API key)
- `OPENAI_API_KEY`: For embeddings using `text-embedding-3-small`
- `CLAUDE_API_KEY`: Optional, for Claude-based processing

## Running the Pipeline

```bash
# Run full ETL pipeline (when implemented)
python src/main.py

# Run individual steps sequentially (0 through 7)
python src/pipeline/step0_registration.py
python src/pipeline/step1_parsing.py
python src/pipeline/step2_segmentation.py
python src/pipeline/step3_cleanup.py
python src/pipeline/step4_tables.py
python src/pipeline/step5_chunking.py
python src/pipeline/step6_embeddings.py
python src/pipeline/step7_qa.py
```

## Database Inspection

```bash
# View database structure
sqlite3 data/ucg23_rag.db ".tables"
sqlite3 data/ucg23_rag.db ".schema"

# Check document registration
sqlite3 data/ucg23_rag.db "SELECT * FROM documents;"

# Check section hierarchy
sqlite3 data/ucg23_rag.db "SELECT level, heading, heading_path FROM sections ORDER BY order_index LIMIT 20;"

# Check chunk statistics
sqlite3 data/ucg23_rag.db "SELECT COUNT(*) FROM parent_chunks;"
sqlite3 data/ucg23_rag.db "SELECT COUNT(*) FROM child_chunks;"
```

## Pipeline Architecture

The pipeline is an **8-step sequential ETL process** where each step writes to SQLite within transaction boundaries, making it resumable and auditable.

### Core Design Principles

1. **Clinical Accuracy First**: NO factual changes allowed. All transformations are purely syntactic.
2. **Transactional**: Each step uses strict transaction boundaries for atomic operations.
3. **Resumable**: Progress logged externally; idempotent insert/update patterns enable recovery.
4. **Auditable**: Raw parsing output preserved in `raw_blocks` table for full traceability.
5. **Parent-Child Retrieval Pattern**: Search on child chunks, return parent chunks to LLM.

### Step-by-Step Pipeline

#### Step 0: Document Registration
- Compute SHA-256 checksum of PDFs
- Insert into `documents` table with metadata
- Insert embedding metadata into `embedding_metadata` table
- **Transaction**: Single transaction per document
- **Output**: Document provenance and version tracking

#### Step 1: Parsing
- **Primary Parser**: LlamaParse with specific configuration (see below)
- **Fallback Parser**: Marker (for offline/local processing)
- Inserts parsed blocks into `raw_blocks` table
- **Transaction**: Batch transactions per 100 blocks
- **Validation**: Flag missing critical fields for manual review

**LlamaParse Configuration** (MUST use these exact settings):
```python
from llama_parse import LlamaParse

parser = LlamaParse(
    api_key="<your-api-key>",
    max_pages=700,
    parse_mode="parse_document_with_agent",
    model="anthropic-sonnet-4.0",
    high_res_ocr=True,
    adaptive_long_table=True,
    outlined_table_extraction=True,
    output_tables_as_HTML=True,
    precise_bounding_box=True,
    merge_tables_across_pages_in_markdown=True,
    page_separator="\\n \\n",
    bbox_top=0,
    bbox_left=0,
    hide_headers=True,
    hide_footers=True,
    replace_failed_page_mode="raw_text",
    extract_printed_page_number=True,
)
```

#### Step 2: Structural Segmentation
- Reconstruct logical hierarchy: Chapters → Diseases → Subsections
- Use regex patterns for numbered headings: `^\d+(\.\d+)*\s+`
- Fuzzy match ToC entries to heading candidates
- Identify standard disease subsections: Definition, Causes, Risk factors, Clinical features, Complications, Differential diagnosis, Investigations, Management, Prevention
- **LLM reconciliation**: Only for problematic areas (missing subsections, level inconsistencies, ambiguous patterns, sections >10 pages without headings)
- **Transaction**: Single transaction per chapter
- **Output**: Populates `sections` table with hierarchy

**LLM Prompt Constraints** (when needed):
- Output ONLY JSON: `[{"heading": "...", "level": N}, ...]`
- Do NOT modify heading text
- Do NOT add content or reorder sections
- Levels: 1=chapter, 2=disease, 3+=subsection

#### Step 3: Cleanup and Parent Chunk Construction
- Remove noise: page markers, headers/footers
- Normalize characters, standardize bullets, enforce heading levels
- Preserve clinical references and conditional logic
- **Parent Chunk Rule**: Concatenate all cleaned markdown per section (level=2, typically one disease)
  - Target: 1,000-1,500 tokens (hard max 2,000)
  - If >2,000 tokens, split ONLY at subsection boundaries, never mid-paragraph
- **Transaction**: Batch transactions per 10 sections
- **Output**: Parent chunks represent complete clinical topics

#### Step 4: Table Linearization
- **Critical**: Tables in UCG often detail Level of Care (LOC) codes aligned with points without splitting cells (see page 641/644)
- Vaccine schedules: Convert each row into precise logical statements
- Most tables (<50 rows, <10 columns): Use LLM with strict prompt
- Large tables (>50 rows or >10 columns): Store markdown + summary chunk
- **Transaction**: Batch transactions per 10 sections
- **Validation**: Automated checks for dose patterns, numeric consistency, age specifications

**LLM Table Transformation Prompt**:
```
Role: Clinical Content Editor for Uganda Ministry of Health.
Task: Convert table into natural language sentences and bulleted lists.

CRITICAL CONSTRAINTS:
1. NO FACTUAL CHANGE: Preserve every medical term, dosage, age, frequency, criteria, diagnosis exactly
2. PRESERVE LISTS: Convert column lists to proper Markdown bullets (-)
3. SYNTACTIC ONLY: Changes must be purely syntactic
4. OUTPUT FORMAT: Clean Markdown text only

[Provide table data and heading]
```

#### Step 5: Child Chunking
- Target: 256 tokens ± 10% (hard max 512)
- Each child includes heading as context: `f"Section: {heading_path}\n\n{chunk_content}"`
- Respect paragraph and bullet boundaries
- Preserve clinical context and cross-references
- Use tiktoken with cl100k_base encoding
- **Transaction**: Batch transactions per disease/topic
- **Output**: Child chunks for retrieval indexing

#### Step 6: Embedding Generation
- Model: OpenAI `text-embedding-3-small` (dimension 1536)
- **IMPORTANT**: Changing embedding model requires regenerating entire vector table
- Process in batches of 100 with exponential backoff retry logic
- **Transaction**: Batch transactions per 100 chunks with rollback on failure
- Store in `vec_child_chunks` virtual table using `sqlite-vec`

#### Step 7: QA and Validation
- **Structural QA**: 100% of chapters for section consistency, no orphaned blocks, no chunk gaps
- **Statistical Requirements**:
  - 20% sample of diseases for full accuracy review
  - 100% validation of emergency protocols
  - 100% validation of vaccine schedules
- **Automated Checks**: Dose patterns, age specifications, numeric consistency, cross-references

#### Step 8: Database Export
- Run final validation queries
- Execute `VACUUM` and `ANALYZE` to optimize
- Generate checksum of final database
- Document size, counts, model details, processing date

## Database Schema Overview

```
documents                    # Document provenance and checksums
├── sections                 # Hierarchical structure (chapters → diseases → subsections)
│   └── raw_blocks          # Parsed blocks from LlamaParse/Marker (auditability)
└── parent_chunks           # Complete clinical topics (1000-1500 tokens)
    └── child_chunks        # Retrieval units (256 tokens)
        └── vec_child_chunks # Vector embeddings (sqlite-vec)

embedding_metadata           # Model name, version, dimension for reproducibility
```

**Key Schema Details**:
- `sections.heading_path`: Full path string like "Emergencies and Trauma > 1.1.1 Anaphylactic Shock"
- `parent_chunks`: Authoritative clinical topic representations
- `child_chunks`: For retrieval only; includes `heading_path` for context
- `vec_child_chunks`: Virtual table using `sqlite-vec` extension

## RAG Query Pattern

**Critical**: Search is performed on child chunks, but **only parent chunks** are returned to the LLM.

```python
# Find similar child chunks, return parent chunks
query_embedding = generate_embedding(user_query)

results = cursor.execute("""
    SELECT DISTINCT
        p.id, p.section_id, p.content, p.page_start, p.page_end,
        MIN(distance) as min_distance
    FROM vec_child_chunks v
    INNER JOIN child_chunks c ON v.chunk_id = c.id
    INNER JOIN parent_chunks p ON c.parent_id = p.id
    WHERE v.embedding MATCH ?
    GROUP BY p.id
    ORDER BY min_distance
    LIMIT 50
""", (query_embedding,)).fetchall()
```

This prevents duplication and ensures the LLM receives complete, coherent clinical sections.

## Transaction Boundaries

Each pipeline step has specific transaction batching:
- Step 0 (Registration): Single transaction
- Step 1 (Parsing): Per 100 blocks
- Step 2 (Segmentation): Per chapter
- Step 3-4 (Cleanup/Tables): Per 10 sections
- Step 5 (Chunking): Per disease/topic
- Step 6 (Embeddings): Per 100 chunks

On failure: rollback current transaction, log error, resume from last successful batch.

## Configuration Constants

From `src/config.py`:
```python
EMBEDDING_MODEL_NAME = "text-embedding-3-small"
EMBEDDING_DIMENSION = "1536"
CHUNK_TOKEN_TARGET = "256"        # Child chunks
PARENT_TOKEN_TARGET = "1500"      # Parent chunks
```

**Note**: All tokenization uses tiktoken with cl100k_base encoding.

## Parser Abstraction

The codebase uses a canonical block schema with validation:

```python
class CanonicalBlock:
    REQUIRED_FIELDS = {'type', 'page'}
    CRITICAL_FIELDS = {'markdown', 'text'}  # At least one required

    # Attributes: type, text, markdown, page, bbox, element_id, metadata

    def validate(self):
        # Check required fields present
        # Warn if missing critical content fields
```

Both LlamaParse and Marker must convert to this canonical format before database insertion.

## Key Dependencies

- `llama-parse`: Primary PDF parser (cloud API, paid)
- `openai`: Embedding generation
- `sqlite-vec`: Vector search extension for SQLite
- `tiktoken`: Token counting (cl100k_base encoding)
- `llama-index-core`: Document processing utilities
- `loguru`: Structured external logging (logs/ directory)
- `aiosqlite`: Async SQLite operations

## Critical Implementation Notes

1. **Clinical Accuracy**: NO paraphrasing, NO summarization. Only syntactic transformations.
2. **Table LOC Codes**: Pay special attention to Level of Care codes aligned with points without cell splits (page 641/644).
3. **Embedding Model Lock-in**: The 1536 dimension is schema-fixed. Changing models requires full re-ingestion.
4. **Parent-Child Pattern**: This is the core RAG architecture - always search children, return parents.
5. **Manual PDF Split**: UCG must be manually split at chapter 14 before processing due to LlamaParse 700-page limit.
6. **Incremental Updates**: Schema supports multiple documents; new versions can be added without rebuilding.

## Logging and Auditability

- External logging via loguru to `logs/` directory
- All raw parsing output preserved in `raw_blocks` table
- Embedding metadata stored for reproducibility
- Transaction boundaries enable precise recovery points
- Manual intervention points flagged in logs for clinical validation
