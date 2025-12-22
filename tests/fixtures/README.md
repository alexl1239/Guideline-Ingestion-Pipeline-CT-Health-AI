# Test Fixtures

This directory contains test data and golden outputs for the UCG-23 RAG ETL Pipeline test suite.

## Test PDFs

### `ucg_4_pages.pdf`
- **Purpose**: Fast smoke test (runs in ~10-30 seconds)
- **Content**: Hand-picked section from Uganda Clinical Guidelines 2023
- **Pages**: [TODO: Document which pages from UCG-23 this represents]
- **Includes**:
  - Section headers with hierarchy
  - Body text with bullet lists
  - At least 1 table
  - Medical terminology

**Use for**: Quick validation during development, pre-commit checks

### `ucg_15_pages.pdf`
- **Purpose**: Comprehensive feature test (runs in ~1-2 minutes)
- **Content**: Complete disease section(s) from Uganda Clinical Guidelines 2023
- **Pages**: [TODO: Document which pages from UCG-23 this represents]
- **Includes**:
  - Multiple chapters/sections
  - Multiple tables (including LOC tables)
  - Figures/images
  - Complex medical content
  - Full disease subsections (Definition → Management)

**Use for**: Full integration testing, pre-PR validation

## Golden Databases

### `golden_4pages.db`
- **Purpose**: Reference output for 4-page test
- **Created**: Manually verified correct output from processing `ucg_4_pages.pdf`
- **How to regenerate**:
  ```bash
  # Run pipeline on 4-page PDF
  python src/main.py --input tests/fixtures/ucg_4_pages.pdf --output tests/fixtures/golden_4pages.db

  # Inspect thoroughly
  python scripts/inspect_db.py --db tests/fixtures/golden_4pages.db

  # If perfect, commit
  git add tests/fixtures/golden_4pages.db
  git commit -m "Update golden database for 4-page test"
  ```

### `golden_15pages.db`
- **Purpose**: Reference output for 15-page test
- **Created**: Manually verified correct output from processing `ucg_15_pages.pdf`
- **How to regenerate**: Same as above, using `ucg_15_pages.pdf`

## Updating Golden Databases

Golden databases should be updated when:
1. You intentionally change pipeline logic that affects output
2. You upgrade Docling version (block structure may change)
3. You change chunking parameters in `src/config.py`

**Process**:
1. Run pipeline on test PDF manually
2. Thoroughly inspect output with `inspect_db.py` and SQL queries
3. Verify medical accuracy (no content changes)
4. Verify chunk distributions are reasonable
5. Replace golden DB and commit with detailed message

## Test Data Selection Criteria

When selecting pages for test PDFs:
- ✅ Include hierarchical headings (H1, H2, H3)
- ✅ Include tables (especially Level of Care tables)
- ✅ Include bullet lists and numbered lists
- ✅ Include complete disease sections (not partial)
- ✅ Include medical terminology
- ✅ Avoid pages with only images or only text

## Notes

- Golden databases are committed to git (they're small and critical for regression testing)
- Test PDFs should be hand-picked, not random pages
- Document any special cases or edge cases covered by test data
