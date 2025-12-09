# UCG-23 RAG ETL Pipeline – Architecture

## 1. High-level goal

Convert the **Uganda Clinical Guidelines 2023 (UCG-23)** PDF (~1100 pages) into a single, offline, queryable **SQLite RAG database** (`ucg23_rag.db`) that powers a clinical decision support chatbot.

Core properties:

- All content for UCG-23 lives inside one SQLite file
- Hierarchical structure: chapters → diseases → subsections → parent chunks → child chunks
- Embeddings stored with `sqlite-vec` for vector search
- Parsing done fully locally with **Docling**

---

## 2. Repo layout (current + planned)

```text
ugc23-rag-etl-pipeline/
├── .venv/                     # Python virtual environment (local only, not committed)
├── data/
│   ├── Uganda_Clinical_Guidelines_2023.pdf
│   └── docling_outputs/
│       ├── ucg23_docling.md   # Docling markdown export
│       └── ucg23_docling.json # Docling structured JSON export
├── scripts/
│   ├── docling_parse_ucg.py   # Parse UCG-23 PDF -> markdown + JSON (Docling)
│   ├── init_db.py             # Create SQLite DB + schema + register document
│   ├── inspect_db.py          # Basic DB inspection (table counts, sanity checks)
│   └── query_db.py            # Ad-hoc queries (e.g., lookup sections, chunks)
├── src/
│   ├── __init__.py
│   ├── config.py              # Central config/env loading (paths, API keys)
│   └── db.py                  # DB connection helpers + schema bootstrap
├── tests/
│   └── ... (unit tests for ETL pieces)
├── architecture.md            # This file: architecture + responsibilities
├── requirements.txt           # Python dependencies
├── README.md
└── CLAUDE.md
