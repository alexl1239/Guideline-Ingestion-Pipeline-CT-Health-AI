-- ============================================================================
-- Uganda Clinical Guidelines 2023 RAG Database Schema v0
-- ============================================================================
--
-- This schema defines the complete data model for converting UCG-23 PDF
-- into a queryable RAG system with vector search capabilities.
--
-- Architecture Pattern: Parent-Child Chunk Model
--   - Parent chunks: 1000-1500 tokens (complete clinical context for LLM)
--   - Child chunks: ~256 tokens (precise retrieval units for search)
--   - RAG Query: Search children → Join to parent → Return parent to LLM
--
-- Dependencies: sqlite-vec extension for vector search
-- Tokenization: tiktoken cl100k_base encoding
-- Embeddings: OpenAI text-embedding-3-small (dimension 1536)
--
-- ============================================================================

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- ============================================================================
-- Table 1: documents
-- Purpose: Document provenance, versioning, and checksums
-- Populated by: Step 0 (Registration)
-- ============================================================================

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    sha256_checksum TEXT NOT NULL UNIQUE,  -- Ensures version control
    title TEXT,
    version TEXT,
    page_count INTEGER,
    docling_json TEXT,  -- Full Docling JSON output for traceability
    processed_date TEXT DEFAULT (datetime('now')),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_documents_checksum ON documents(sha256_checksum);
CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename);


-- ============================================================================
-- Table 2: sections
-- Purpose: Hierarchical document structure (chapters → diseases → subsections)
-- Populated by: Step 2 (Segmentation)
-- ============================================================================

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    parent_id INTEGER,  -- Self-referential: points to parent section
    level INTEGER NOT NULL,  -- 1=chapter, 2=disease, 3+=subsection
    heading TEXT NOT NULL,
    heading_path TEXT NOT NULL,  -- Full path: "Chapter > Disease > Subsection"
    order_index INTEGER NOT NULL,  -- Preserve document order
    page_start INTEGER,
    page_end INTEGER,
    created_at TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES sections(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sections_document_id ON sections(document_id);
CREATE INDEX IF NOT EXISTS idx_sections_parent_id ON sections(parent_id);
CREATE INDEX IF NOT EXISTS idx_sections_level ON sections(level);
CREATE INDEX IF NOT EXISTS idx_sections_order ON sections(order_index);


-- ============================================================================
-- Table 3: raw_blocks
-- Purpose: Store raw Docling parsed output for auditability
-- Populated by: Step 1 (Parsing)
-- ============================================================================

CREATE TABLE IF NOT EXISTS raw_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    section_id INTEGER,  -- Linked after segmentation
    block_type TEXT NOT NULL,  -- Docling native types: section_header, text, table, etc.
    page_number INTEGER NOT NULL,
    text_content TEXT,  -- Plain text content
    markdown_content TEXT,  -- Markdown formatted content
    page_range TEXT,  -- For multi-page elements (e.g., "12-14")
    docling_level INTEGER,  -- Hierarchy level from Docling
    bbox TEXT,  -- Bounding box as JSON
    is_continuation INTEGER DEFAULT 0,  -- TRUE for continued tables
    element_id TEXT,  -- Docling's internal element ID
    metadata TEXT,  -- Additional metadata as JSON
    created_at TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_blocks_document_id ON raw_blocks(document_id);
CREATE INDEX IF NOT EXISTS idx_raw_blocks_section_id ON raw_blocks(section_id);
CREATE INDEX IF NOT EXISTS idx_raw_blocks_type ON raw_blocks(block_type);
CREATE INDEX IF NOT EXISTS idx_raw_blocks_page ON raw_blocks(page_number);


-- ============================================================================
-- Table 4: parent_chunks
-- Purpose: Complete clinical sections (1000-1500 tokens) for LLM context
-- Populated by: Step 3 (Cleanup) and Step 4 (Table Linearization)
-- ============================================================================

CREATE TABLE IF NOT EXISTS parent_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER NOT NULL,
    content TEXT NOT NULL,  -- Complete cleaned markdown content
    token_count INTEGER NOT NULL,  -- Actual token count (tiktoken cl100k_base)
    page_start INTEGER,
    page_end INTEGER,
    created_at TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE CASCADE,

    -- Constraint: Enforce token limits (1000-2000 tokens)
    CHECK (token_count >= 1000 AND token_count <= 2000)
);

CREATE INDEX IF NOT EXISTS idx_parent_chunks_section_id ON parent_chunks(section_id);
CREATE INDEX IF NOT EXISTS idx_parent_chunks_tokens ON parent_chunks(token_count);


-- ============================================================================
-- Table 5: child_chunks
-- Purpose: Small retrieval units (~256 tokens) for vector search
-- Populated by: Step 5 (Chunking)
-- ============================================================================

CREATE TABLE IF NOT EXISTS child_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,  -- Order within parent (0, 1, 2, ...)
    content TEXT NOT NULL,  -- Includes heading context prefix
    token_count INTEGER NOT NULL,  -- Actual token count (tiktoken cl100k_base)
    created_at TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (parent_id) REFERENCES parent_chunks(id) ON DELETE CASCADE,

    -- Constraint: Enforce hard max token limit (512 tokens)
    CHECK (token_count > 0 AND token_count <= 512),

    -- Ensure unique chunk index per parent
    UNIQUE (parent_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_child_chunks_parent_id ON child_chunks(parent_id);
CREATE INDEX IF NOT EXISTS idx_child_chunks_tokens ON child_chunks(token_count);


-- ============================================================================
-- Table 6: embedding_metadata
-- Purpose: Track embedding model for reproducibility
-- Populated by: Step 0 (Registration)
-- ============================================================================

CREATE TABLE IF NOT EXISTS embedding_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,  -- e.g., "text-embedding-3-small"
    model_version TEXT,
    dimension INTEGER NOT NULL,  -- e.g., 1536
    docling_version TEXT,  -- Docling version used for parsing
    created_at TEXT DEFAULT (datetime('now'))
);


-- ============================================================================
-- Table 7: vec_child_chunks
-- Purpose: Vector embeddings for child chunks (sqlite-vec)
-- Populated by: Step 6 (Embeddings)
--
-- IMPORTANT: This is a virtual table using sqlite-vec extension
-- The embedding dimension (1536) is fixed and tied to the embedding model
-- Changing models requires regenerating the entire table
-- ============================================================================

-- Note: Uncomment when sqlite-vec extension is loaded
-- CREATE VIRTUAL TABLE IF NOT EXISTS vec_child_chunks USING vec0(
--     chunk_id INTEGER PRIMARY KEY,
--     embedding FLOAT[1536]
-- );

-- Placeholder comment for sqlite-vec table:
-- This table will be created after the sqlite-vec extension is loaded.
-- See Step 6 implementation for actual creation logic.


-- ============================================================================
-- Indexes Summary
-- ============================================================================
--
-- All foreign key columns are indexed for query performance:
--   - idx_sections_document_id
--   - idx_sections_parent_id
--   - idx_raw_blocks_document_id
--   - idx_raw_blocks_section_id
--   - idx_parent_chunks_section_id
--   - idx_child_chunks_parent_id
--
-- Additional indexes for common queries:
--   - idx_documents_checksum (UNIQUE constraint already creates index)
--   - idx_sections_level
--   - idx_sections_order
--   - idx_raw_blocks_type
--   - idx_raw_blocks_page
--   - idx_parent_chunks_tokens
--   - idx_child_chunks_tokens
--
-- ============================================================================


-- ============================================================================
-- Views for Common Queries
-- ============================================================================

-- View: Parent-Child relationship with section info
CREATE VIEW IF NOT EXISTS v_chunk_hierarchy AS
SELECT
    d.filename AS document,
    s.heading_path AS section_path,
    s.level AS section_level,
    p.id AS parent_id,
    p.token_count AS parent_tokens,
    c.id AS child_id,
    c.chunk_index AS child_index,
    c.token_count AS child_tokens,
    p.page_start,
    p.page_end
FROM documents d
JOIN sections s ON s.document_id = d.id
JOIN parent_chunks p ON p.section_id = s.id
JOIN child_chunks c ON c.parent_id = p.id
ORDER BY s.order_index, c.chunk_index;


-- View: Section statistics
CREATE VIEW IF NOT EXISTS v_section_stats AS
SELECT
    s.id AS section_id,
    s.heading_path,
    s.level,
    COUNT(DISTINCT p.id) AS parent_count,
    COUNT(DISTINCT c.id) AS child_count,
    SUM(p.token_count) AS total_parent_tokens,
    SUM(c.token_count) AS total_child_tokens
FROM sections s
LEFT JOIN parent_chunks p ON p.section_id = s.id
LEFT JOIN child_chunks c ON c.parent_id = p.id
GROUP BY s.id
ORDER BY s.order_index;


-- View: Document processing summary
CREATE VIEW IF NOT EXISTS v_document_summary AS
SELECT
    d.id AS document_id,
    d.filename,
    d.version,
    d.page_count,
    d.processed_date,
    COUNT(DISTINCT s.id) AS section_count,
    COUNT(DISTINCT p.id) AS parent_chunk_count,
    COUNT(DISTINCT c.id) AS child_chunk_count,
    SUM(c.token_count) AS total_tokens
FROM documents d
LEFT JOIN sections s ON s.document_id = d.id
LEFT JOIN parent_chunks p ON p.section_id = s.id
LEFT JOIN child_chunks c ON c.parent_id = p.id
GROUP BY d.id;


-- ============================================================================
-- Validation Queries (for testing)
-- ============================================================================

-- Check for orphaned child chunks (should return 0)
-- SELECT COUNT(*) FROM child_chunks
-- WHERE parent_id NOT IN (SELECT id FROM parent_chunks);

-- Check for orphaned parent chunks (should return 0)
-- SELECT COUNT(*) FROM parent_chunks
-- WHERE section_id NOT IN (SELECT id FROM sections);

-- Check for sections without parent chunks (may be valid during processing)
-- SELECT COUNT(*) FROM sections
-- WHERE id NOT IN (SELECT section_id FROM parent_chunks);

-- Check token count distributions
-- SELECT
--     'Parent' AS chunk_type,
--     MIN(token_count) AS min_tokens,
--     AVG(token_count) AS avg_tokens,
--     MAX(token_count) AS max_tokens
-- FROM parent_chunks
-- UNION ALL
-- SELECT
--     'Child' AS chunk_type,
--     MIN(token_count) AS min_tokens,
--     AVG(token_count) AS avg_tokens,
--     MAX(token_count) AS max_tokens
-- FROM child_chunks;


-- ============================================================================
-- RAG Query Pattern Example
-- ============================================================================

-- This is the core query pattern for RAG retrieval:
-- 1. Search vec_child_chunks for similar embeddings
-- 2. Join to child_chunks to get chunk IDs
-- 3. Join to parent_chunks to get complete context
-- 4. Return DISTINCT parent content to avoid duplicates

/*
Example RAG query (pseudo-code, requires sqlite-vec):

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
WHERE v.embedding MATCH ?
GROUP BY p.id
ORDER BY min_distance
LIMIT 5;

Note: The DISTINCT ensures that even if multiple child chunks from the same
parent match the query, we only return the parent once.
*/


-- ============================================================================
-- Schema Version Information
-- ============================================================================

-- Store schema version for migration tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version TEXT PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now')),
    description TEXT
);

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('v0', 'Initial schema with 7 core tables and parent-child chunk pattern');


-- ============================================================================
-- End of schema_v0.sql
-- ============================================================================
