# Quick Start Guide

## Validate the Setup

### 1. Test the Schema

The first step is to verify that the database schema is valid and all tables, indexes, and constraints work correctly.

```bash
# Make script executable (if not already)
chmod +x scripts/test_schema.sh

# Run the test
./scripts/test_schema.sh
```

**Expected output:**
```
==================================
Testing schema_v0.sql
==================================

Step 1: Creating database from schema...
✅ PASS: Schema created successfully

Step 2: Checking all 7 tables exist...
  ✅ documents
  ✅ sections
  ✅ raw_blocks
  ✅ parent_chunks
  ✅ child_chunks
  ✅ embedding_metadata
  ℹ️  vec_child_chunks (requires sqlite-vec extension, checked separately)

Step 3: Testing foreign key constraints...
✅ PASS: Foreign keys working correctly

Step 4: Testing parent-child relationship...
✅ PASS: Parent-child relationship validated

Step 5: Testing section hierarchy (self-referential FK)...
✅ PASS: Section hierarchy working

Step 6: Checking indexes exist...
  ✅ idx_sections_document_id
  ✅ idx_child_chunks_parent_id
  ✅ idx_parent_chunks_section_id
  ✅ idx_raw_blocks_section_id

Step 7: Testing token count constraints...
✅ PASS: Parent chunk constraint (1000-2000 tokens) enforced
✅ PASS: Child chunk constraint (max 512 tokens) enforced

Step 8: Testing views...
  ✅ v_chunk_hierarchy
  ✅ v_section_stats
  ✅ v_document_summary
✅ PASS: Views are queryable

Step 9: Testing schema version tracking...
✅ PASS: Schema version tracking working

==================================
🎉 ALL TESTS PASSED!
==================================
```

---

## 2. Understand the Schema

### Core Tables and Their Purpose

**Document Flow:**
```
PDF → documents → sections → raw_blocks
                      ↓
               parent_chunks → child_chunks → vec_child_chunks
```

**Table Details:**

| Table | Purpose | Key Fields | Populated By |
|-------|---------|------------|--------------|
| `documents` | PDF metadata & checksums | sha256_checksum, docling_json | Step 0 |
| `sections` | Hierarchical structure | heading_path, level, parent_id | Step 2 |
| `raw_blocks` | Docling parsed output | block_type, page_range, docling_level | Step 1 |
| `parent_chunks` | Complete sections (1000-1500 tokens) | content, token_count | Step 3 & 4 |
| `child_chunks` | Search units (~256 tokens) | parent_id, chunk_index | Step 5 |
| `embedding_metadata` | Model tracking | model_name, dimension | Step 0 |
| `vec_child_chunks` | Vector embeddings | embedding FLOAT[1536] | Step 6 |

### Critical Relationship: Parent-Child Chunks

**The Core Architecture Pattern**:

```
Parent Chunk (1 per section)          Child Chunks (3-7 per parent)
├─ Full clinical context              ├─ Small, focused pieces
├─ 1000-1500 tokens                   ├─ ~256 tokens each
└─ Returned to LLM                    └─ Used for search only
```

**Why This Matters**:
- **Small child chunks** = Precise, focused search results
- **Large parent chunks** = Complete, coherent context for LLM
- **No duplication** = Each parent returned only once (using DISTINCT)

### RAG Query Pattern

```sql
-- Search on children, return parents
SELECT DISTINCT p.content
FROM vec_child_chunks v
JOIN child_chunks c ON v.chunk_id = c.id
JOIN parent_chunks p ON c.parent_id = p.id
WHERE v.embedding MATCH ?
LIMIT 5;
```

**Query Flow**:
1. Vector search finds similar child chunks (precise retrieval)
2. Join child → parent via foreign key
3. DISTINCT ensures no duplicate parents
4. Return complete parent content to LLM (full context)

---

## 3. Setup Development Environment

### Prerequisites
- Python 3.9 or higher
- SQLite 3.x (bundled with Python)
- ~500MB disk space for database

### Installation

```bash
# 1. Clone the repository
git clone <repository-url>
cd ugc23-rag-etl-pipeline

# 2. Create virtual environment
python -m venv .venv

# 3. Activate virtual environment
source .venv/bin/activate  # On macOS/Linux
# OR
.venv\Scripts\activate     # On Windows

# 4. Install dependencies
pip install -r requirements.txt

# 5. Configure API keys
cp .env.example .env

# 6. Edit .env and add your OPENAI_API_KEY
nano .env  # or use any text editor
```

**Required in `.env`**:
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

**Optional in `.env`**:
```bash
CLAUDE_API_KEY=your_claude_api_key_here  # For LLM-based processing
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

---

## 4. Run Tests

### Run All Tests

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run with detailed output (shows print statements)
pytest tests/ -v -s

# Run only parent-child chunk tests
pytest tests/test_parent_child_chunks.py -v -s
```

**Expected Output**:
```
tests/test_parent_child_chunks.py::test_parent_child_chunk_creation PASSED
tests/test_parent_child_chunks.py::test_multiple_parents_query_deduplication PASSED

============================== 2 passed in 0.12s ===============================
```

### What the Tests Validate

The parent-child chunk tests verify:
1. ✅ ONE parent chunk per section (1000-2000 tokens)
2. ✅ MULTIPLE child chunks per parent (~256 tokens each)
3. ✅ Foreign key relationships work (children link to parent)
4. ✅ Children include heading context prefix
5. ✅ RAG query pattern works (search children → return parent)
6. ✅ No orphaned chunks (data integrity)
7. ✅ Token counts accurate (using tiktoken)
8. ✅ DISTINCT prevents duplicate parents in results

---

## 5. Inspect the Database Schema

### Using SQLite Command Line

```bash
# Open the test database created by test_schema.sh
sqlite3 test_schema.db

# View all tables
.tables

# View schema for a specific table
.schema parent_chunks

# View all indexes
.indexes

# Run a test query
SELECT * FROM documents;

# Exit SQLite
.quit
```

### Using Python

```python
import sqlite3

# Connect to database
conn = sqlite3.connect('test_schema.db')
cursor = conn.cursor()

# List all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print(cursor.fetchall())

# Check parent-child relationship
cursor.execute("""
    SELECT p.id, COUNT(c.id) as child_count
    FROM parent_chunks p
    LEFT JOIN child_chunks c ON c.parent_id = p.id
    GROUP BY p.id;
""")
print(cursor.fetchall())

conn.close()
```

---

## 6. Understand the ETL Pipeline

### Pipeline Steps Overview

```
Step 0: Registration
  ↓ documents, embedding_metadata

Step 1: Parsing (Docling)
  ↓ raw_blocks

Step 2: Segmentation
  ↓ sections (hierarchy)

Step 3: Cleanup
  ↓ parent_chunks (cleaned)

Step 4: Table Linearization
  ↓ parent_chunks (tables → text)

Step 5: Child Chunking
  ↓ child_chunks (~256 tokens)

Step 6: Embeddings (OpenAI)
  ↓ vec_child_chunks (vectors)

Step 7: QA Validation
  ↓ validation reports
```

### Running Individual Steps

```bash
# Step 0: Register document and create database
python src/pipeline/step0_registration.py

# Step 1: Parse PDF with Docling
python src/pipeline/step1_parsing.py

# Step 2: Build section hierarchy
python src/pipeline/step2_segmentation.py

# ... and so on through step7
```

### Running Full Pipeline

```bash
# Run all steps sequentially
python src/main.py
```

---

## 7. Key Design Decisions (Quick Reference)

### Why SQLite?
- **Portable**: Single file, easy to distribute
- **Offline**: No server, works anywhere
- **Fast**: Excellent for read-heavy RAG workloads

### Why Docling?
- **Offline**: No API key, fully local
- **Quality**: Multi-page tables, accurate layout
- **No limits**: Processes entire 1100-page PDF

### Why OpenAI Embeddings?
- **Quality**: State-of-the-art semantic understanding
- **Cost**: $0.02 per 1M tokens (~$0.01 for UCG-23)
- **Stable**: Reliable API, consistent results

### Why tiktoken?
- **Accurate**: Matches OpenAI's tokenization exactly
- **Fast**: Rust-based implementation
- **Essential**: Prevents API errors from oversized chunks

---

## 8. Common Commands

### Database Operations

```bash
# Create fresh database from schema
sqlite3 data/ucg23_rag.db < schema_v0.sql

# Backup database
cp data/ucg23_rag.db data/ucg23_rag_backup_$(date +%Y%m%d).db

# Check database size
ls -lh data/ucg23_rag.db

# Vacuum database (optimize size)
sqlite3 data/ucg23_rag.db "VACUUM;"

# Analyze for query optimization
sqlite3 data/ucg23_rag.db "ANALYZE;"
```

### View Database Statistics

```bash
# Using provided views
sqlite3 data/ucg23_rag.db "SELECT * FROM v_document_summary;"

# Count all tables
sqlite3 data/ucg23_rag.db <<EOF
SELECT
  (SELECT COUNT(*) FROM documents) AS documents,
  (SELECT COUNT(*) FROM sections) AS sections,
  (SELECT COUNT(*) FROM raw_blocks) AS raw_blocks,
  (SELECT COUNT(*) FROM parent_chunks) AS parents,
  (SELECT COUNT(*) FROM child_chunks) AS children;
EOF
```

### Development Workflow

```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Run tests
pytest tests/ -v

# 3. Test schema changes
./scripts/test_schema.sh

# 4. Run ETL pipeline
python src/main.py

# 5. Inspect results
sqlite3 data/ucg23_rag.db
```

---

## 9. Troubleshooting

### Schema test fails

**Problem**: `./scripts/test_schema.sh` reports errors

**Solution**:
1. Check SQLite version: `sqlite3 --version` (need 3.x)
2. Verify schema_v0.sql exists in project root
3. Check write permissions in current directory
4. Read error messages carefully for specific failures

### API Key errors

**Problem**: `ConfigurationError: OPENAI_API_KEY is not set`

**Solution**:
1. Ensure `.env` file exists (not `.env.example`)
2. Check `.env` contains valid API key
3. Verify no extra spaces around `=` in `.env`
4. Restart terminal after editing `.env`

### Import errors

**Problem**: `ModuleNotFoundError: No module named 'docling'`

**Solution**:
1. Activate virtual environment: `source .venv/bin/activate`
2. Reinstall dependencies: `pip install -r requirements.txt`
3. Check Python version: `python --version` (need 3.9+)

### PDF not found

**Problem**: `Source PDF not found: data/ugc23_raw/Uganda_Clinical_Guidelines_2023.pdf`

**Solution**:
1. Create directory: `mkdir -p data/ugc23_raw`
2. Place PDF in correct location
3. Verify filename matches exactly (case-sensitive)

---

## 10. Next Steps

Once you've validated the setup:

1. **Read Architecture**: `docs/architecture_notes.md` for detailed design rationale
2. **Review Pipeline**: `CLAUDE.md` for complete pipeline documentation
3. **Understand Config**: `src/config.py` for all configuration options
4. **Run ETL**: Follow `README.md` for running the full pipeline
5. **Write Tests**: Add tests in `tests/` for new functionality

---

## 11. Quick Links

- **Schema**: `schema_v0.sql` - Database structure
- **Architecture**: `docs/architecture_notes.md` - Design decisions
- **Pipeline**: `CLAUDE.md` - Complete ETL specification
- **Config**: `src/config.py` - Configuration settings
- **Tests**: `tests/test_parent_child_chunks.py` - Core validation

---

## 12. Support

For issues or questions:
1. Check `CLAUDE.md` for detailed pipeline documentation
2. Review `docs/architecture_notes.md` for design rationale
3. Inspect logs in `logs/` directory
4. Run tests to identify specific failures

**Happy coding!** 🚀
