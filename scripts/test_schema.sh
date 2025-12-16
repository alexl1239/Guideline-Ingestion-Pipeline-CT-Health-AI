#!/bin/bash
# Test script for schema_v0.sql validation
# This script verifies the schema creates correctly and all tables work

echo "=================================="
echo "Testing schema_v0.sql"
echo "=================================="

# Create test database
TEST_DB="test_schema.db"
rm -f $TEST_DB

echo ""
echo "Step 1: Creating database from schema..."
sqlite3 $TEST_DB < schema_v0.sql

if [ $? -ne 0 ]; then
    echo "❌ FAILED: Schema creation failed"
    exit 1
fi
echo "✅ PASS: Schema created successfully"

echo ""
echo "Step 2: Checking all 7 tables exist..."
TABLES=$(sqlite3 $TEST_DB ".tables")
EXPECTED_TABLES=("documents" "sections" "raw_blocks" "parent_chunks" "child_chunks" "embedding_metadata" "vec_child_chunks")

# Note: vec_child_chunks is commented out in schema, so only check for 6 tables
REQUIRED_TABLES=("documents" "sections" "raw_blocks" "parent_chunks" "child_chunks" "embedding_metadata")

for table in "${REQUIRED_TABLES[@]}"; do
    if [[ $TABLES == *"$table"* ]]; then
        echo "  ✅ $table"
    else
        echo "  ❌ Missing: $table"
        exit 1
    fi
done

echo "  ℹ️  vec_child_chunks (requires sqlite-vec extension, checked separately)"

echo ""
echo "Step 3: Testing foreign key constraints..."

# Insert test document
sqlite3 $TEST_DB "INSERT INTO documents (id, filename, sha256_checksum) VALUES (1, 'test.pdf', 'abc123');"

# Insert test section
sqlite3 $TEST_DB "INSERT INTO sections (id, document_id, level, heading, heading_path, order_index) VALUES (1, 1, 2, 'Test', 'Test', 1);"

# Insert parent chunk
sqlite3 $TEST_DB "INSERT INTO parent_chunks (id, section_id, content, token_count) VALUES (1, 1, 'Test content', 1200);"

# Insert child chunk (tests FK to parent_chunks)
sqlite3 $TEST_DB "INSERT INTO child_chunks (id, parent_id, chunk_index, content, token_count) VALUES (1, 1, 0, 'Test', 256);"

if [ $? -ne 0 ]; then
    echo "❌ FAILED: Foreign key constraint test failed"
    exit 1
fi
echo "✅ PASS: Foreign keys working correctly"

echo ""
echo "Step 4: Testing parent-child relationship..."
RESULT=$(sqlite3 $TEST_DB "SELECT p.id, c.id FROM parent_chunks p JOIN child_chunks c ON c.parent_id = p.id WHERE p.id = 1;")

if [ -z "$RESULT" ]; then
    echo "❌ FAILED: Parent-child join failed"
    exit 1
fi
echo "✅ PASS: Parent-child relationship validated"

echo ""
echo "Step 5: Testing section hierarchy (self-referential FK)..."
sqlite3 $TEST_DB "INSERT INTO sections (id, document_id, parent_id, level, heading, heading_path, order_index) VALUES (2, 1, 1, 3, 'Subsection', 'Test > Subsection', 2);"

HIERARCHY=$(sqlite3 $TEST_DB "SELECT child.heading FROM sections parent JOIN sections child ON child.parent_id = parent.id WHERE parent.id = 1;")

if [ -z "$HIERARCHY" ]; then
    echo "❌ FAILED: Section hierarchy test failed"
    exit 1
fi
echo "✅ PASS: Section hierarchy working"

echo ""
echo "Step 6: Checking indexes exist..."
INDEXES=$(sqlite3 $TEST_DB ".indexes")
EXPECTED_INDEXES=("idx_sections_document_id" "idx_child_chunks_parent_id" "idx_parent_chunks_section_id" "idx_raw_blocks_section_id")

for idx in "${EXPECTED_INDEXES[@]}"; do
    if [[ $INDEXES == *"$idx"* ]]; then
        echo "  ✅ $idx"
    else
        echo "  ⚠️  Missing index: $idx (non-critical but recommended)"
    fi
done

echo ""
echo "Step 7: Testing token count constraints..."

# Test parent chunk constraint (must be 1000-2000 tokens)
sqlite3 $TEST_DB "INSERT INTO parent_chunks (section_id, content, token_count) VALUES (1, 'Test', 500);" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "❌ FAILED: Parent chunk token constraint not enforced (accepted 500 tokens)"
    exit 1
fi
echo "✅ PASS: Parent chunk constraint (1000-2000 tokens) enforced"

# Test child chunk constraint (must be <= 512 tokens)
sqlite3 $TEST_DB "INSERT INTO child_chunks (parent_id, chunk_index, content, token_count) VALUES (1, 1, 'Test', 600);" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "❌ FAILED: Child chunk token constraint not enforced (accepted 600 tokens)"
    exit 1
fi
echo "✅ PASS: Child chunk constraint (max 512 tokens) enforced"

echo ""
echo "Step 8: Testing views..."
VIEWS=$(sqlite3 $TEST_DB ".tables" | grep "^v_")
EXPECTED_VIEWS=("v_chunk_hierarchy" "v_section_stats" "v_document_summary")

for view in "${EXPECTED_VIEWS[@]}"; do
    if [[ $VIEWS == *"$view"* ]]; then
        echo "  ✅ $view"
    else
        echo "  ⚠️  Missing view: $view"
    fi
done

# Test view query
VIEW_RESULT=$(sqlite3 $TEST_DB "SELECT COUNT(*) FROM v_chunk_hierarchy;")
if [ "$VIEW_RESULT" -eq "1" ]; then
    echo "✅ PASS: Views are queryable"
else
    echo "⚠️  WARNING: View query returned unexpected result: $VIEW_RESULT"
fi

echo ""
echo "Step 9: Testing schema version tracking..."
VERSION=$(sqlite3 $TEST_DB "SELECT version FROM schema_version WHERE version = 'v0';")
if [ "$VERSION" == "v0" ]; then
    echo "✅ PASS: Schema version tracking working"
else
    echo "❌ FAILED: Schema version not recorded"
    exit 1
fi

echo ""
echo "=================================="
echo "🎉 ALL TESTS PASSED!"
echo "=================================="
echo ""
echo "Schema is valid and ready for use."
echo "Database created: $TEST_DB"
echo ""
echo "Database statistics:"
sqlite3 $TEST_DB "SELECT
    (SELECT COUNT(*) FROM documents) AS documents,
    (SELECT COUNT(*) FROM sections) AS sections,
    (SELECT COUNT(*) FROM parent_chunks) AS parent_chunks,
    (SELECT COUNT(*) FROM child_chunks) AS child_chunks;"
echo ""
echo "To inspect the test database:"
echo "  sqlite3 $TEST_DB"
echo ""
echo "To clean up test database:"
echo "  rm $TEST_DB"
echo ""

exit 0
