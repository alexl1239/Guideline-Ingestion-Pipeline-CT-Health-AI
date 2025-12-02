# Tests

Test structure for the UCG-23 RAG ETL pipeline.

## Directory Structure

```
tests/
├── unit/              # Unit tests for individual modules
├── integration/       # Integration tests for pipeline steps
└── qa_validation/     # QA validation tests (Step 7)
```

## Unit Tests

Test individual utilities and modules in isolation:
- `test_tokenizer.py` - Token counting accuracy
- `test_chunk_splitter.py` - Parent/child chunking logic
- `test_table_converter.py` - Table linearization
- `test_embedding_generator.py` - Embedding generation with mocks

## Integration Tests

Test pipeline steps with database interactions:
- `test_step0_registration.py` - Document registration
- `test_step1_parsing.py` - Parser abstraction and output
- `test_step2_segmentation.py` - Heading hierarchy construction
- `test_step3_cleanup.py` - Markdown normalization
- `test_step4_tables.py` - Table conversion accuracy
- `test_step5_chunking.py` - End-to-end chunking
- `test_step6_embeddings.py` - Embedding generation and storage
- `test_step7_qa.py` - QA validation logic
- `test_step8_export.py` - Database finalization

## QA Validation Tests

Tests for Step 7 validation requirements (section 5.8):

### Structural QA
- `test_structural_qa.py` - All validation checks:
  - 100% of chapters for section count consistency
  - All raw_blocks assigned to sections
  - Parent/child chunk coverage without gaps
  - Multi-page table merging

### Content QA
- `test_content_qa.py` - Clinical accuracy checks:
  - Dose pattern verification (regex for "0.5 mL", "2 drops")
  - Age specification preservation ("6, 10 and 14 weeks")
  - Numeric consistency between tables and linearized text
  - Cross-reference preservation

### Statistical Sampling
- `test_sampling_qa.py` - Statistical validation:
  - 20% sample of diseases for full accuracy review
  - 100% validation of emergency protocols
  - 100% validation of vaccine schedules

## Running Tests

```bash
# Run all tests
pytest tests/

# Run unit tests only
pytest tests/unit/

# Run integration tests only
pytest tests/integration/

# Run QA validation tests only
pytest tests/qa_validation/

# Run specific test file
pytest tests/unit/test_tokenizer.py

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

## Test Data

Test fixtures and sample data should be placed in:
- `tests/fixtures/` - Small test PDF samples
- `tests/fixtures/tables/` - Sample tables for linearization testing
- `tests/fixtures/markdown/` - Sample markdown for segmentation testing
