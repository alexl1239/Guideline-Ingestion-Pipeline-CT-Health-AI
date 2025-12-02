# Design for Building an Offline RAG Database from Uganda Clinical Guidelines 2023 (UCG‑23)

---

## 1. Purpose and final deliverable

This document describes the end‑to‑end process to convert the Uganda Clinical Guidelines 2023 PDF into a single SQLite database (with `sqlite-vec`) that can be used offline as the knowledge base for a clinical support chatbot.

Key outcomes:

* An SQLite database `ucg23_rag.db` containing:
  * Clean, structured text of UCG‑23
  * Hierarchical sections and parent–child chunks sized for RAG
  * Tables converted into logical text statements
  * Embeddings stored using `sqlite-vec`
* The database exists as a single portable file that can be moved offline.

The design assumes UCG‑23 is the only source, but the schema supports multi-document ingestion—new guidelines can be added incrementally without rebuilding the entire database.

---

## 2. High‑level architecture

### 2.1 Pipeline overview

1. **Document registration**
   * Store original UCG‑23 PDF hash and metadata in SQLite.

2. **Parsing to canonical representation**
   * Primary: Use **LlamaParse** (cloud API) to convert PDF → structured JSON with markdown representations.
   * Fallback: Use **Marker** (local) if offline/local processing is required.

3. **Structural segmentation**
   * Build a heading hierarchy (chapters, diseases, subsections) from parsed output + ToC heuristics.

4. **Cleanup and normalization**
   * Clean markdown, fix spacing, normalize bullets, canonicalize header levels without changing clinical content.

5. **Table → logic conversion**
   * Convert tables into natural‑language logical statements using strict constraints to preserve clinical accuracy.

6. **Parent–child chunking**
   * Create section‑level "parent" chunks (target 1,000–1,500 tokens, hard max 2,000).
   * Split into "child" retrieval chunks (target 256 tokens ± 10%, hard max 512) based on headings.

7. **Embedding generation**
   * Generate embeddings for child chunks and store them using `sqlite-vec` in SQLite.

8. **QA and export**
   * Run structural and semantic checks; database file is ready for distribution.

---

## 3. Technology choices

### 3.1 SQLite + sqlite-vec

* **SQLite** is the primary storage; everything (text, structure, embeddings) is in one database file.
* `sqlite-vec` is an SQLite extension that adds vector similarity search capabilities, enabling vector search alongside relational queries.

Key setup:

```python
import sqlite3
import sqlite_vec

conn = sqlite3.connect('ucg23_rag.db')
conn.enable_load_extension(True)
sqlite_vec.load(conn)
conn.enable_load_extension(False)
```

### 3.2 Parsing engine: LlamaParse (primary) or Marker (fallback)

* **LlamaParse** (primary - cloud API)
  * GenAI‑native parsing platform integrated with LlamaIndex, optimized for complex PDFs, tables, and visual elements.
  * Supports options like merging tables across pages and removing headers/footers in markdown output.
  * Requires Llama Cloud API key and internet connectivity during parsing.
  * Best quality output for complex medical documents.
  * **Note**: LlamaParse supports documents up to 700 pages. UCG-23 will be manually split by a human at a natural section break into two parts for processing.

* **Marker** (fallback - local/offline)
  * Python package and CLI that converts PDFs to markdown quickly and accurately.
  * Designed for books and scientific papers; removes headers/footers, formats tables, extracts images, supports many languages.
  * Purely local (no external API), suitable when offline processing is required.
  * Use when LlamaParse is unavailable or for sensitive documents requiring local processing.

LlamaParse will require a paid API key.

### 3.3 Embedding model

* **OpenAI text-embedding-3-small** (dimension 1536) is the chosen embedding model.
* All tokenization throughout the pipeline will use tiktoken with the cl100k_base encoding.
* **IMPORTANT**: The embedding dimension is fixed in the schema. Changing to a different embedding model (e.g., one with 768 dimensions) requires migrating or regenerating the entire vector table and all embeddings.

---

## 4. Target database schema

This schema is designed so all content and metadata lives inside SQLite, and the single `.db` file is sufficient to recreate the RAG store offline.

### 4.1 Core tables

```sql
CREATE TABLE documents (
  id              TEXT PRIMARY KEY,
  title           TEXT NOT NULL,
  version_label   TEXT NOT NULL,       -- e.g. 'UCG 2023'
  source_url      TEXT,
  checksum_sha256 TEXT NOT NULL,
  pdf_bytes       BLOB,                -- optional: original PDF (trade-off: increases DB size)
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sections (
  id              TEXT PRIMARY KEY,
  document_id     TEXT NOT NULL REFERENCES documents(id),
  parent_id       TEXT REFERENCES sections(id),
  level           INTEGER NOT NULL,    -- 1=chapter, 2=disease/topic, 3+=subsections
  heading         TEXT NOT NULL,
  heading_path    TEXT NOT NULL,       -- e.g. 'Emergencies and Trauma > 1.1.1 Anaphylactic Shock'
  page_start      INTEGER,
  page_end        INTEGER,
  order_index     INTEGER NOT NULL
);

-- from parsing engine output, keep for auditability
CREATE TABLE raw_blocks (
  id              TEXT PRIMARY KEY,
  document_id     TEXT NOT NULL REFERENCES documents(id),
  section_id      TEXT REFERENCES sections(id),
  block_type      TEXT NOT NULL,       -- 'heading' | 'text' | 'table' | 'image' | ...
  page_number     INTEGER,
  sort_key        INTEGER NOT NULL,
  raw_markdown    TEXT,
  raw_json        TEXT                 -- JSON stored as TEXT in SQLite
);

-- Metadata table for auditability
CREATE TABLE embedding_metadata (
  id              INTEGER PRIMARY KEY,
  model_name      TEXT NOT NULL,       -- e.g., 'text-embedding-3-small'
  model_version   TEXT,
  dimension       INTEGER NOT NULL,    -- e.g., 1536
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 Parent/child chunks and embeddings

```sql
CREATE TABLE parent_chunks (
  id              TEXT PRIMARY KEY,
  section_id      TEXT NOT NULL REFERENCES sections(id),
  content         TEXT NOT NULL,
  token_count     INTEGER NOT NULL,
  page_start      INTEGER,
  page_end        INTEGER
);

CREATE TABLE child_chunks (
  id              TEXT PRIMARY KEY,
  parent_id       TEXT NOT NULL REFERENCES parent_chunks(id),
  section_id      TEXT NOT NULL REFERENCES sections(id),
  heading_path    TEXT NOT NULL,
  content         TEXT NOT NULL,       -- includes heading context for better retrieval
  token_count     INTEGER NOT NULL,
  order_index     INTEGER NOT NULL
);

-- Vector storage using sqlite-vec
CREATE VIRTUAL TABLE vec_child_chunks USING vec0(
  chunk_id TEXT PRIMARY KEY,
  embedding FLOAT[1536]  -- dimension matches OpenAI text-embedding-3-small
);
```

### 4.3 Indexes

Recommended indexes for query performance:

```sql
CREATE INDEX idx_sections_doc ON sections(document_id, order_index);
CREATE INDEX idx_sections_heading_path ON sections(heading_path);
CREATE INDEX idx_child_chunks_section ON child_chunks(section_id, order_index);
CREATE INDEX idx_child_chunks_parent ON child_chunks(parent_id);
CREATE INDEX idx_raw_blocks_section ON raw_blocks(section_id, sort_key);
```

---

## 5. ETL pipeline steps

Each step writes into the database within transaction boundaries, making the pipeline resumable and auditable. Progress is logged externally (stdout or application logs); the pipeline is resumable because each ETL step uses strict transaction boundaries and idempotent insert/update patterns.

### 5.1 Step 0 – Document registration

1. Compute the SHA‑256 checksum of the official UCG‑23 PDF.
2. Begin transaction.
3. Insert a row into `documents` with:
   * `id = <generated UUID>`
   * `title = 'Uganda Clinical Guidelines'`
   * `version_label = 'UCG 2023'`
   * `source_url` (Ministry of Health link if available)
   * `checksum_sha256`
   * Optionally `pdf_bytes` (storing the PDF as BLOB is optional—document the size trade-off).
4. Insert embedding metadata into `embedding_metadata` table.
5. Commit transaction.

This ensures provenance and supports future re‑ingestion of updates.

---

### 5.2 Step 1 – Parsing with LlamaParse (primary) or Marker (fallback)

#### 5.2.1 LlamaParse configuration

Use the following specific configuration for UCG-23:

```python
from llama_parse import LlamaParse

parser = LlamaParse(
  api_key="<your-api-key>",
  
  # Maximum pages (UCG will be split into two parts)
  max_pages=700,
  
  # Use agent-based parsing for best quality
  parse_mode="parse_document_with_agent",
  
  # Use Anthropic Sonnet 4.0 for parsing
  model="anthropic-sonnet-4.0",
  
  # High resolution OCR for medical text accuracy
  high_res_ocr=True,
  
  # Handle long tables that span pages
  adaptive_long_table=True,
  
  # Extract tables with outlines
  outlined_table_extraction=True,
  
  # Output tables as HTML for better structure preservation
  output_tables_as_HTML=True,
  
  # Precise bounding boxes for layout preservation
  precise_bounding_box=True,
  
  # Merge tables across pages
  merge_tables_across_pages_in_markdown=True,
  
  # Page separator
  page_separator="\\n \\n",
  
  # Full page processing
  bbox_top=0,
  bbox_left=0,
  
  # Remove headers/footers
  hide_headers=True,
  hide_footers=True,
  
  # Fallback for failed pages
  replace_failed_page_mode="raw_text",
  
  # Extract page numbers for reference
  extract_printed_page_number=True,
)
```

Before processing, the UCG will need to be split into two parts. It is recommended to do this manually at chapter 14.

#### 5.2.2 Processing LlamaParse output

For each parsed block:
* Begin transaction for each batch of 100 blocks.
* Insert into `raw_blocks` with appropriate `block_type`, `raw_markdown`, and `raw_json`.
* Include validation: if critical fields are missing, log warning and flag for manual review.
* Commit transaction.

#### 5.2.3 Marker (fallback option)

Use Marker when:
* Internet connectivity is unavailable
* Local/offline processing is required
* Working with sensitive documents that cannot leave the premises

#### 5.2.4 Parser abstraction

Define an internal canonical block schema with validation:

```python
class CanonicalBlock:
    REQUIRED_FIELDS = {'type', 'page'}
    CRITICAL_FIELDS = {'markdown', 'text'}  # At least one must be present
    
    def __init__(self):
        self.type = None  # 'heading', 'text', 'table', 'image'
        self.text = None
        self.markdown = None
        self.page = None
        self.bbox = None
        self.element_id = None
        self.metadata = {}
        
    def validate(self):
        """Validate that critical fields are present"""
        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if getattr(self, field) is None:
                raise ValueError(f"Missing required field: {field}")
        
        # Check at least one critical field is present
        if not any(getattr(self, field) for field in self.CRITICAL_FIELDS):
            logging.warning(f"Block missing critical content fields on page {self.page}")
            return False
        return True
```

---

### 5.3 Step 2 – Structural segmentation into sections

Goal: reconstruct the logical structure with explicit heuristics for LLM use.

Process:

1. **Heading candidate detection**
   * From `raw_blocks` where `block_type = 'heading'`:
     * Use the `lvl` field from LlamaParse (stored in JSON metadata).
     * Use regex patterns for numbered headings:
       * `^\d+(\.\d+)*\s+` (numbered headings like "18.1.1 National Immunization Schedule").
       * Chapter patterns like `^\d+\s+[A-Z]` (e.g., "18 Immunization").

2. **Handle multi-page tables**
   * LlamaParse marks tables with continuation flags.
   * Merge table fragments before processing.

3. **ToC alignment**
   * Parse the table of contents pages.
   * Fuzzy match ToC entries to heading candidates.

4. **Subsection identification**
   * Within each disease section, look for repeated patterns:
     * `Definition`, `Causes`, `Risk factors`, `Clinical features`, `Complications`, `Differential diagnosis`, `Investigations`, `Management`, `Prevention`.

5. **LLM reconciliation (for problematic areas only)**
   
   **Explicit heuristics for triggering LLM review:**
   * Missing expected subsections (e.g., disease without "Management" section)
   * Heading level inconsistencies (e.g., jump from level 1 to level 3)
   * Ambiguous heading patterns not matching regex
   * Sections with > 10 pages without sub-headings
   
   **Strict LLM prompt template:**
   ```
   You are a structural editor. Your ONLY task is to identify section headings and their hierarchy levels.
   
   STRICT CONSTRAINTS:
   1. Output ONLY JSON with format: [{"heading": "...", "level": N}, ...]
   2. Do NOT modify heading text
   3. Do NOT add content
   4. Do NOT reorder sections
   5. Levels must be 1 (chapter), 2 (disease), or 3+ (subsection)
   
   Input markdown:
   [MARKDOWN HERE]
   
   Output JSON only:
   ```

6. **Persist with transaction boundaries**
   * Begin transaction.
   * Insert nodes into `sections`.
   * Update `raw_blocks.section_id`.
   * Commit transaction.
   * Export section tree to text file for validation.

---

### 5.4 Step 3 – Markdown cleanup and normalization

For each section (in transaction batches):

1. **Remove noise**
   * Strip page markers.
   * Remove header/footer content.
   * For images: If diagnostic flowcharts or critical diagrams are detected, flag for human review to create text summaries.

2. **Normalize characters**
   * Replace LaTeX sequences.
   * Fix word spacing.
   * Clean line breaks in tables.

3. **Standardize bullets**
   * Convert to `-` or `*` lists.

4. **Enforce heading levels**
   * Top chapter: `#`
   * Disease: `##`  
   * Subsections: `###`

5. **Preserve clinical references**
   * Maintain cross-references (e.g., "see Anaphylaxis section").
   * Preserve conditional logic (e.g., "use drug X except if condition Y").

6. **Parent chunk construction**
   
   **Parent Chunk Construction Rule:** After markdown cleanup, all cleaned markdown belonging to a given `section` is concatenated in section order to form the base text of that section. This cleaned, normalized section markdown becomes the input to parent-chunk formation. Typically:
   * 1 parent chunk per disease or topic (i.e., per section with `level = 2`), unless token count exceeds target size.
   * If >2,000 tokens, split only at subsection boundaries (`level ≥ 3`), never mid-paragraph.
   
   ```python
   cleaned_markdown = assemble_cleaned_markdown(section.raw_blocks)
   
   if token_count(cleaned_markdown) <= 2000:
       parent_chunks = [cleaned_markdown]
   else:
       parent_chunks = split_at_subsection_boundaries(cleaned_markdown)
   ```
   
   Parent chunks are authoritative representations of entire clinical topics; child chunks are only for retrieval indexing.

---

### 5.5 Step 4 – Table → logical text transformation

By design, linearize tables with strict clinical accuracy constraints. It is critical to get this correct, as tables in the UCG often detail level of care. In the UCG, some tables align the LOC code with the points, without splitting cells. Look at page 641 (or 644 depending on version) for an example of this issue.

1. **Identify tables**
   * From `raw_blocks` where `block_type = 'table'`.

2. **Handle vaccine schedule tables**
   * Convert each row into precise logical statements preserving all details.

3. **Most tables (< 50 rows, < 10 columns)**
   
   **LLM Prompt Template for Table Transformation:**
   
   ```
   Role: You are a highly specialized Clinical Content Editor for the Uganda Ministry of Health.
   
   Task: Convert the provided table into natural language sentences and bulleted lists.
   
   CRITICAL CONSTRAINT - DO NOT BREAK:
   1. NO FACTUAL CHANGE: Preserve every piece of information exactly. Do not alter any medical term, dosage, age, frequency, criteria, or diagnosis.
   2. PRESERVE LISTS: If a column contains a list, convert to proper Markdown bullets (-)
   3. SYNTACTIC ONLY: Changes must be purely syntactic while maintaining exact clinical meaning
   4. OUTPUT FORMAT: Clean Markdown text only
   
   Source Table Title: [HEADING]
   Table Content (CSV/Markdown):
   [TABLE DATA]
   
   Based only on content above, generate linearized output. Example structure:
   - The guidelines state that [A VALUE] requires [B VALUE]
   - For [A VALUE 2], the recommended action is [B VALUE 2]
   
   Begin Output Below:
   ```

4. **Large/complex tables (> 50 rows or > 10 columns)**
   * Store markdown representation as-is.
   * Create a summary chunk: "This section contains a detailed table of [X] with [Y rows] covering [brief description]."
   * Both table and summary are embedded in the same child chunk to ensure RAG discoverability.

5. **Persist with validation**
   * Run automated checks on linearized text:
     * Regex for dose patterns
     * Numeric comparison with original
     * Age specification verification

---

### 5.6 Step 5 – Parent–child chunking

Use tiktoken with cl100k_base encoding for all tokenization.

1. **Parent chunk formation**
   * Parent chunks were already constructed in Step 3 from the cleaned markdown.
   * Target: 1,000-1,500 tokens (hard max 2,000).
   * One parent per disease/topic when possible.
   * Split at subsection boundaries if exceeding limits.

2. **Child chunk formation**
   * Target: 256 tokens ± 10% (hard max 512).
   * Each child includes its immediate heading as context before the content.
   * Respect paragraph and bullet boundaries.
   * Preserve clinical context and cross-references.

3. **Metadata augmentation**
   * Prepend heading context to child chunk content for better retrieval:
   ```python
   augmented_content = f"Section: {heading_path}\n\n{chunk_content}"
   ```

4. **Persist with validation**
   * Verify token counts are within specified ranges.
   * Ensure no content gaps between chunks.

---

### 5.7 Step 6 – Embedding generation

1. Use OpenAI text-embedding-3-small (dimension 1536).
2. Process in batches with error handling:

```python
def generate_embeddings_with_retry(chunks, batch_size=100, max_retries=3):
    """Generate embeddings with transaction boundaries and retry logic"""
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        conn.execute("BEGIN TRANSACTION")
        
        try:
            for chunk in batch:
                embedding = None
                for attempt in range(max_retries):
                    try:
                        embedding = generate_embedding(chunk.content)
                        break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise
                        time.sleep(2 ** attempt)  # Exponential backoff
                
                cursor.execute(
                    "INSERT INTO vec_child_chunks (chunk_id, embedding) VALUES (?, ?)",
                    (chunk.id, embedding)
                )
            
            conn.execute("COMMIT")
        except Exception as e:
            conn.execute("ROLLBACK")
            logging.error(f"Failed to process batch {i//batch_size}: {e}")
            raise
```

---

### 5.8 Step 7 – QA and validation

#### 5.8.1 Structural QA

* Verify 100% of chapters for section count consistency.
* Ensure all raw_blocks are assigned to sections.
* Validate parent/child chunk coverage without gaps.
* Check multi-page table merging.

#### 5.8.2 Content QA

**Statistical validation requirements:**
* Sample 20% of diseases for full clinical accuracy review.
* 100% validation of emergency protocols.
* 100% validation of vaccine schedules.

**Automated checks:**
* Dose pattern verification (regex for formats like "0.5 mL", "2 drops").
* Age specification preservation ("6, 10 and 14 weeks").
* Numeric consistency between tables and linearized text.
* Cross-reference preservation.

---

### 5.9 Step 8 – Exporting the database

Once ETL is completed and QA passed:

1. Run final validation queries.
2. Execute `VACUUM` to optimize:
   ```sql
   VACUUM;
   ANALYZE;  -- Update query planner statistics
   ```
3. Generate checksum of final database.
4. Document in README:
   * Database size
   * Document count
   * Total chunks
   * Embedding model details
   * Processing date

---

## 6. Query and RAG integration pattern

### 6.1 Building query embeddings

1. Take user question + optional context.
2. Generate embedding with text-embedding-3-small.

### 6.2 Vector similarity search

Using sqlite-vec to retrieve parent chunks only:

```python
# Find similar child chunks, but return only parent chunks
query_embedding = generate_embedding(user_query)

results = cursor.execute("""
    SELECT DISTINCT
        p.id,
        p.section_id,
        p.content,
        p.page_start,
        p.page_end,
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

**Important:** Although similarity search is performed on child chunks for fine-grained retrieval quality, only their corresponding parent chunks are returned to the LLM. This prevents duplication, reduces noise, and ensures the model receives a complete, coherent clinical section as context.

### 6.3 Answer generation

* Provide only parent chunks as context to the LLM.
* Include section headings and page ranges for citations.
* Preserve clinical warnings and contraindications in responses.

---

## 7. Error handling and recovery

### 7.1 Transaction boundaries

* Step 0 (Registration): Single transaction
* Step 1 (Parsing): Batch transactions per 100 blocks
* Step 2 (Segmentation): Single transaction per chapter
* Step 3-4 (Cleanup/Tables): Batch transactions per 10 sections
* Step 5 (Chunking): Batch transactions per disease/topic
* Step 6 (Embeddings): Batch transactions per 100 chunks

### 7.2 Recovery procedures

* Progress is logged externally (stdout or application logs).
* The pipeline is resumable because each ETL step uses strict transaction boundaries and idempotent insert/update patterns.
* On failure: rollback current transaction, log error, resume from last successful batch.
* Manual intervention points flagged in logs for clinical validation.

---

## 8. Version control and updates

* The schema supports multiple documents via the `documents` table.
* New versions of UCG can be added without rebuilding:
  1. Register new document with updated version_label.
  2. Run pipeline for new document only.
  3. Existing chunks remain unchanged.
* Query can filter by document version or search across all versions.

---

## 9. Summary

The pipeline converts UCG‑23 from PDF into a single SQLite database that is:

* **Parser‑flexible**: Primarily LlamaParse with specific configuration for quality, Marker as offline fallback.
* **Clinically accurate**: Strict constraints on content transformation, extensive QA validation.
* **Fully self‑contained**: Single `.db` file with embedded model metadata.
* **Structured hierarchically**: Chapters → diseases → subsections → parent/child chunks.
* **Enriched**: Tables converted to logical statements while preserving all clinical information.
* **Optimized for RAG**: sqlite-vec embeddings with OpenAI text-embedding-3-small on child chunks, but returns parent chunks for context.
* **Production‑ready**: Transaction boundaries, error handling, and recovery procedures with external logging.
* **Extensible**: Supports incremental updates and multi-document management.

The SQLite database file is a single portable artifact that can be distributed and used in offline environments as the core knowledge base of a clinical support chatbot built around the Uganda Clinical Guidelines 2023.
