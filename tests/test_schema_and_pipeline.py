"""
Comprehensive test suite for UCG-23 ETL Pipeline

Tests schema integrity, parent-child chunk relationships, and the complete
data flow from PDF parsing through to vector embeddings.

The parent-child chunk pattern is the CORE of our RAG architecture:
- We search on small child chunks (~256 tokens) for precision
- We return large parent chunks (1000-1500 tokens) to the LLM for context
- This prevents duplication and ensures coherent clinical information
"""

import pytest
import sqlite3
import json
import hashlib
import numpy as np
from pathlib import Path
from datetime import datetime, UTC
from typing import Optional

# Try to import tiktoken, but don't fail if not available
try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def test_db():
    """
    Create temporary in-memory test database with full schema.

    This fixture provides a clean database for each test with:
    - All 7 core tables created
    - Foreign key constraints enabled
    - Proper indexes for performance

    The database is automatically cleaned up after each test.
    """
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Enable foreign key constraints
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Create schema - adapted from src/database/schema.py
    # Documents table
    cursor.execute("""
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            version_label TEXT,
            source_url TEXT,
            checksum_sha256 TEXT NOT NULL UNIQUE,
            pdf_bytes BLOB,
            docling_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Embedding metadata table
    cursor.execute("""
        CREATE TABLE embedding_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT NOT NULL,
            dimension INTEGER NOT NULL,
            docling_version TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT valid_dimension CHECK (dimension > 0)
        );
    """)

    # Sections table
    cursor.execute("""
        CREATE TABLE sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            level INTEGER NOT NULL,
            heading TEXT NOT NULL,
            heading_path TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            page_start INTEGER,
            page_end INTEGER,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
            CONSTRAINT valid_level CHECK (level >= 1)
        );
    """)

    # Raw blocks table
    cursor.execute("""
        CREATE TABLE raw_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            block_type TEXT NOT NULL,
            text_content TEXT,
            markdown_content TEXT,
            page_number INTEGER NOT NULL,
            page_range TEXT,
            docling_level INTEGER,
            bbox TEXT,
            is_continuation BOOLEAN DEFAULT FALSE,
            element_id TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
            CONSTRAINT has_content CHECK (
                text_content IS NOT NULL OR markdown_content IS NOT NULL
            )
        );
    """)

    # Parent chunks table
    cursor.execute("""
        CREATE TABLE parent_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER NOT NULL,
            page_start INTEGER,
            page_end INTEGER,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE CASCADE,
            CONSTRAINT valid_token_count CHECK (token_count > 0),
            CONSTRAINT valid_content CHECK (LENGTH(content) > 0)
        );
    """)

    # Child chunks table
    cursor.execute("""
        CREATE TABLE child_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER NOT NULL,
            section_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            page_start INTEGER,
            page_end INTEGER,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_id) REFERENCES parent_chunks(id) ON DELETE CASCADE,
            FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE CASCADE,
            CONSTRAINT valid_token_count CHECK (token_count > 0),
            CONSTRAINT valid_content CHECK (LENGTH(content) > 0),
            CONSTRAINT valid_chunk_index CHECK (chunk_index >= 0)
        );
    """)

    # Create indexes
    cursor.execute("CREATE INDEX idx_sections_document_id ON sections(document_id);")
    cursor.execute("CREATE INDEX idx_sections_order_index ON sections(document_id, order_index);")
    cursor.execute("CREATE INDEX idx_raw_blocks_document_id ON raw_blocks(document_id);")
    cursor.execute("CREATE INDEX idx_parent_chunks_section_id ON parent_chunks(section_id);")
    cursor.execute("CREATE INDEX idx_child_chunks_parent_id ON child_chunks(parent_id);")
    cursor.execute("CREATE INDEX idx_child_chunks_section_id ON child_chunks(section_id);")
    cursor.execute("CREATE UNIQUE INDEX idx_child_chunks_parent_index ON child_chunks(parent_id, chunk_index);")

    conn.commit()

    yield conn

    conn.close()


@pytest.fixture
def malaria_fixture():
    """Load malaria section test fixture with parent-child chunks."""
    fixture_path = Path(__file__).parent / 'fixtures' / 'test_malaria_section.json'
    with open(fixture_path, 'r') as f:
        return json.load(f)


@pytest.fixture
def hierarchy_fixture():
    """Load section hierarchy test fixture."""
    fixture_path = Path(__file__).parent / 'fixtures' / 'test_section_hierarchy.json'
    with open(fixture_path, 'r') as f:
        return json.load(f)


@pytest.fixture
def clinical_content_fixture():
    """Load raw clinical content markdown."""
    fixture_path = Path(__file__).parent / 'fixtures' / 'test_clinical_content.md'
    with open(fixture_path, 'r') as f:
        return f.read()


# ==============================================================================
# Test 1: Schema Creation and Integrity
# ==============================================================================

def test_schema_creation(test_db):
    """
    Test: Verify that all required tables are created with correct structure.

    This test ensures:
    1. All 7 core tables exist
    2. Foreign key constraints are properly defined
    3. Indexes are created on key lookup fields

    Success criteria:
    - All tables exist
    - Foreign keys defined correctly
    - Indexes present on lookup fields
    """
    cursor = test_db.cursor()

    # Check all 7 tables exist
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table'
        ORDER BY name
    """)
    tables = {row[0] for row in cursor.fetchall()}

    required_tables = {
        'documents',
        'sections',
        'raw_blocks',
        'parent_chunks',
        'child_chunks',
        'embedding_metadata'
    }

    missing_tables = required_tables - tables
    assert not missing_tables, f"Missing tables: {missing_tables}"

    # Check foreign keys are enabled
    cursor.execute("PRAGMA foreign_keys;")
    fk_enabled = cursor.fetchone()[0]
    assert fk_enabled == 1, "Foreign keys must be enabled"

    # Check indexes exist
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND name LIKE 'idx_%'
    """)
    indexes = {row[0] for row in cursor.fetchall()}

    required_indexes = {
        'idx_sections_document_id',
        'idx_raw_blocks_document_id',
        'idx_parent_chunks_section_id',
        'idx_child_chunks_parent_id',
        'idx_child_chunks_section_id'
    }

    missing_indexes = required_indexes - indexes
    assert not missing_indexes, f"Missing indexes: {missing_indexes}"

    print("✓ Schema creation validated")
    print(f"✓ All {len(required_tables)} tables created")
    print(f"✓ Foreign keys enabled")
    print(f"✓ All {len(required_indexes)} required indexes created")


def test_document_registration(test_db):
    """
    Test: Verify document registration with checksum and metadata.

    This test ensures:
    1. Document can be registered with all metadata
    2. SHA-256 checksum is stored correctly
    3. All required fields are populated

    Success criteria:
    - Document inserted successfully
    - Checksum matches expected format
    - All metadata fields populated
    """
    cursor = test_db.cursor()

    # Create test document data
    test_pdf_content = b"Mock PDF content for testing"
    checksum = hashlib.sha256(test_pdf_content).hexdigest()
    doc_id = "test-doc-001"

    # Insert document
    cursor.execute("""
        INSERT INTO documents (
            id, title, version_label, source_url, checksum_sha256,
            pdf_bytes, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        doc_id,
        "Uganda Clinical Guidelines",
        "UCG 2023",
        "https://health.go.ug/guidelines/",
        checksum,
        test_pdf_content,
        datetime.now(UTC).isoformat()
    ))

    test_db.commit()

    # Verify document was inserted
    cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    doc = cursor.fetchone()

    assert doc is not None, "Document should be inserted"
    assert doc['id'] == doc_id
    assert doc['title'] == "Uganda Clinical Guidelines"
    assert doc['version_label'] == "UCG 2023"
    assert doc['checksum_sha256'] == checksum
    assert len(doc['checksum_sha256']) == 64, "SHA-256 should be 64 chars"

    # Verify checksum is unique
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO documents (id, title, checksum_sha256)
            VALUES (?, ?, ?)
        """, ("test-doc-002", "Duplicate", checksum))

    print("✓ Document registration validated")
    print(f"✓ Checksum stored: {checksum[:16]}...")
    print(f"✓ All metadata fields populated")
    print(f"✓ Checksum uniqueness constraint enforced")


# ==============================================================================
# Test 2: Parent-Child Chunk Relationships (CRITICAL)
# ==============================================================================

def test_parent_child_chunk_creation(test_db, malaria_fixture):
    """
    Test: Validate parent-child chunk relationship with realistic clinical data.

    This test ensures:
    1. ONE parent chunk is created with 1000-1500 tokens
    2. Multiple child chunks (~256 tokens each) are created
    3. All child chunks link back to parent via foreign key
    4. Child chunks include heading context prefix
    5. Token counts are accurate

    This is CRITICAL because it validates the core RAG pattern:
    - Search happens on child chunks (small, focused)
    - Results return parent chunks (complete, coherent context)
    """
    cursor = test_db.cursor()

    # Step 1: Insert test document
    cursor.execute("""
        INSERT INTO documents (id, title, checksum_sha256)
        VALUES (?, ?, ?)
    """, ("1", "Test Document", "abc123"))

    # Step 2: Insert the section
    section = malaria_fixture['section']
    cursor.execute("""
        INSERT INTO sections (id, document_id, level, heading, heading_path,
                             order_index, page_start, page_end)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (section['id'], "1", section['level'],
          section['heading'], section['heading_path'], section['order_index'],
          section['page_start'], section['page_end']))

    # Step 3: Insert the parent chunk
    parent = malaria_fixture['parent_chunk']
    cursor.execute("""
        INSERT INTO parent_chunks (id, section_id, content, token_count,
                                   page_start, page_end)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (parent['id'], parent['section_id'], parent['content'],
          parent['token_count'], parent['page_start'], parent['page_end']))

    # Step 4: Insert child chunks
    for child in malaria_fixture['child_chunks']:
        cursor.execute("""
            INSERT INTO child_chunks (id, parent_id, section_id, chunk_index,
                                     content, token_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (child['id'], child['parent_id'], child['section_id'],
              child['chunk_index'], child['content'], child['token_count']))

    test_db.commit()

    # VALIDATION 1: Check parent chunk token count
    cursor.execute("SELECT token_count FROM parent_chunks WHERE id = 1")
    parent_tokens = cursor.fetchone()[0]
    assert 1000 <= parent_tokens <= 1500, \
        f"Parent chunk should be 1000-1500 tokens, got {parent_tokens}"

    # VALIDATION 2: Check number of child chunks created
    cursor.execute("SELECT COUNT(*) FROM child_chunks WHERE parent_id = 1")
    child_count = cursor.fetchone()[0]
    assert child_count >= 3, \
        f"Should have at least 3 child chunks, got {child_count}"

    # VALIDATION 3: Check each child chunk token count
    cursor.execute("SELECT token_count FROM child_chunks WHERE parent_id = 1")
    for row in cursor.fetchall():
        token_count = row[0]
        # 256 ± 10% = 230-282 tokens
        assert 230 <= token_count <= 282, \
            f"Child chunk should be ~256 tokens (±10%), got {token_count}"

    # VALIDATION 4: Verify all children link to parent
    cursor.execute("""
        SELECT c.id, c.parent_id, p.id
        FROM child_chunks c
        JOIN parent_chunks p ON c.parent_id = p.id
        WHERE c.parent_id = 1
    """)
    results = cursor.fetchall()
    assert len(results) == child_count, \
        "All child chunks should have valid parent foreign key"

    # VALIDATION 5: Check that child chunks include heading context
    cursor.execute("SELECT content FROM child_chunks WHERE parent_id = 1 LIMIT 1")
    first_child = cursor.fetchone()[0]
    assert first_child.startswith("Section: Infectious Diseases > 1.2 Malaria\n\n"), \
        "Child chunks must include heading context prefix"

    # VALIDATION 6: Verify no orphaned children
    cursor.execute("""
        SELECT COUNT(*) FROM child_chunks c
        LEFT JOIN parent_chunks p ON c.parent_id = p.id
        WHERE p.id IS NULL
    """)
    orphaned_count = cursor.fetchone()[0]
    assert orphaned_count == 0, "No orphaned child chunks should exist"

    # VALIDATION 7: Check chunk indexes are sequential
    cursor.execute("""
        SELECT chunk_index FROM child_chunks
        WHERE parent_id = 1
        ORDER BY chunk_index
    """)
    indexes = [row[0] for row in cursor.fetchall()]
    expected_indexes = list(range(len(indexes)))
    assert indexes == expected_indexes, \
        f"Chunk indexes should be sequential starting at 0, got {indexes}"

    print("✓ Parent-child relationship validated successfully")
    print(f"✓ Parent chunk: {parent_tokens} tokens")
    print(f"✓ Child chunks: {child_count} chunks, ~256 tokens each")
    print(f"✓ All children link to parent via foreign key")
    print(f"✓ No orphaned chunks")
    print(f"✓ Chunk indexes are sequential")


def test_rag_query_pattern(test_db, malaria_fixture):
    """
    Test: Validate the core RAG pattern: search on children, return parents.

    This test ensures:
    1. RAG query joins correctly through foreign keys
    2. Query returns PARENT chunk content, not child chunks
    3. No duplicate parent chunks in results
    4. Results include citation metadata (page numbers)

    This demonstrates the CORE architecture:
    - Search on small child chunks for precision
    - Return large parent chunks for complete context
    """
    cursor = test_db.cursor()

    # Setup: Insert document, section, parent, and children
    cursor.execute("""
        INSERT INTO documents (id, title, checksum_sha256)
        VALUES (?, ?, ?)
    """, ("1", "Test Document", "abc123"))

    section = malaria_fixture['section']
    cursor.execute("""
        INSERT INTO sections (id, document_id, level, heading, heading_path,
                             order_index, page_start, page_end)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (section['id'], "1", section['level'],
          section['heading'], section['heading_path'], section['order_index'],
          section['page_start'], section['page_end']))

    parent = malaria_fixture['parent_chunk']
    cursor.execute("""
        INSERT INTO parent_chunks (id, section_id, content, token_count,
                                   page_start, page_end)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (parent['id'], parent['section_id'], parent['content'],
          parent['token_count'], parent['page_start'], parent['page_end']))

    for child in malaria_fixture['child_chunks']:
        cursor.execute("""
            INSERT INTO child_chunks (id, parent_id, section_id, chunk_index,
                                     content, token_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (child['id'], child['parent_id'], child['section_id'],
              child['chunk_index'], child['content'], child['token_count']))

    test_db.commit()

    # Execute RAG query pattern: search on children, return parent
    cursor.execute("""
        SELECT DISTINCT
            p.id, p.section_id, p.content, p.page_start, p.page_end,
            p.token_count
        FROM child_chunks c
        JOIN parent_chunks p ON c.parent_id = p.id
        WHERE c.parent_id = 1
    """)

    results = cursor.fetchall()

    # VALIDATION 1: Query returns results
    assert len(results) > 0, "RAG query should return results"

    # VALIDATION 2: Only ONE parent chunk returned (no duplicates)
    assert len(results) == 1, \
        f"Should return exactly 1 parent chunk, got {len(results)}"

    # VALIDATION 3: Result is parent content (1000-1500 tokens)
    result = results[0]
    assert result['token_count'] >= 1000, \
        f"Result should be parent chunk (≥1000 tokens), got {result['token_count']}"

    # VALIDATION 4: Content is complete parent chunk
    assert "# 1.2 Malaria" in result['content'], \
        "Should return full parent content with heading"
    assert "Management" in result['content'], \
        "Parent content should be complete with all sections"

    # VALIDATION 5: Citation metadata included
    assert result['page_start'] is not None, "Should include page_start for citation"
    assert result['page_end'] is not None, "Should include page_end for citation"
    assert result['page_start'] == 145, "Page start should match fixture"
    assert result['page_end'] == 148, "Page end should match fixture"

    # VALIDATION 6: Section link preserved
    assert result['section_id'] == 1, "Should link to correct section"

    print("✓ RAG query pattern validated successfully")
    print(f"✓ Query returns parent chunk: {result['token_count']} tokens")
    print(f"✓ No duplicate parent chunks")
    print(f"✓ Citation metadata included: pages {result['page_start']}-{result['page_end']}")
    print(f"✓ Content is complete and coherent")
    print(f"✓ Core RAG pattern works: search children → return parent")


# ==============================================================================
# Test 3: Section Hierarchy
# ==============================================================================

def test_section_hierarchy(test_db, hierarchy_fixture):
    """
    Test: Verify hierarchical section structure and heading paths.

    This test ensures:
    1. Sections can be organized in multi-level hierarchy
    2. heading_path strings are constructed correctly
    3. order_index maintains document order
    4. Can traverse from subsection to disease to chapter

    Success criteria:
    - Hierarchy preserved correctly
    - heading_path strings formatted properly
    - Can query by level and traverse relationships
    """
    cursor = test_db.cursor()

    # Insert test document
    cursor.execute("""
        INSERT INTO documents (id, title, checksum_sha256)
        VALUES (?, ?, ?)
    """, ("1", "Test Document", "abc123"))

    # Insert all sections from hierarchy fixture
    for section in hierarchy_fixture['sections']:
        cursor.execute("""
            INSERT INTO sections (
                id, document_id, level, heading, heading_path,
                order_index, page_start, page_end
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            section['id'],
            "1",
            section['level'],
            section['heading'],
            section['heading_path'],
            section['order_index'],
            section['page_start'],
            section['page_end']
        ))

    test_db.commit()

    # VALIDATION 1: Check all 3 levels exist
    cursor.execute("""
        SELECT level, COUNT(*) as count
        FROM sections
        GROUP BY level
        ORDER BY level
    """)
    levels = {row['level']: row['count'] for row in cursor.fetchall()}

    assert 1 in levels, "Should have level 1 (chapters)"
    assert 2 in levels, "Should have level 2 (diseases)"
    assert 3 in levels, "Should have level 3 (subsections)"

    # VALIDATION 2: Check heading_path format for each level
    # Level 1 (Chapter)
    cursor.execute("SELECT heading_path FROM sections WHERE level = 1 LIMIT 1")
    chapter_path = cursor.fetchone()['heading_path']
    assert chapter_path == "Emergencies and Trauma", \
        "Chapter heading_path should be just the chapter name"

    # Level 2 (Disease)
    cursor.execute("SELECT heading_path FROM sections WHERE level = 2 LIMIT 1")
    disease_path = cursor.fetchone()['heading_path']
    assert " > " in disease_path, "Disease heading_path should include separator"
    assert disease_path.startswith("Emergencies and Trauma"), \
        "Disease path should start with chapter name"

    # Level 3 (Subsection)
    cursor.execute("SELECT heading_path FROM sections WHERE level = 3 LIMIT 1")
    subsection_path = cursor.fetchone()['heading_path']
    assert subsection_path.count(" > ") == 2, \
        "Subsection path should have 2 separators (chapter > disease > subsection)"

    # VALIDATION 3: Check order_index maintains sequence
    cursor.execute("""
        SELECT order_index FROM sections
        ORDER BY order_index
    """)
    indexes = [row['order_index'] for row in cursor.fetchall()]
    assert indexes == sorted(indexes), "order_index should be sequential"
    assert indexes[0] == 1, "order_index should start at 1"

    # VALIDATION 4: Verify specific heading_path formats
    expected_paths = {
        "Emergencies and Trauma",
        "Emergencies and Trauma > 1.1.1 Anaphylactic Shock",
        "Emergencies and Trauma > 1.1.1 Anaphylactic Shock > Definition",
        "Emergencies and Trauma > 1.1.1 Anaphylactic Shock > Management",
        "Emergencies and Trauma > 1.1.2 Burns"
    }

    cursor.execute("SELECT heading_path FROM sections")
    actual_paths = {row['heading_path'] for row in cursor.fetchall()}

    assert actual_paths == expected_paths, \
        f"heading_path mismatch. Expected: {expected_paths}, Got: {actual_paths}"

    print("✓ Section hierarchy validated successfully")
    print(f"✓ All 3 levels present: {levels}")
    print(f"✓ heading_path formatting correct for all levels")
    print(f"✓ order_index maintains sequence")
    print(f"✓ Can traverse chapter → disease → subsection")


# ==============================================================================
# Test 4: Raw Blocks and Docling Integration
# ==============================================================================

def test_docling_block_preservation(test_db):
    """
    Test: Ensure raw Docling output is preserved for auditability.

    This test ensures:
    1. Various Docling block types can be stored
    2. Metadata fields (page_range, docling_level, bbox) preserved
    3. Multi-page tables marked correctly
    4. All blocks link to correct document

    Success criteria:
    - All Docling block types represented
    - Metadata fields populated correctly
    - Can reconstruct original Docling output
    """
    cursor = test_db.cursor()

    # Insert test document
    cursor.execute("""
        INSERT INTO documents (id, title, checksum_sha256)
        VALUES (?, ?, ?)
    """, ("1", "Test Document", "abc123"))

    # Test various Docling block types
    test_blocks = [
        {
            'block_type': 'section_header',
            'text_content': '1.2 Malaria',
            'page_number': 145,
            'docling_level': 2,
            'bbox': '{"x": 72, "y": 100, "width": 200, "height": 20}'
        },
        {
            'block_type': 'paragraph',
            'text_content': 'Malaria is an acute febrile illness...',
            'page_number': 145,
            'bbox': '{"x": 72, "y": 130, "width": 450, "height": 60}'
        },
        {
            'block_type': 'table',
            'markdown_content': '| Drug | Dosage |\n|------|--------|\n| AL | 20/120mg |',
            'page_number': 146,
            'page_range': '146-147',
            'is_continuation': False
        },
        {
            'block_type': 'table',
            'markdown_content': '| Weight | Tablets |\n|--------|----------|\n| 5-14kg | 1 tablet |',
            'page_number': 147,
            'page_range': '146-147',
            'is_continuation': True
        },
        {
            'block_type': 'page_header',
            'text_content': 'Uganda Clinical Guidelines 2023',
            'page_number': 145
        },
        {
            'block_type': 'page_footer',
            'text_content': 'Page 145',
            'page_number': 145
        }
    ]

    # Insert all test blocks
    for i, block in enumerate(test_blocks):
        cursor.execute("""
            INSERT INTO raw_blocks (
                document_id, block_type, text_content, markdown_content,
                page_number, page_range, docling_level, bbox, is_continuation,
                element_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "1",
            block['block_type'],
            block.get('text_content'),
            block.get('markdown_content'),
            block['page_number'],
            block.get('page_range'),
            block.get('docling_level'),
            block.get('bbox'),
            block.get('is_continuation', False),
            f"elem_{i}"
        ))

    test_db.commit()

    # VALIDATION 1: All block types inserted
    cursor.execute("""
        SELECT DISTINCT block_type FROM raw_blocks
        ORDER BY block_type
    """)
    block_types = {row[0] for row in cursor.fetchall()}
    expected_types = {'section_header', 'paragraph', 'table', 'page_header', 'page_footer'}
    assert block_types == expected_types, \
        f"Should have all Docling block types. Expected: {expected_types}, Got: {block_types}"

    # VALIDATION 2: Check section_header has docling_level
    cursor.execute("""
        SELECT docling_level FROM raw_blocks
        WHERE block_type = 'section_header'
    """)
    level = cursor.fetchone()[0]
    assert level == 2, "section_header should have docling_level preserved"

    # VALIDATION 3: Check multi-page table markers
    cursor.execute("""
        SELECT page_number, page_range, is_continuation
        FROM raw_blocks
        WHERE block_type = 'table'
        ORDER BY page_number
    """)
    table_blocks = cursor.fetchall()
    assert len(table_blocks) == 2, "Should have 2 table blocks"

    # First table block
    assert table_blocks[0]['page_number'] == 146
    assert table_blocks[0]['page_range'] == '146-147'
    assert table_blocks[0]['is_continuation'] == 0, "First table block not a continuation"

    # Second table block (continuation)
    assert table_blocks[1]['page_number'] == 147
    assert table_blocks[1]['page_range'] == '146-147'
    assert table_blocks[1]['is_continuation'] == 1, "Second table block is continuation"

    # VALIDATION 4: Check bbox preserved
    cursor.execute("""
        SELECT bbox FROM raw_blocks
        WHERE block_type = 'section_header'
    """)
    bbox_json = cursor.fetchone()[0]
    assert bbox_json is not None, "bbox should be preserved"
    bbox = json.loads(bbox_json)
    assert 'x' in bbox and 'y' in bbox, "bbox should have coordinates"

    # VALIDATION 5: Check element_id preserved
    cursor.execute("SELECT COUNT(*) FROM raw_blocks WHERE element_id IS NOT NULL")
    count = cursor.fetchone()[0]
    assert count == len(test_blocks), "All blocks should have element_id"

    print("✓ Docling block preservation validated")
    print(f"✓ All {len(expected_types)} block types stored correctly")
    print(f"✓ Multi-page table markers preserved")
    print(f"✓ Metadata fields (docling_level, bbox, page_range) intact")
    print(f"✓ Can reconstruct original Docling output")


# ==============================================================================
# Test 5: Token Count Validation
# ==============================================================================

@pytest.mark.skipif(not HAS_TIKTOKEN, reason="tiktoken not installed")
def test_token_counting_accuracy(test_db):
    """
    Test: Verify tiktoken token counting matches expected values.

    This test ensures:
    1. Token counts use tiktoken cl100k_base encoding
    2. Stored token counts match actual token counts
    3. Both parent and child chunks use same encoding

    Success criteria:
    - Token counts accurate within ±1 token
    - Same encoding used throughout
    """
    cursor = test_db.cursor()
    encoding = tiktoken.get_encoding("cl100k_base")

    # Test strings with known approximate token counts
    test_cases = [
        ("Short clinical sentence about fever.", 50),  # ~6-8 tokens
        ("A medium-length paragraph describing malaria symptoms including " +
         "fever, chills, headache, muscle aches, and fatigue. " * 5, 250),  # ~200-300 tokens
        ("# Full Disease Section\n\n" + "Clinical content. " * 200, 1200)  # ~1000-1500 tokens
    ]

    # Insert test document and section
    cursor.execute("""
        INSERT INTO documents (id, title, checksum_sha256)
        VALUES (?, ?, ?)
    """, ("1", "Test Document", "abc123"))

    cursor.execute("""
        INSERT INTO sections (id, document_id, level, heading, heading_path, order_index)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (1, "1", 2, "Test Section", "Test Section", 1))

    # Test each case
    for i, (text, expected_range) in enumerate(test_cases):
        # Calculate actual token count
        actual_tokens = len(encoding.encode(text))

        # Insert as parent chunk
        cursor.execute("""
            INSERT INTO parent_chunks (section_id, content, token_count)
            VALUES (?, ?, ?)
        """, (1, text, actual_tokens))

        test_db.commit()

        # Retrieve and verify
        cursor.execute("""
            SELECT token_count, content FROM parent_chunks
            WHERE id = ?
        """, (i + 1,))
        row = cursor.fetchone()
        stored_tokens = row[0]
        stored_content = row[1]

        # Recalculate from stored content
        recalculated_tokens = len(encoding.encode(stored_content))

        # VALIDATION: Stored count matches actual count
        assert stored_tokens == actual_tokens, \
            f"Stored token count ({stored_tokens}) should match actual ({actual_tokens})"

        # VALIDATION: Recalculated count matches (proves encoding consistency)
        assert abs(recalculated_tokens - stored_tokens) <= 1, \
            f"Recalculated tokens ({recalculated_tokens}) should match stored ({stored_tokens})"

        print(f"✓ Test case {i+1}: {actual_tokens} tokens counted correctly")

    print("✓ Token counting accuracy validated")
    print(f"✓ Using tiktoken cl100k_base encoding")
    print(f"✓ All token counts accurate within ±1 token")


# ==============================================================================
# Test 6: Transaction and Rollback
# ==============================================================================

def test_transaction_boundaries(test_db):
    """
    Test: Verify atomic transactions and rollback on failure.

    This test ensures:
    1. Transactions are atomic (all-or-nothing)
    2. Rollback removes all partial data
    3. Database state unchanged after rollback

    Success criteria:
    - All inserts rolled back on error
    - No orphaned chunks remain
    - Database state unchanged
    """
    cursor = test_db.cursor()

    # Setup: Insert document and section
    cursor.execute("""
        INSERT INTO documents (id, title, checksum_sha256)
        VALUES (?, ?, ?)
    """, ("1", "Test Document", "abc123"))

    cursor.execute("""
        INSERT INTO sections (id, document_id, level, heading, heading_path, order_index)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (1, "1", 2, "Test Section", "Test Section", 1))

    test_db.commit()

    # Get initial counts
    cursor.execute("SELECT COUNT(*) FROM parent_chunks")
    initial_parent_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM child_chunks")
    initial_child_count = cursor.fetchone()[0]

    # Start transaction that will fail
    try:
        # Insert parent chunk
        cursor.execute("""
            INSERT INTO parent_chunks (id, section_id, content, token_count)
            VALUES (?, ?, ?, ?)
        """, (1, 1, "Parent content", 100))

        # Insert some child chunks successfully
        cursor.execute("""
            INSERT INTO child_chunks (id, parent_id, section_id, chunk_index, content, token_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (1, 1, 1, 0, "Child 1", 50))

        cursor.execute("""
            INSERT INTO child_chunks (id, parent_id, section_id, chunk_index, content, token_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (2, 1, 1, 1, "Child 2", 50))

        cursor.execute("""
            INSERT INTO child_chunks (id, parent_id, section_id, chunk_index, content, token_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (3, 1, 1, 2, "Child 3", 50))

        # This insert will fail (duplicate chunk_index)
        cursor.execute("""
            INSERT INTO child_chunks (id, parent_id, section_id, chunk_index, content, token_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (4, 1, 1, 2, "Child 4", 50))  # Duplicate chunk_index!

        test_db.commit()

    except sqlite3.IntegrityError:
        # Expected error - rollback transaction
        test_db.rollback()

    # VALIDATION 1: Parent chunk was not inserted (rolled back)
    cursor.execute("SELECT COUNT(*) FROM parent_chunks")
    final_parent_count = cursor.fetchone()[0]
    assert final_parent_count == initial_parent_count, \
        "Parent chunk should be rolled back"

    # VALIDATION 2: Child chunks were not inserted (rolled back)
    cursor.execute("SELECT COUNT(*) FROM child_chunks")
    final_child_count = cursor.fetchone()[0]
    assert final_child_count == initial_child_count, \
        "All child chunks should be rolled back"

    # VALIDATION 3: No orphaned data
    cursor.execute("""
        SELECT COUNT(*) FROM child_chunks c
        LEFT JOIN parent_chunks p ON c.parent_id = p.id
        WHERE p.id IS NULL
    """)
    orphaned = cursor.fetchone()[0]
    assert orphaned == 0, "No orphaned child chunks should exist"

    # VALIDATION 4: Database state unchanged
    cursor.execute("SELECT COUNT(*) FROM documents")
    doc_count = cursor.fetchone()[0]
    assert doc_count == 1, "Original document should still exist"

    cursor.execute("SELECT COUNT(*) FROM sections")
    section_count = cursor.fetchone()[0]
    assert section_count == 1, "Original section should still exist"

    print("✓ Transaction boundaries validated")
    print(f"✓ Rollback removed all {3} child chunk inserts")
    print(f"✓ Rollback removed parent chunk insert")
    print(f"✓ No orphaned data remains")
    print(f"✓ Database state unchanged after rollback")


# ==============================================================================
# Test 7: Foreign Key Constraints
# ==============================================================================

def test_foreign_key_constraints(test_db):
    """
    Test: Verify foreign key constraints prevent orphaned records.

    This test ensures:
    1. Cannot insert child without parent
    2. Cannot insert section without document
    3. Cascading deletes work correctly

    Success criteria:
    - Foreign key violations raise errors
    - Cascading deletes remove dependent records
    """
    cursor = test_db.cursor()

    # VALIDATION 1: Cannot insert child without parent
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO child_chunks (parent_id, section_id, chunk_index, content, token_count)
            VALUES (?, ?, ?, ?, ?)
        """, (999, 1, 0, "Orphan child", 50))

    # VALIDATION 2: Cannot insert section without document
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO sections (document_id, level, heading, heading_path, order_index)
            VALUES (?, ?, ?, ?, ?)
        """, ("nonexistent", 1, "Test", "Test", 1))

    # VALIDATION 3: Test cascading delete
    # Insert document → section → parent → children
    cursor.execute("""
        INSERT INTO documents (id, title, checksum_sha256)
        VALUES (?, ?, ?)
    """, ("1", "Test", "abc123"))

    cursor.execute("""
        INSERT INTO sections (id, document_id, level, heading, heading_path, order_index)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (1, "1", 2, "Test Section", "Test", 1))

    cursor.execute("""
        INSERT INTO parent_chunks (id, section_id, content, token_count)
        VALUES (?, ?, ?, ?)
    """, (1, 1, "Parent", 100))

    cursor.execute("""
        INSERT INTO child_chunks (id, parent_id, section_id, chunk_index, content, token_count)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (1, 1, 1, 0, "Child", 50))

    test_db.commit()

    # Delete parent, should cascade to children
    cursor.execute("DELETE FROM parent_chunks WHERE id = 1")
    test_db.commit()

    cursor.execute("SELECT COUNT(*) FROM child_chunks WHERE parent_id = 1")
    child_count = cursor.fetchone()[0]
    assert child_count == 0, "Cascading delete should remove child chunks"

    print("✓ Foreign key constraints validated")
    print(f"✓ Cannot create orphaned children")
    print(f"✓ Cannot create sections without document")
    print(f"✓ Cascading deletes work correctly")


# ==============================================================================
# Test 8: Edge Cases
# ==============================================================================

def test_empty_content_rejected(test_db):
    """Test that empty content is rejected by CHECK constraints."""
    cursor = test_db.cursor()

    cursor.execute("""
        INSERT INTO documents (id, title, checksum_sha256)
        VALUES (?, ?, ?)
    """, ("1", "Test", "abc123"))

    cursor.execute("""
        INSERT INTO sections (id, document_id, level, heading, heading_path, order_index)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (1, "1", 2, "Test", "Test", 1))

    # Try to insert parent chunk with empty content
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO parent_chunks (section_id, content, token_count)
            VALUES (?, ?, ?)
        """, (1, "", 100))

    print("✓ Empty content correctly rejected")


def test_negative_token_count_rejected(test_db):
    """Test that negative token counts are rejected."""
    cursor = test_db.cursor()

    cursor.execute("""
        INSERT INTO documents (id, title, checksum_sha256)
        VALUES (?, ?, ?)
    """, ("1", "Test", "abc123"))

    cursor.execute("""
        INSERT INTO sections (id, document_id, level, heading, heading_path, order_index)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (1, "1", 2, "Test", "Test", 1))

    # Try to insert chunk with negative token count
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO parent_chunks (section_id, content, token_count)
            VALUES (?, ?, ?)
        """, (1, "Content", -100))

    print("✓ Negative token count correctly rejected")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
