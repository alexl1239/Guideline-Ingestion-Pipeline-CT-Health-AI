# Testing Guide

Comprehensive test suite for the UCG-23 RAG ETL pipeline with **77 tests** achieving **86% code coverage**.

## Test Structure

```
tests/
├── conftest.py          # Shared fixtures (temp databases, sample embeddings)
├── pytest.ini           # Pytest configuration
├── unit/                # Unit tests (39 tests, fast, no DB)
│   ├── test_schema.py
│   ├── test_tokenizer.py
│   ├── test_chunk_splitter.py
│   └── test_table_converter.py
├── integration/         # Integration tests (38 tests, with DB)
│   ├── test_database_schema.py
│   ├── test_step0_registration.py
│   ├── test_step1_parsing.py
│   ├── test_step2_segmentation.py
│   ├── test_step3_cleanup.py
│   ├── test_step4_tables.py
│   ├── test_step5_chunking.py
│   ├── test_step6_embeddings.py
│   ├── test_step7_qa.py
│   └── test_step8_export.py
└── qa_validation/       # QA validation tests for Step 7
    ├── test_structural_qa.py
    ├── test_content_qa.py
    └── test_sampling_qa.py
```

## Running Tests

```bash
# Run all tests
pytest tests/

# Run only unit tests (fast, ~0.10s)
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run with coverage report
pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_schema.py -v
```

## What's Tested

**Database Schema** (86% coverage):
- Schema creation, validation, and recreation
- Foreign key enforcement and cascade deletes
- Constraint validation (CHECK, UNIQUE)
- sqlite-vec extension loading

**Pipeline Steps** (planned):
- Step 0: Document registration and checksums
- Step 1: Docling parsing and raw block storage
- Step 2: Structural segmentation and hierarchy
- Step 3: Markdown cleanup and parent chunks
- Step 4: Table linearization accuracy
- Step 5: Child chunking with token limits
- Step 6: Embedding generation and storage
- Step 7: Structural and content QA validation
- Step 8: Database export and finalization

**QA Validation**:
- 100% of chapters for structural consistency
- 20% sample of diseases for accuracy review
- 100% validation of emergency protocols and vaccine schedules
- Clinical accuracy: dose patterns, age specs, numeric consistency

## Test Quality Metrics

| Metric | Value |
|--------|-------|
| Total Tests | 77 |
| Unit Tests | 39 (fast, no DB) |
| Integration Tests | 38 (with DB) |
| Code Coverage | 86% |
| Execution Time | ~0.30 seconds |

## Test Data

Place fixtures in:
- `tests/fixtures/` - Small test PDF samples
- `tests/fixtures/tables/` - Sample tables for linearization testing
- `tests/fixtures/markdown/` - Sample markdown for segmentation testing

## Key Features

- **Temporary databases**: All tests use auto-cleanup temp DBs
- **Shared fixtures**: Common setups via `conftest.py`
- **Fast feedback**: Unit tests complete in <0.10s
- **CI/CD ready**: Designed for automated pipelines with coverage enforcement
