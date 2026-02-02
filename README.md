## Summary of the UCG-23 RAG Pipeline

The pipeline converts **UCG-23** from PDF into a **single SQLite database** that is:

* **Parser-flexible**

  * Primarily uses **Docling**

* **Clinically accurate**

  * Strict constraints on content transformation
  * Extensive multi-stage QA validation

* **Fully self-contained**

  * Produces one `.db` file
  * Includes embedded model metadata for reproducibility

* **Structured hierarchically**

  * Chapters → diseases → subsections → parent chunks → child chunks

* **Enriched**

  * Tables are converted into logical text statements
  * All clinical meaning is preserved exactly

* **Optimized for RAG**

  * Uses `sqlite-vec` embeddings (OpenAI `text-embedding-3-small`)
  * Similarity search runs on **child chunks**
  * Retrieval returns **parent chunks** to the LLM for cleaner context

* **Production-ready**

  * Transaction boundaries for every step
  * Robust error handling and recovery procedures
  * External logging for full traceability

* **Extensible**

  * Supports incremental updates
  * Multi-document ingestion compatible

---

### Final Deliverable

A **single portable SQLite database file** that can be distributed and used fully offline as the **core knowledge base** of a clinical support chatbot built around the *Uganda Clinical Guidelines 2023*.

---

## Working with Multiple Clinical Guidelines

The pipeline supports processing multiple clinical guideline documents, with each document generating its own separate SQLite database file. This keeps each guideline's data isolated and portable.

### File Structure

```
data/
  source_pdfs/                                      # All source PDF files
    Uganda_Clinical_Guidelines_2023.pdf
    National integrated Community Case Management (iCCM) guidelines.pdf

  Uganda_Clinical_Guidelines_2023_rag.db           # Generated databases
  National integrated Community Case Management (iCCM) guidelines_rag.db

  intermediate/                                     # Processing artifacts
  exports/                                          # Export artifacts
  qa_reports/                                       # QA reports
```

### Setting the Active Document

Open `src/config.py` and change this line:

```python
# Line ~165 in src/config.py
ACTIVE_PDF = "Uganda_Clinical_Guidelines_2023.pdf"  # Change to your PDF filename
```

Database name is auto-generated from PDF filename:
- `Uganda_Clinical_Guidelines_2023.pdf` → `Uganda_Clinical_Guidelines_2023_rag.db`
- `National integrated Community Case Management (iCCM) guidelines.pdf` → `National integrated Community Case Management (iCCM) guidelines_rag.db`

### Processing a New Guideline

**Step 1:** Add your PDF to `data/source_pdfs/`

**Step 2:** Edit `src/config.py` line ~165:
```python
ACTIVE_PDF = "YourGuideline.pdf"  # Change to your PDF filename
```

**Step 3:** Run the pipeline:
```bash
python src/main.py
```

A new database `YourGuideline_rag.db` will be created in `data/`

### Helper Scripts

#### List Available Databases

View all databases:

```bash
python scripts/list_databases.py
```

Shows all `*_rag.db` files with their size, date, and corresponding PDF.

### Querying a Specific Database

All scripts automatically use the database corresponding to `ACTIVE_PDF` in `config.py`:

```bash
# Query current active database
sqlite3 data/Uganda_Clinical_Guidelines_2023_rag.db "SELECT * FROM sections LIMIT 5;"

# Or use direct path
sqlite3 data/[YourDatabase]_rag.db "SELECT * FROM sections;"
```

### Best Practices

1. **Check config:** Verify `ACTIVE_PDF` in `config.py` before running pipeline
2. **Consistent naming:** Keep PDF filenames consistent (they become database names)
3. **Separate databases:** Each guideline gets its own `.db` file for portability

---

## Configuration

See `CLAUDE.md` for detailed pipeline configuration and implementation notes.
