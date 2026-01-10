# Database Inspection Guide

This document explains how to inspect the UCG-23 RAG ETL pipeline database (`data/ucg23_rag.db`).

## Database Location

The SQLite database is located at:
```
data/ucg23_rag.db
```

## Inspection Methods

### 1. VS Code SQLite Extension

The easiest way to browse the database visually:

1. Install the **SQLite** extension in VS Code (by alexcvzz)
   - Or use **SQLite Viewer** extension (by Florian Klampfer)

2. Open the database:
   - Right-click on `data/ucg23_rag.db` in the Explorer
   - Select "Open Database" or "Open SQLite Database"
   - The database tables will appear in the SQLite Explorer panel

3. Browse tables:
   - Click on any table to view its schema
   - Right-click and "Show Table" to view data
   - Run custom queries in a new SQL file

### 2. SQLite3 CLI

For command-line inspection:

```bash
# Enter interactive mode
sqlite3 data/ucg23_rag.db

# Show all tables
.tables

# Show table schema
.schema documents
.schema sections
.schema raw_blocks
.schema parent_chunks
.schema child_chunks

# Show full schema
.schema

# Run queries
SELECT COUNT(*) FROM documents;
SELECT COUNT(*) FROM sections;
SELECT COUNT(*) FROM parent_chunks;

# Exit
.exit
```

#### Useful CLI Commands

```bash
# Quick table counts
sqlite3 data/ucg23_rag.db "SELECT 'documents', COUNT(*) FROM documents UNION ALL SELECT 'sections', COUNT(*) FROM sections UNION ALL SELECT 'raw_blocks', COUNT(*) FROM raw_blocks UNION ALL SELECT 'parent_chunks', COUNT(*) FROM parent_chunks UNION ALL SELECT 'child_chunks', COUNT(*) FROM child_chunks;"

# Section counts by level
sqlite3 data/ucg23_rag.db "SELECT level, COUNT(*) FROM sections GROUP BY level ORDER BY level;"

# Parent chunk token statistics
sqlite3 data/ucg23_rag.db "SELECT COUNT(*) as count, MIN(token_count) as min, MAX(token_count) as max, AVG(token_count) as avg FROM parent_chunks;"

# Check for token limit violations
sqlite3 data/ucg23_rag.db "SELECT COUNT(*) FROM parent_chunks WHERE token_count > 2000;"

# Sample parent chunks
sqlite3 data/ucg23_rag.db "SELECT id, section_id, token_count, substr(content, 1, 100) FROM parent_chunks LIMIT 5;"
```

### 3. Python Inspection Scripts

The repository includes several inspection scripts:

#### General Database Inspection
```bash
# Full database overview
python scripts/inspect_db.py

# With custom database path
python scripts/inspect_db.py --db data/ucg23_rag.db
```

#### Parent Chunks Listing
```bash
# Print outline of sections with chunk counts
python scripts/list_parent_chunks.py outline

# Show individual chunks under each section
python scripts/list_parent_chunks.py outline --show-chunks

# Dump a specific chunk by ID
python scripts/list_parent_chunks.py dump 42

# Dump in JSON format
python scripts/list_parent_chunks.py dump 42 --format json

# Export all chunks to markdown
python scripts/list_parent_chunks.py export data/exports/parent_chunks_all.md

# Show statistics
python scripts/list_parent_chunks.py stats
```

#### Export Sample Hierarchy
```bash
# Export a section with its raw blocks
python scripts/export_sample_hierarchy.py 21419 sample_export.md
```

### 4. SQL Query File

Run all common inspection queries at once:
```bash
sqlite3 data/ucg23_rag.db < scripts/queries.sql
```

Or run individual queries from the file in any SQLite client.

## Key Tables

| Table | Description | Step Created |
|-------|-------------|--------------|
| `documents` | PDF metadata, checksums, Docling JSON | Step 0 |
| `embedding_metadata` | Embedding model configuration | Step 0 |
| `sections` | Hierarchical structure (chapters, diseases, subsections) | Step 2 |
| `raw_blocks` | Parsed content from Docling | Step 1 |
| `parent_chunks` | Cleaned chunks for RAG (1000-2000 tokens) | Step 3 |
| `child_chunks` | Retrieval units (~256 tokens) | Step 5 |
| `vec_child_chunks` | Vector embeddings (sqlite-vec) | Step 6 |

## Common Inspection Queries

### Document Overview
```sql
SELECT id, title, version_label,
       substr(checksum_sha256, 1, 16) || '...' as checksum,
       created_at
FROM documents;
```

### Section Hierarchy
```sql
-- Counts by level
SELECT level,
       CASE level WHEN 1 THEN 'Chapters'
                  WHEN 2 THEN 'Diseases/Topics'
                  ELSE 'Subsections' END as type,
       COUNT(*) as count
FROM sections
GROUP BY level
ORDER BY level;

-- Sample headings
SELECT level, heading, page_start, page_end
FROM sections
WHERE level = 2
ORDER BY order_index
LIMIT 20;
```

### Parent Chunk Analysis
```sql
-- Token distribution
SELECT
    CASE
        WHEN token_count < 500 THEN '< 500'
        WHEN token_count < 1000 THEN '500-999'
        WHEN token_count < 1500 THEN '1000-1499'
        WHEN token_count < 2000 THEN '1500-1999'
        ELSE '>= 2000'
    END as bucket,
    COUNT(*) as count
FROM parent_chunks
GROUP BY bucket
ORDER BY MIN(token_count);

-- Chunks per section
SELECT s.heading, COUNT(pc.id) as chunks, SUM(pc.token_count) as total_tokens
FROM sections s
LEFT JOIN parent_chunks pc ON pc.section_id = s.id
WHERE s.level = 2
GROUP BY s.id
ORDER BY s.order_index
LIMIT 20;
```

### Data Quality Checks
```sql
-- Orphan blocks (no section assigned)
SELECT COUNT(*) as orphan_blocks
FROM raw_blocks
WHERE section_id IS NULL;

-- Sections without parent chunks
SELECT s.id, s.heading
FROM sections s
LEFT JOIN parent_chunks pc ON pc.section_id = s.id
WHERE s.level = 2 AND pc.id IS NULL;

-- Token limit violations (should be 0)
SELECT id, token_count
FROM parent_chunks
WHERE token_count > 2000;
```

## Troubleshooting

### Database locked
If you see "database is locked" errors:
- Close any other connections to the database
- Check for running Python processes: `ps aux | grep python`
- The database uses WAL mode, so multiple readers are allowed

### sqlite-vec extension errors
The `vec_child_chunks` table requires the sqlite-vec extension:
```bash
# Make sure sqlite-vec is installed
pip install sqlite-vec

# When using Python, the extension is loaded automatically by get_connection()
```

### Empty results
If queries return no data, check which pipeline steps have been run:
```bash
# Check what data exists
python scripts/inspect_db.py
```
