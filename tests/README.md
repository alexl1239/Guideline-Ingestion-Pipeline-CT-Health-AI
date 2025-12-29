# Testing Guide

Comprehensive test suite for the UCG-23 RAG ETL pipeline with **114 tests** covering database schema, pipeline steps, and data quality.

## Test Structure

```
tests/
├── conftest.py                   # Shared fixtures (temp databases, test PDFs)
├── unit/                            # Unit tests (fast, isolated logic)
│   ├── test_docling_mapper.py      # Docling JSON extraction logic
│   └── test_step0_registration.py  # SHA-256 computation and validation
└── integration/                     # Integration tests (real DB operations)
    ├── test_database_schema.py     # Schema creation and constraints
    ├── test_step0_registration.py  # Document registration
    └── test_step1_parsing.py       # Docling parsing and block extraction
```

## Running Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests
pytest tests/

# Run only unit tests (fast, no DB)
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v

# Run specific pipeline step
pytest tests/integration/test_step1_parsing.py -v

# Run with verbose output
pytest tests/ -v

# Run specific test
pytest tests/integration/test_step1_parsing.py::TestStep1OutputQuality::test_block_type_distribution_is_plausible -xvs
```

## What's Tested

### Database Schema (38 tests)
- Schema creation, validation, and idempotency
- All 7 tables: documents, sections, raw_blocks, parent_chunks, child_chunks, vec_child_chunks, embedding_metadata
- Foreign key enforcement and cascade deletes
- Constraint validation (CHECK, UNIQUE, NOT NULL)
- sqlite-vec extension loading and vector operations
- Transaction behavior and rollback scenarios

### Step 0: Document Registration (18 tests)
- PDF checksum computation (SHA-256)
- Document metadata storage
- Idempotent registration
- Embedding metadata tracking
- Error handling (missing files, duplicate checksums)

### Step 1: Parsing (7 tests)
- **Real Docling parsing** (no mocking) on 4-page test PDF
- Block extraction and storage
- Docling JSON preservation
- Block type distribution validation
- Page sequence completeness
- Content validation (all blocks have text/markdown)
- Idempotency checks

### Unit Tests (51 tests)
- Docling JSON extraction functions (page numbers, ranges, bounding boxes)
- Block type and level detection
- Text and markdown content extraction
- SHA-256 computation edge cases
- Document existence checks

## Test Quality Metrics

| Metric | Current Status |
|--------|---------------|
| Total Tests | 114 |
| Unit Tests | 51 (fast, isolated) |
| Integration Tests | 63 (with real DB) |
| Pipeline Steps Tested | 2 of 8 (Step 0, Step 1) |

## Test Data

Test fixtures in `tests/fixtures/`:
- `ucg_4_pages.pdf` - 4-page sample from UCG-23 for fast integration tests
- Future: Additional samples for specific edge cases

Test outputs in `tests/outputs/`:
- Temporary databases created during test runs
- Auto-cleaned after test completion

## Key Features

- **Temporary databases**: All tests use isolated temp DBs with auto-cleanup
- **Real Docling parsing**: Integration tests use actual Docling (no mocking)
- **Shared fixtures**: Common setups via `conftest.py`
- **Fast feedback**: Unit tests complete in <1 second
- **CI/CD ready**: Designed for automated pipelines
- **Comprehensive validation**: Block type distributions, content checks, idempotency

## Adding New Tests

### For New Pipeline Steps

1. Create integration test file: `tests/integration/test_stepN_<name>.py`
2. Use fixtures from `conftest.py`: `temp_db_with_registered_doc_4_pages`
3. Follow existing patterns from Step 1 tests
4. Test both success and failure scenarios
5. Validate output quality (distribution, completeness, accuracy)

### For New Utility Functions

1. Add unit tests to appropriate file in `tests/unit/`
2. Test edge cases, error handling, and expected behavior
3. Keep tests fast and isolated (no DB operations)

## Coverage Goals

- **Unit tests**: 100% coverage of utility functions
- **Integration tests**: All pipeline steps (0-8) with quality validation
- **Error handling**: All error paths tested
- **Data quality**: Distribution checks, consistency validation, clinical accuracy
