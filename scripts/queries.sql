-- ================================================================
-- UCG-23 RAG ETL Pipeline - Common Inspection Queries
-- ================================================================
-- Usage: sqlite3 data/ucg23_rag.db < scripts/queries.sql
-- Or run individual queries: sqlite3 data/ucg23_rag.db "SELECT ..."
-- ================================================================

-- ================================================================
-- DOCUMENT OVERVIEW
-- ================================================================

-- List all registered documents
.print ""
.print "=== REGISTERED DOCUMENTS ==="
SELECT id, title, version_label, substr(checksum_sha256, 1, 16) || '...' as checksum, created_at
FROM documents;

-- ================================================================
-- SECTION STATISTICS
-- ================================================================

-- Section counts by level
.print ""
.print "=== SECTIONS BY LEVEL ==="
SELECT
    level,
    CASE level
        WHEN 1 THEN 'Chapters'
        WHEN 2 THEN 'Diseases/Topics'
        WHEN 3 THEN 'Subsections'
        ELSE 'Level ' || level
    END as level_name,
    COUNT(*) as count
FROM sections
GROUP BY level
ORDER BY level;

-- Sample level-2 sections (diseases/topics)
.print ""
.print "=== SAMPLE LEVEL-2 SECTIONS (first 10) ==="
SELECT id, heading, page_start, page_end
FROM sections
WHERE level = 2
ORDER BY order_index
LIMIT 10;

-- ================================================================
-- RAW BLOCKS STATISTICS
-- ================================================================

-- Block type distribution
.print ""
.print "=== RAW BLOCK TYPE DISTRIBUTION ==="
SELECT
    block_type,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM raw_blocks), 1) || '%' as percentage
FROM raw_blocks
GROUP BY block_type
ORDER BY count DESC;

-- Blocks without section assignment
.print ""
.print "=== BLOCKS WITHOUT SECTION ASSIGNMENT ==="
SELECT COUNT(*) as orphan_blocks
FROM raw_blocks
WHERE section_id IS NULL;

-- Block coverage by section
.print ""
.print "=== BLOCK ASSIGNMENT COVERAGE ==="
SELECT
    ROUND(
        COUNT(CASE WHEN section_id IS NOT NULL THEN 1 END) * 100.0 / COUNT(*),
        1
    ) || '%' as assigned_percentage,
    COUNT(CASE WHEN section_id IS NOT NULL THEN 1 END) as assigned,
    COUNT(CASE WHEN section_id IS NULL THEN 1 END) as unassigned,
    COUNT(*) as total
FROM raw_blocks;

-- ================================================================
-- PARENT CHUNK STATISTICS
-- ================================================================

-- Parent chunk overview
.print ""
.print "=== PARENT CHUNK OVERVIEW ==="
SELECT
    COUNT(*) as total_chunks,
    MIN(token_count) as min_tokens,
    MAX(token_count) as max_tokens,
    ROUND(AVG(token_count), 1) as avg_tokens,
    SUM(token_count) as total_tokens
FROM parent_chunks;

-- Parent chunk token distribution
.print ""
.print "=== PARENT CHUNK TOKEN DISTRIBUTION ==="
SELECT
    CASE
        WHEN token_count < 500 THEN '< 500'
        WHEN token_count < 1000 THEN '500-999'
        WHEN token_count < 1500 THEN '1000-1499'
        WHEN token_count < 2000 THEN '1500-1999'
        ELSE '>= 2000 (VIOLATION)'
    END as token_range,
    COUNT(*) as chunk_count
FROM parent_chunks
GROUP BY 1
ORDER BY
    CASE
        WHEN token_count < 500 THEN 1
        WHEN token_count < 1000 THEN 2
        WHEN token_count < 1500 THEN 3
        WHEN token_count < 2000 THEN 4
        ELSE 5
    END;

-- Chunks exceeding 2000 token limit (should be zero)
.print ""
.print "=== CHUNKS EXCEEDING 2000 TOKEN LIMIT ==="
SELECT id, section_id, token_count
FROM parent_chunks
WHERE token_count > 2000;

-- Chunks per level-2 section
.print ""
.print "=== CHUNKS PER LEVEL-2 SECTION (sample) ==="
SELECT
    s.id as section_id,
    s.heading,
    COUNT(pc.id) as chunk_count,
    COALESCE(SUM(pc.token_count), 0) as total_tokens
FROM sections s
LEFT JOIN parent_chunks pc ON pc.section_id = s.id
WHERE s.level = 2
GROUP BY s.id
ORDER BY s.order_index
LIMIT 15;

-- Level-2 sections without parent chunks
.print ""
.print "=== LEVEL-2 SECTIONS WITHOUT PARENT CHUNKS ==="
SELECT s.id, s.heading, s.page_start, s.page_end
FROM sections s
LEFT JOIN parent_chunks pc ON pc.section_id = s.id
WHERE s.level = 2 AND pc.id IS NULL
LIMIT 10;

-- ================================================================
-- CHILD CHUNK STATISTICS
-- ================================================================

-- Child chunk overview
.print ""
.print "=== CHILD CHUNK OVERVIEW ==="
SELECT
    COUNT(*) as total_chunks,
    MIN(token_count) as min_tokens,
    MAX(token_count) as max_tokens,
    ROUND(AVG(token_count), 1) as avg_tokens
FROM child_chunks;

-- ================================================================
-- EMBEDDING STATISTICS
-- ================================================================

-- Embedding metadata
.print ""
.print "=== EMBEDDING METADATA ==="
SELECT model_name, dimension, docling_version, created_at
FROM embedding_metadata;

-- Vector embedding count
.print ""
.print "=== VECTOR EMBEDDINGS ==="
SELECT COUNT(*) as embedded_chunks FROM vec_child_chunks;

-- ================================================================
-- DATA QUALITY CHECKS
-- ================================================================

-- Empty parent chunks (should be zero)
.print ""
.print "=== EMPTY PARENT CHUNKS (content issues) ==="
SELECT id, section_id, token_count, LENGTH(content) as content_length
FROM parent_chunks
WHERE content IS NULL OR LENGTH(content) = 0;

-- Parent chunks with null token_count (should be zero)
.print ""
.print "=== PARENT CHUNKS WITH NULL TOKEN_COUNT ==="
SELECT id, section_id FROM parent_chunks WHERE token_count IS NULL;

-- ================================================================
-- USEFUL QUERIES FOR MANUAL INSPECTION
-- ================================================================

-- Find a section by heading text
-- SELECT id, heading, heading_path, page_start, page_end
-- FROM sections
-- WHERE heading LIKE '%Anaphylactic%';

-- Get all parent chunks for a specific section
-- SELECT id, token_count, substr(content, 1, 100) || '...' as content_preview
-- FROM parent_chunks
-- WHERE section_id = ?;

-- Get parent chunks with their section context
-- SELECT pc.id, s.heading, pc.token_count, pc.page_start, pc.page_end
-- FROM parent_chunks pc
-- JOIN sections s ON pc.section_id = s.id
-- ORDER BY s.order_index, pc.id
-- LIMIT 20;

.print ""
.print "=== INSPECTION COMPLETE ==="
