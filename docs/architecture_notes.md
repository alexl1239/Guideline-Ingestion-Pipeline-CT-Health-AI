# UCG-23 RAG ETL Pipeline – Architecture Notes

## 1. System Overview

### Purpose
This ETL pipeline converts the **Uganda Clinical Guidelines 2023 (UCG-23)** PDF document into a single, portable SQLite database with vector search capabilities for offline clinical RAG applications.

### Input
- **Single PDF**: `Uganda_Clinical_Guidelines_2023.pdf` (~1100 pages)
- **No page limit**: Docling processes the entire document in a single pass

### Output
- **Portable database**: `ucg23_rag.db` - Single SQLite file with embedded vectors
- **Complete system**: All data, metadata, and embeddings in one file
- **Offline capable**: No internet required after database creation

### Key Technologies
- **Parser**: Docling (open-source, offline, no API key required)
- **Embeddings**: OpenAI text-embedding-3-small (dimension 1536)
- **Vector search**: sqlite-vec extension
- **Tokenization**: tiktoken with cl100k_base encoding

---

## 2. Parent-Child Chunk Pattern (CRITICAL)

The **parent-child chunk pattern** is the core architectural decision that enables both precise retrieval and complete context delivery.

### Why This Pattern?

**The Problem**:
- **Small chunks** (~256 tokens): Great for precise search, but fragments clinical information
- **Large chunks** (1000+ tokens): Complete context, but less precise search results
- **Traditional approach**: Use one size → compromise on precision OR context

**Our Solution**: Use BOTH sizes with foreign key relationships

```
┌─────────────────────────────────────────┐
│ Parent Chunk (1000-1500 tokens)        │
│ - Complete clinical section             │
│ - Full context for LLM                  │
│ - Example: Entire Malaria section       │
│   with all subsections                  │
└─────────────────────────────────────────┘
           │ parent_id FK
           ├─────────────────────────────┐
           │                             │
           ▼                             ▼
┌──────────────────────┐   ┌──────────────────────┐
│ Child Chunk 1        │   │ Child Chunk 2        │
│ (~256 tokens)        │   │ (~256 tokens)        │
│ - For search/index   │   │ - For search/index   │
│ - Has heading prefix │   │ - Has heading prefix │
│ "Section: Malaria"   │   │ "Section: Malaria"   │
└──────────────────────┘   └──────────────────────┘

RAG Query Flow:
1. Vector search → finds Child Chunks (precise)
2. JOIN child → parent via foreign key
3. Return DISTINCT Parent Chunks to LLM (complete context)
4. No duplication even if multiple children match
```

### Token Size Specifications

**Parent Chunks**:
- **Target**: 1000-1500 tokens
- **Hard max**: 2000 tokens
- **Scope**: Typically one disease or major clinical section
- **Purpose**: Provide complete, coherent clinical information to LLM

**Child Chunks**:
- **Target**: 256 tokens (±10%)
- **Hard max**: 512 tokens
- **Scope**: Focused clinical facts (symptoms, dosages, procedures)
- **Purpose**: Precise retrieval from vector search
- **Format**: Each includes `"Section: {heading_path}\n\n{content}"`

### Benefits

1. **Prevents duplication**: DISTINCT clause ensures each parent returned only once
2. **Maintains context**: LLM sees complete clinical sections, not fragments
3. **Precise retrieval**: Small child chunks enable focused semantic search
4. **Efficient indexing**: Vector embeddings only for child chunks (fewer, smaller)
5. **Clinical accuracy**: Complete treatment protocols stay together in parent chunks

---

## 3. Schema → ETL Pipeline Mapping

The database schema is progressively populated through 8 sequential ETL steps:

| Step | Name | Tables Updated | Purpose |
|------|------|----------------|---------|
| **Step 0** | Registration | `documents`, `embedding_metadata` | Register PDF with checksum, track model versions |
| **Step 1** | Parsing | `raw_blocks` | Extract all content from PDF using Docling |
| **Step 2** | Segmentation | `sections` | Build hierarchical structure (chapters → diseases → subsections) |
| **Step 3** | Cleanup | `parent_chunks` | Clean content, create parent chunks (1000-1500 tokens) |
| **Step 4** | Tables | `parent_chunks` | Linearize complex tables into parent chunks |
| **Step 5** | Chunking | `child_chunks` | Split parents into child chunks (~256 tokens) |
| **Step 6** | Embeddings | `vec_child_chunks` | Generate vector embeddings for child chunks |
| **Step 7** | QA | *(validation only)* | Run validation queries, check data integrity |

### Detailed Step Descriptions

#### Step 0: Document Registration
```sql
-- Insert document with SHA-256 checksum
INSERT INTO documents (filename, sha256_checksum, page_count)
VALUES ('Uganda_Clinical_Guidelines_2023.pdf', '<checksum>', 1100);

-- Track embedding model for reproducibility
INSERT INTO embedding_metadata (model_name, dimension, docling_version)
VALUES ('text-embedding-3-small', 1536, '2.0.0');
```

#### Step 1: Parsing (Docling)
```sql
-- Store raw Docling output blocks
INSERT INTO raw_blocks (document_id, block_type, page_number, markdown_content)
VALUES (1, 'section_header', 145, '## 1.2 Malaria');

INSERT INTO raw_blocks (document_id, block_type, page_number, text_content)
VALUES (1, 'text', 145, 'Malaria is an acute febrile illness...');
```

**Docling Key Features**:
- Processes entire PDF offline (no API key)
- Automatic multi-page table reconstruction
- High-quality reading order for multi-column layouts
- Native header/footer identification

#### Step 2: Structural Segmentation
```sql
-- Build hierarchical structure
INSERT INTO sections (document_id, parent_id, level, heading, heading_path, order_index)
VALUES
  (1, NULL, 1, 'Infectious Diseases', 'Infectious Diseases', 10),
  (1, 10, 2, '1.2 Malaria', 'Infectious Diseases > 1.2 Malaria', 11);
```

**Hierarchy Levels**:
- Level 1: Chapters (e.g., "Infectious Diseases")
- Level 2: Diseases (e.g., "1.2 Malaria")
- Level 3+: Subsections (e.g., "Clinical Features", "Management")

#### Step 3-4: Parent Chunk Construction
```sql
-- Create parent chunk with cleaned, complete content
INSERT INTO parent_chunks (section_id, content, token_count, page_start, page_end)
VALUES (11, '<complete malaria section markdown>', 1247, 145, 148);
```

**Cleanup Operations**:
- Remove page markers, headers, footers
- Normalize bullets and formatting
- Preserve all clinical references (NO paraphrasing)
- Linearize tables into natural language

#### Step 5: Child Chunking
```sql
-- Split parent into child chunks with heading context
INSERT INTO child_chunks (parent_id, chunk_index, content, token_count)
VALUES
  (1, 0, 'Section: Infectious Diseases > 1.2 Malaria\n\n## Clinical Features...', 256),
  (1, 1, 'Section: Infectious Diseases > 1.2 Malaria\n\n## Management...', 258);
```

**Splitting Rules**:
- Respect paragraph boundaries (never split mid-paragraph)
- Respect list boundaries (keep bullet lists together)
- Include heading context prefix on every child
- Target ~256 tokens, max 512 tokens

#### Step 6: Vector Embeddings
```sql
-- Generate embeddings for each child chunk (using OpenAI API)
-- Stored in sqlite-vec virtual table
INSERT INTO vec_child_chunks (chunk_id, embedding)
VALUES (1, <1536-dimensional vector>);
```

**Embedding Process**:
- Batch processing (100 chunks at a time)
- Exponential backoff retry logic
- Transactional (rollback on failure)
- Model: `text-embedding-3-small` (fixed dimension 1536)

---

## 4. RAG Query Pattern

### Core Query: Search Children, Return Parents

```sql
-- Find relevant parent chunks for a user query
SELECT DISTINCT
    p.id AS parent_id,
    p.section_id,
    s.heading_path,
    p.content AS parent_content,
    p.token_count,
    p.page_start,
    p.page_end,
    MIN(distance) AS min_distance
FROM vec_child_chunks v
INNER JOIN child_chunks c ON v.chunk_id = c.id
INNER JOIN parent_chunks p ON c.parent_id = p.id
INNER JOIN sections s ON p.section_id = s.id
WHERE v.embedding MATCH ?  -- Vector similarity search
GROUP BY p.id
ORDER BY min_distance
LIMIT 5;
```

### Query Breakdown

1. **Vector Search**: `vec_child_chunks` finds similar child chunks
2. **Join to Children**: Get child chunk IDs
3. **Join to Parents**: Get parent chunk IDs via `parent_id` foreign key
4. **Join to Sections**: Get section metadata (heading_path, hierarchy)
5. **DISTINCT**: Ensures each parent returned only once
6. **MIN(distance)**: If multiple children match, use closest distance
7. **LIMIT 5**: Return top 5 parent chunks to LLM

### Why DISTINCT is Critical

```
User Query: "How do you treat severe malaria?"

Without DISTINCT:
✗ Returns 4 chunks (2 parents × 2 matching children each)
✗ Duplicated information confuses LLM
✗ Wastes context window

With DISTINCT:
✓ Returns 2 unique parent chunks
✓ Complete, coherent clinical sections
✓ Efficient use of context window
```

---

## 5. Key Design Decisions

### 5.1 Why SQLite?

**Portability**:
- Single file database (~500MB for UCG-23)
- Easy distribution to offline clinics
- No server infrastructure required
- Works on mobile devices, embedded systems

**Performance**:
- Fast local queries (no network latency)
- Excellent read performance for RAG workloads
- sqlite-vec provides efficient vector search

**Simplicity**:
- No configuration or administration
- Atomic transactions for data integrity
- Built-in to Python standard library

### 5.2 Why Docling?

**Offline Processing**:
- No API key required
- No internet connectivity needed
- Processes locally on any machine
- No per-page costs

**Superior Quality**:
- **Multi-page tables**: Automatically reconstructs tables spanning multiple pages
- **Reading order**: Handles multi-column layouts correctly
- **Layout analysis**: Identifies headers, footers, captions accurately
- **No page limit**: Processes entire UCG-23 PDF (1100+ pages) in one pass

**Open Source**:
- Fully auditable code
- Active development by IBM Research
- Community-driven improvements

### 5.3 Why tiktoken?

**Accurate Token Counting**:
- Matches OpenAI's actual tokenization
- Essential for embedding API batch sizing
- Prevents API errors from oversized inputs

**Performance**:
- Fast Rust-based implementation
- Handles large documents efficiently

**Encoding**: `cl100k_base`
- Used by OpenAI's latest models
- Compatible with GPT-4, text-embedding-3-small

### 5.4 Why OpenAI Embeddings?

**Quality**:
- State-of-the-art semantic understanding
- Excellent for medical/clinical text
- Dimension 1536 provides rich representations

**Cost-Effective**:
- text-embedding-3-small: $0.02 per 1M tokens
- UCG-23 (~400K tokens for children) ≈ $0.01
- One-time cost for database creation

**Stability**:
- Consistent results across runs
- Well-documented API
- Reliable uptime

**Alternative**: For fully offline systems, consider using local embedding models (e.g., sentence-transformers) with modified schema.

---

## 6. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                Uganda Clinical Guidelines 2023 PDF          │
│                      (~1100 pages, 150MB)                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ Step 1: Parsing (Docling)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     raw_blocks table                        │
│  • Block type, page number, content                         │
│  • Preserves original Docling structure                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ Step 2: Segmentation
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     sections table                          │
│  • Hierarchical structure (parent_id self-FK)               │
│  • Levels: 1=chapter, 2=disease, 3+=subsection              │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ Steps 3-4: Cleanup & Tables
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  parent_chunks table                        │
│  • Complete sections: 1000-1500 tokens                      │
│  • Cleaned markdown, linearized tables                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ Step 5: Child Chunking
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   child_chunks table                        │
│  • Small units: ~256 tokens each                            │
│  • Includes heading context prefix                          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ Step 6: Embeddings (OpenAI API)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 vec_child_chunks table                      │
│  • Vector embeddings: dimension 1536                        │
│  • Enables semantic search                                  │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ RAG Query Time
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                User Query → Vector Search                   │
│  1. Search vec_child_chunks                                 │
│  2. JOIN to child_chunks                                    │
│  3. JOIN to parent_chunks (DISTINCT)                        │
│  4. Return complete parent content to LLM                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Clinical Accuracy Principles

### No Factual Changes

**Strict Rule**: All transformations are PURELY syntactic
- ✓ Convert tables to bullet lists
- ✓ Remove page headers/footers
- ✓ Normalize bullets (• → -)
- ✗ Paraphrase medical terms
- ✗ Summarize treatment protocols
- ✗ Reorder clinical steps

### Auditability

**Full Traceability**:
- `raw_blocks`: Preserves original Docling output
- `documents.docling_json`: Complete Docling JSON export
- All transformations logged externally (loguru)
- Manual validation checkpoints in Step 7

### Validation Requirements

**From CLAUDE.md**:
- 100% validation: Emergency protocols, vaccine schedules
- 20% sample: Random disease sections
- Automated checks: Dose patterns, age specifications, cross-references

---

## 8. Future Enhancements

### Multi-Document Support

Current schema already supports multiple documents:
```sql
-- Add new guideline version
INSERT INTO documents (filename, sha256_checksum, version)
VALUES ('Uganda_Clinical_Guidelines_2024.pdf', '<new_checksum>', '2024');
```

### Incremental Updates

- Checksum-based version control
- Compare new vs. old document checksums
- Only reprocess changed content
- Preserve historical versions

### Alternative Embedding Models

To use local embeddings (e.g., sentence-transformers):
1. Update `embedding_metadata` table
2. Modify dimension in `vec_child_chunks`
3. Re-generate all embeddings (Step 6)

---

## 9. Summary

**The UCG-23 RAG ETL Pipeline** is designed around three core principles:

1. **Clinical Accuracy First**: No paraphrasing, full traceability, strict validation
2. **Parent-Child Pattern**: Precise retrieval + complete context
3. **Offline Capable**: SQLite + Docling enable complete offline operation

The result is a portable, auditable, clinically accurate RAG system suitable for deployment in resource-limited settings.

**Key Files**:
- `schema_v0.sql`: Complete database schema
- `CLAUDE.md`: Detailed pipeline specifications
- `src/config.py`: Configuration and validation

**Next Steps**: See `QUICKSTART.md` for setup and validation instructions.
